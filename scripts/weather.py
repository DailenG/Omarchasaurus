"""Rare passing showers: active-time arrivals and motion-time cloud/rain/rainbow."""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import math
import random

from layout import HORIZON_Y, RainDrop
from scene_types import Nanoseconds, RainStreakPose, WeatherPose

SECOND = 1_000_000_000


def _ease(value: float) -> float:
    value = min(1.0, max(0.0, value))
    return value * value * (3 - 2 * value)


@dataclass(frozen=True, slots=True)
class _Episode:
    born: Fraction
    calm: bool

    @property
    def duration(self) -> int:
        return (90 if self.calm else 66) * SECOND


def _cloud_x(age: float, calm: bool) -> float:
    return 46 + (8 if calm else 16) * _ease(age / (42 if calm else 30))


def _birth_intensity(age: float, calm: bool) -> float:
    start, full, taper, stop = (6, 14, 24, 28) if calm else (4, 10, 18, 22)
    return _ease((age - start) / (full - start)) * (1 - _ease((age - taper) / (stop - taper)))


class ValleyWeather:
    """One episode, one interval stream, and algebraic rain without spawn history.

    Constructor clocks establish a fresh lifecycle origin. Replaying constant-
    configuration history means constructing at zero and advancing both clocks.
    Every deadline consumes exactly one next interval, even while busy. Profile
    changes only affect future births, never the geometry/timing of a live event.
    """
    def __init__(self, descriptors: tuple[RainDrop, ...], seed: int,
                 elapsed_ns: Nanoseconds = 0, motion_ns: Nanoseconds = 0) -> None:
        self.descriptors = descriptors
        self.rng = random.Random(seed)
        self.elapsed_ns = Fraction(elapsed_ns)
        self.motion_ns = Fraction(motion_ns)
        self.deadline = self.elapsed_ns + self._interval()
        self.generation = -1
        self._episode: _Episode | None = None

    def _interval(self) -> int:
        return self.rng.randint(600 * SECOND, 900 * SECOND)

    def advance(self, elapsed_ns: Nanoseconds, motion_ns: Nanoseconds,
                *, calm: bool = False) -> None:
        """Resolve crossings in clock order, including arbitrary clock partitions."""
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
                self._episode = None
            else:
                break
        self.elapsed_ns, self.motion_ns = end_elapsed, end_motion

    def _rain(self, age: float, calm: bool) -> tuple[RainStreakPose, ...]:
        count = 16 if calm else 48
        width = 18 if calm else 22
        stop = 28 if calm else 22
        baseline = 8.5
        fall = HORIZON_Y - baseline
        streaks = []
        for index, drop in enumerate(self.descriptors[:count]):
            period = drop.period * (1.8 if calm else 1)
            cycle = math.floor((age + drop.phase * period) / period)
            born = cycle * period - drop.phase * period
            # Admission is decided at natural birth, never at the current age.
            if not 0 <= born < stop or (index + .5) / count > _birth_intensity(born, calm):
                continue
            progress = (age - born) / period
            head_y = min(HORIZON_Y, baseline + fall * progress)
            tail_y = max(baseline, head_y - drop.length * (.65 if calm else 1))
            origin_x = _cloud_x(born, calm) + (drop.offset - .5) * width * .85
            slant = drop.slant * (.65 if calm else 1)
            streaks.append(RainStreakPose(
                id=drop.id, cycle=cycle,
                head=(origin_x + slant * (head_y - baseline), head_y),
                tail=(origin_x + slant * (tail_y - baseline), tail_y)))
        return tuple(streaks)

    def current(self) -> WeatherPose | None:
        """Return a fresh viewport-independent pose without advancing or drawing RNG."""
        episode = self._episode
        if episode is None:
            return None
        calm = episode.calm
        age = float((self.motion_ns - episode.born) / SECOND)
        stop, clear, end = (28, 42, 90) if calm else (22, 30, 66)
        arrival = 6 if calm else 4
        cloud_strength = _ease(age / arrival) * (1 - _ease((age - stop) / (clear - stop)))
        rain_strength = (_ease((age - arrival) / (8 if calm else 6)) *
                         (1 - _ease((age - stop) / (clear - stop))))
        rainbow_strength = (_ease((age - clear) / (8 if calm else 4)) *
                            (1 - _ease((age - (end - (12 if calm else 8))) / (12 if calm else 8))))
        return WeatherPose(
            generation=self.generation,
            state='shower' if age < stop else 'clearing' if age < clear else 'rainbow',
            age=age, calm=calm,
            cloud_x=_cloud_x(age, calm), cloud_y=8.5,
            cloud_width=18.0 if calm else 22.0,
            cloud_height=2.8 if calm else 3.2,
            cloud_strength=cloud_strength, rain_strength=rain_strength,
            rainbow_strength=rainbow_strength,
            rain=self._rain(age, calm) if age < clear else ())
