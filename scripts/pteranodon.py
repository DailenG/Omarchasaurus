"""Pure flying silhouettes and one bounded, active-time flock encounter."""
from __future__ import annotations

from fractions import Fraction
import math
import random

from layout import Pteranodon
from scene_types import (ActorBounds, HorizontalBounds, Nanoseconds,
                         PteranodonFlockPose, PteranodonPose)

SECOND = 1_000_000_000
PACE = Fraction(6, 5)


def flight_radius(span: float) -> float:
    """Rotation-safe envelope of every authored wing, head and tail point."""
    return math.hypot(span, 2.8)


def pteranodon_bounds(pose: PteranodonPose) -> ActorBounds:
    radius = flight_radius(pose['span'])
    return (pose['x'] - radius, pose['y'] - radius,
            pose['x'] + radius, pose['y'] + radius, pose['depth'])


def pteranodon_pose(bird: Pteranodon, time: float, motion: float,
                    x: float) -> PteranodonPose:
    """Two flapping beats, a glide, a gentle bank, then a longer glide.

    Squared-sine windows join at zero value and velocity. Bank is applied by
    the renderer to the complete silhouette, not merely to the wing tips.
    """
    cycle = (time * .53 + bird.phase) % 9
    flap = (math.sin(math.pi * cycle / 2) ** 2 * math.sin(math.tau * cycle)
            if cycle < 2 else 0.0)
    bank = (.28 * math.sin(math.pi * (cycle - 4) / 2) ** 2
            if 4 <= cycle < 6 else 0.0)
    bank *= motion * (1 if math.sin(bird.phase) >= 0 else -1)
    y = bird.y + math.sin(time * .31 + bird.phase) * .55 * motion
    return PteranodonPose(id=bird.id, depth=bird.depth, span=bird.span,
                         x=x, y=y, tip_y=y - .7 - flap * 1.9 * motion,
                         bank=bank)


class PteranodonFlocks:
    """One pass at a time; no queues, recorded episodes, or snapshot mutations.

    Elapsed time schedules arrivals independently of motion speed. Motion time
    advances the formation rigidly. Event interpolation preserves overshoot and
    makes constant-configuration replay independent of frame rate. An admitted
    prefix is latched for retirement even if Off or a lower cap releases seats.
    """
    def __init__(self, descriptors: tuple[Pteranodon, ...], visit_seed: int,
                 bounds: HorizontalBounds, elapsed_ns: Nanoseconds = 0,
                 motion_ns: Nanoseconds = 0, *, enabled: bool = True) -> None:
        self.descriptors = descriptors
        self.bounds = bounds
        self.elapsed_ns = Fraction(elapsed_ns)
        self.motion_ns = Fraction(motion_ns)
        self.bounds_changed_at = self.motion_ns
        self.enabled = enabled
        self.rng = random.Random(visit_seed)
        self.generation = -1
        self.active = False
        self.born = self.motion_ns
        self.start_x = 0.0
        self.admitted_count: int | None = None
        self.deadline = self.elapsed_ns + self._interval()

    def _interval(self) -> int:
        return self.rng.randint(240 * SECOND, 540 * SECOND)

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled

    def set_viewport(self, bounds: HorizontalBounds) -> None:
        if bounds != self.bounds:
            self.bounds = bounds
            self.bounds_changed_at = self.motion_ns

    def latch_prefix(self, count: int) -> None:
        if self.active and self.admitted_count is None and count >= 2:
            self.admitted_count = min(count, len(self.descriptors))
            # A newly shortened rear must never retire at a historical instant.
            self.bounds_changed_at = self.motion_ns

    def _arrive(self, motion_ns: Fraction) -> None:
        self.generation += 1
        self.active = True
        self.born = motion_ns
        self.admitted_count = None
        self.start_x = min(self.bounds[0] - bird.start_x
                           - flight_radius(bird.span) - 3.5 * bird.depth - 1
                           for bird in self.descriptors)

    def _departure_boundary(self) -> Fraction:
        members = self.descriptors[:self.admitted_count]
        target = max(self.bounds[1] + 3.5 * bird.depth + 1
                     - bird.start_x + flight_radius(bird.span)
                     for bird in members)
        distance = Fraction(str(max(0.0, target - self.start_x)))
        return max(self.born + distance / PACE * SECOND, self.bounds_changed_at)

    def advance(self, elapsed_ns: Nanoseconds, motion_ns: Nanoseconds) -> None:
        end_elapsed, end_motion = Fraction(elapsed_ns), Fraction(motion_ns)
        elapsed, motion = self.elapsed_ns, self.motion_ns
        while True:
            departure = self._departure_boundary() if self.active else None
            arrival = (Fraction(0) if self.deadline <= elapsed else
                       (self.deadline - elapsed) / (end_elapsed - elapsed)
                       if end_elapsed > elapsed else None)
            leaving = (Fraction(0) if departure is not None and departure <= motion else
                       (departure - motion) / (end_motion - motion)
                       if departure is not None and end_motion > motion else None)
            if arrival is not None and arrival <= 1 and (leaving is None or arrival <= leaving):
                motion += (end_motion - motion) * arrival
                elapsed += (end_elapsed - elapsed) * arrival
                self.deadline += self._interval()
                if self.enabled and not self.active:
                    self._arrive(motion)
            elif leaving is not None and leaving <= 1:
                elapsed += (end_elapsed - elapsed) * leaving
                motion += (end_motion - motion) * leaving
                self.active = False
                self.admitted_count = None
            else:
                break
        self.elapsed_ns, self.motion_ns = end_elapsed, end_motion

    def current(self, time: float, motion: float = 1.0) -> PteranodonFlockPose | None:
        if not self.active:
            return None
        travel = float((self.motion_ns - self.born) / SECOND * PACE)
        return PteranodonFlockPose(
            generation=self.generation,
            members=tuple(pteranodon_pose(bird, time, motion,
                                         self.start_x + travel + bird.start_x)
                          for bird in self.descriptors))
