"""One recurring nest encounter, scheduled in active time and walked in motion time."""
from __future__ import annotations

from fractions import Fraction
import math
import random

from layout import Nest
from scene_types import ActorBounds, HatchingPose, Nanoseconds, ViewportBounds

SECOND = 1_000_000_000
YOUNG_EXTENTS = (-4.2, -5.8, 2.6, .2)
YOUNG_HEIGHT = 5.8
DURATION = 33 * SECOND


def egg_offsets(nest: Nest) -> tuple[float, ...]:
    """The same authored clutch geometry for resting and animated eggs."""
    return (-.9, 0.0, .9) if nest.eggs == 3 else (-1.2, -.4, .4, 1.2)


def young_brachiosaurus_bounds(pose: HatchingPose) -> ActorBounds:
    left, top, right, bottom = YOUNG_EXTENTS
    return (pose['x'] + left, pose['foot_y'] + top,
            pose['x'] + right, pose['foot_y'] + bottom, pose['depth'])


def _ease(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3 - 2 * value)


class NestHatching:
    """One live generation, no pending arrivals or recorded event history.

    Only intervals consume randomness. Rejected/busy deadlines consume the same
    interval as successful ones. Egg rotation and gait use the independent layout
    phase, so admission cannot perturb future scheduled deadlines.
    """
    def __init__(self, nest: Nest | None, seed: int, phase: float,
                 bounds: ViewportBounds = (23.0, 0.0, 123.0, 60.0),
                 elapsed_ns: Nanoseconds = 0, walk_ns: Nanoseconds = 0) -> None:
        self.nest = nest
        self.bounds = bounds
        self.phase = phase
        self.rng = random.Random(seed)
        self.elapsed_ns = Fraction(elapsed_ns)
        self.walk_ns = Fraction(walk_ns)
        self.deadline = self.elapsed_ns + self._interval()
        self.active = False
        self.generation = -1
        self.born = self.walk_ns
        self.egg_index = 0

    def _interval(self) -> int:
        return self.rng.randint(480 * SECOND, 900 * SECOND)

    def set_nest(self, nest: Nest | None) -> None:
        if nest != self.nest:
            self.cancel()
        self.nest = nest

    def set_viewport(self, bounds: ViewportBounds) -> None:
        self.bounds = bounds

    def cancel(self) -> None:
        self.active = False

    def _nest_visible(self) -> bool:
        nest = self.nest
        if nest is None:
            return False
        left, top, right, bottom = self.bounds
        return (nest.x + nest.radius >= left
                and nest.x - nest.radius <= right
                and nest.y + .5 >= top
                and nest.y - 1.6 <= bottom)

    def advance(self, elapsed_ns: Nanoseconds, walk_ns: Nanoseconds,
                *, can_start: bool = True) -> None:
        """Interpolate deadline and completion crossings in chronological order."""
        end_elapsed, end_walk = Fraction(elapsed_ns), Fraction(walk_ns)
        elapsed, walk = self.elapsed_ns, self.walk_ns
        while True:
            finish = self.born + DURATION if self.active else None
            arrival = (Fraction(0) if self.deadline <= elapsed else
                       (self.deadline - elapsed) / (end_elapsed - elapsed)
                       if end_elapsed > elapsed else None)
            leaving = (Fraction(0) if finish is not None and finish <= walk else
                       (finish - walk) / (end_walk - walk)
                       if finish is not None and end_walk > walk else None)
            if arrival is not None and arrival <= 1 and (leaving is None or arrival < leaving):
                walk += (end_walk - walk) * arrival
                elapsed += (end_elapsed - elapsed) * arrival
                self.deadline += self._interval()
                if can_start and not self.active and self.nest is not None and self._nest_visible():
                    self.generation += 1
                    self.active = True
                    self.born = walk
                    slots = egg_offsets(self.nest)
                    first = int(self.phase / math.tau * len(slots)) % len(slots)
                    self.egg_index = (first + self.generation) % len(slots)
            elif leaving is not None and leaving <= 1:
                elapsed += (end_elapsed - elapsed) * leaving
                walk += (end_walk - walk) * leaving
                self.active = False
            else:
                break
        self.elapsed_ns, self.walk_ns = end_elapsed, end_walk

    def current(self, reaction: float = 0, calm: bool = False) -> HatchingPose | None:
        """Pure rigid pose; the renderer clips emergence against the nest rim."""
        if not self.active or self.nest is None:
            return None
        nest = self.nest
        age = float((self.walk_ns - self.born) / SECOND)
        egg_x, egg_y = nest.x + egg_offsets(nest)[self.egg_index], nest.y - .8
        wobble = crack = emerge = reset = stride = 0.0
        progress = 0.0
        if age < 4:
            state = 'wobbling'
            wobble = .22 * math.sin(math.tau * age / 1.1) * math.sin(math.pi * age / 4) ** 2
        elif age < 7:
            state = 'cracking'
            crack = _ease((age - 4) / 3)
        elif age < 11:
            state = 'hatching'
            crack = 1.0
            emerge = _ease((age - 7) / 4)
        elif age < 29:
            state = 'toddling'
            crack = emerge = 1.0
            progress = _ease((age - 11) / 18)
            stride = math.sin(math.pi * (age - 11) / 18) ** 2
        else:
            state = 'settling'
            crack = emerge = progress = 1.0
            reset = _ease((age - 29) / 4)
        x = egg_x + (69.0 - egg_x) * progress
        foot_y = nest.y + YOUNG_HEIGHT * (1 - emerge) + (48.6 - nest.y) * progress
        distance = math.hypot(69.0 - egg_x, 48.6 - nest.y) * progress
        return HatchingPose(
            id='brachiosaurus:young', generation=self.generation, state=state,
            egg_index=self.egg_index, egg_x=egg_x, egg_y=egg_y,
            wobble=wobble * (.18 if calm else 1), crack=crack,
            emerge=emerge, reset=reset, x=x, foot_y=foot_y,
            depth=.8 + (.39 - .8) * progress,
            phase=self.phase + distance * 2.4, stride=stride,
            blink=(age + self.phase) % 5.7 > 5.5, reaction=reaction)
