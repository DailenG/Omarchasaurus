"""One far-bank visitor, scheduled in active time and moving in walk time."""
from fractions import Fraction
import math
import random

SECOND = 1_000_000_000
PACE = Fraction(3, 4)
REAR = -42
NOSE = 40


def _ease(value):
    value = max(0.0, min(1.0, value))
    return value * value * (3 - 2 * value)


class DiplodocusVisits:
    """Constant-space lifecycle; snapshots never advance clocks or draw randomness.

    Event boundaries are interpolated between the last elapsed/walk clock pair.
    This also replays constant-speed snapshot history without a frame-step loop.
    """
    def __init__(self, descriptor, resident: bool, bounds, elapsed_ns=0, walk_ns=0):
        self.descriptor = descriptor
        self.resident_requested = resident
        self.bounds = bounds
        self.elapsed_ns = Fraction(elapsed_ns)
        self.walk_ns = Fraction(walk_ns)
        self.bounds_changed_at = self.walk_ns
        self.rng = random.Random(descriptor.visit_seed)
        self.generation = -1
        self.state = None
        self.born = self.walk_ns
        self.start_x = descriptor.shore_x
        self.approach_duration = Fraction(0)
        self.travel = 0.0
        self.resident = False
        self.exit_at = None
        self.deadline = None
        if resident:
            self.generation = 0
            self.state = 'drinking'
            self.resident = True
            self.born -= 12 * SECOND
        else:
            self.deadline = self.elapsed_ns + self._interval()

    def _interval(self):
        return self.rng.randint(600 * SECOND, 1200 * SECOND)

    @property
    def token(self):
        return self.generation, self.state is not None

    def set_viewport(self, bounds):
        if bounds != self.bounds:
            self.bounds = bounds
            self.bounds_changed_at = self.walk_ns

    def set_resident(self, resident: bool):
        if resident == self.resident_requested:
            return
        self.resident_requested = resident
        if resident:
            self.deadline = None
            self.exit_at = None
            if self.state is None:
                self._approach(self.walk_ns)
            elif self.state == 'drinking':
                self.resident = True
        else:
            self.deadline = self.elapsed_ns + self._interval()
            if self.state == 'drinking' and self.resident:
                age = self.walk_ns - self.born
                self.exit_at = self.born + (age // (36 * SECOND) + 1) * 36 * SECOND

    def _approach(self, walk_ns):
        self.generation += 1
        self.state = 'approaching'
        self.born = walk_ns
        self.start_x = min(self.descriptor.shore_x,
                           self.bounds[0] - 3.5 * self.descriptor.depth - NOSE - 1)
        distance = Fraction(str(self.descriptor.shore_x - self.start_x))
        self.approach_duration = distance / PACE * SECOND
        self.travel = 0.0
        self.resident = False
        self.exit_at = None

    def _departure_boundary(self):
        # Invert the two-second acceleration ramp, then constant forward pace.
        target = self.bounds[1] + 3.5 * self.descriptor.depth - REAR + 1
        distance = max(0.0, target - self.descriptor.shore_x)
        age = (math.sqrt(4 * distance / float(PACE)) if distance < float(PACE)
               else distance / float(PACE) + 1)
        return max(self.born + Fraction(str(age)) * SECOND, self.bounds_changed_at)

    def advance(self, elapsed_ns, walk_ns):
        end_elapsed, end_walk = Fraction(elapsed_ns), Fraction(walk_ns)
        elapsed, walk = self.elapsed_ns, self.walk_ns
        while True:
            event_elapsed = self.deadline
            event_walk = None
            if self.state == 'approaching':
                event_walk = self.born + self.approach_duration
            elif self.state == 'drinking':
                event_walk = (self.exit_at if self.resident else self.born + 24 * SECOND)
            elif self.state == 'departing':
                event_walk = self._departure_boundary()

            # Consume due events even after another event exhausts this segment.
            arrival = (Fraction(0) if event_elapsed is not None and event_elapsed <= elapsed
                       else (event_elapsed - elapsed) / (end_elapsed - elapsed)
                       if event_elapsed is not None and end_elapsed > elapsed else None)
            transition = (Fraction(0) if event_walk is not None and event_walk <= walk
                          else (event_walk - walk) / (end_walk - walk)
                          if event_walk is not None and end_walk > walk else None)
            if arrival is not None and arrival <= 1 and (transition is None or arrival <= transition):
                walk += (end_walk - walk) * arrival
                elapsed += (end_elapsed - elapsed) * arrival
                # Schedule from the previous scheduled arrival, never completion.
                self.deadline += self._interval()
                if self.state is None:
                    self._approach(walk)
            elif transition is not None and transition <= 1:
                elapsed += (end_elapsed - elapsed) * transition
                walk += (end_walk - walk) * transition
                if self.state == 'approaching':
                    self.travel = self.descriptor.shore_x - self.start_x
                    self.state = 'drinking'
                    self.born = walk
                    self.resident = self.resident_requested
                elif self.state == 'drinking':
                    self.state = 'departing'
                    self.born = walk
                    self.exit_at = None
                else:
                    self.state = None
                    if self.resident_requested:
                        self._approach(walk)
            else:
                break
        self.elapsed_ns, self.walk_ns = end_elapsed, end_walk

    def current(self, motion_time, reaction=0.0):
        if self.state is None:
            return None
        age = float((self.walk_ns - self.born) / SECOND)
        x = self.descriptor.shore_x
        stride = drink = 0.0
        travel = self.travel
        state = self.state
        if state == 'approaching':
            duration = float(self.approach_duration / SECOND)
            progress = min(1.0, age / duration) if duration else 1.0
            travel = (self.descriptor.shore_x - self.start_x) * _ease(progress)
            x = self.start_x + travel
            stride = 4 * progress * (1 - progress)
        elif state == 'departing':
            distance = float(PACE) * (age * age / 4 if age < 2 else age - 1)
            x += distance
            travel += distance
            stride = min(1.0, age / 2)
        else:
            cycle_age = age % 36 if self.resident else age
            drink = _ease(cycle_age / 6) * _ease((24 - cycle_age) / 6)
            if cycle_age >= 24:
                state = 'looking'
        return {
            'id': self.descriptor.id, 'x': x,
            'foot_y': self.descriptor.foot_y, 'depth': self.descriptor.depth,
            'phase': self.descriptor.phase + travel * 1.8,
            'stride': stride, 'drink': drink,
            'look': .045 * math.sin(motion_time * .31 + self.descriptor.look_phase),
            'reaction': reaction,
            'blink': (motion_time + self.descriptor.blink_phase) % 6.9 > 6.7,
            'state': state, 'generation': self.generation,
        }
