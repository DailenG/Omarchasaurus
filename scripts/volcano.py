"""One soft smoke swell, with active-time arrivals and motion-time buoyancy."""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import math
import random

from scene_types import Nanoseconds, VolcanoPuffPose

SECOND = 1_000_000_000


@dataclass(frozen=True, slots=True)
class _Episode:
    born: Fraction
    calm: bool

    @property
    def duration(self) -> int:
        return (32 if self.calm else 24) * SECOND

    @property
    def rise(self) -> Fraction:
        return Fraction(4, 5) if self.calm else Fraction(12, 5)


class VolcanoPuffs:
    """Independent deadlines, one live episode, and no recorded event history.

    Constructor clocks establish a fresh scheduling origin. To replay history,
    construct at zero and advance to the accumulated elapsed and motion clocks.
    Busy deadlines still draw their next interval and are never queued. Completed
    buoyancy is retained modulo the ambient smoke's eleven-unit wrap period.
    """
    def __init__(self, seed: int, elapsed_ns: Nanoseconds = 0,
                 motion_ns: Nanoseconds = 0) -> None:
        self.rng = random.Random(seed)
        self.elapsed_ns = Fraction(elapsed_ns)
        self.motion_ns = Fraction(motion_ns)
        self.deadline = self.elapsed_ns + self._interval()
        self.generation = -1
        self._episode: _Episode | None = None
        self._completed_lift = Fraction(0)

    def _interval(self) -> int:
        return self.rng.randint(180 * SECOND, 420 * SECOND)

    def advance(self, elapsed_ns: Nanoseconds, motion_ns: Nanoseconds,
                *, calm: bool = False) -> None:
        """Resolve birth and retirement crossings in exact chronological order."""
        end_elapsed, end_motion = Fraction(elapsed_ns), Fraction(motion_ns)
        elapsed, motion = self.elapsed_ns, self.motion_ns
        while True:
            episode = self._episode
            finish = episode.born + episode.duration if episode is not None else None
            arrival = (Fraction(0) if self.deadline <= elapsed else
                       (self.deadline - elapsed) / (end_elapsed - elapsed)
                       if end_elapsed > elapsed else None)
            leaving = (Fraction(0) if finish is not None and finish <= motion else
                       (finish - motion) / (end_motion - motion)
                       if finish is not None and end_motion > motion else None)
            if arrival is not None and arrival <= 1 and (leaving is None or arrival < leaving):
                motion += (end_motion - motion) * arrival
                elapsed += (end_elapsed - elapsed) * arrival
                self.deadline += self._interval()
                if self._episode is None:
                    self.generation += 1
                    self._episode = _Episode(motion, calm)
            elif episode is not None and leaving is not None and leaving <= 1:
                elapsed += (end_elapsed - elapsed) * leaving
                motion += (end_motion - motion) * leaving
                self._completed_lift = (self._completed_lift + episode.rise) % 11
                self._episode = None
            else:
                break
        self.elapsed_ns, self.motion_ns = end_elapsed, end_motion

    def current(self) -> VolcanoPuffPose | None:
        """Return a fresh pose without advancing clocks or consuming randomness."""
        episode = self._episode
        if episode is None:
            return None
        progress = float((self.motion_ns - episode.born) / episode.duration)
        strength = math.sin(math.pi * progress) ** 2 if 0 < progress < 1 else 0.0
        return VolcanoPuffPose(generation=self.generation, progress=progress,
                               strength=strength, calm=episode.calm)

    @property
    def smoke_lift(self) -> float:
        """Continuous added rise; only the ambient smoke's regular wrap remains."""
        episode = self._episode
        added = 0.0
        if episode is not None:
            progress = float((self.motion_ns - episode.born) / episode.duration)
            added = float(episode.rise) * (progress - math.sin(math.tau * progress) / math.tau)
        return (float(self._completed_lift) + added) % 11
