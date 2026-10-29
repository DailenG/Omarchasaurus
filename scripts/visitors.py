"""One session-shuffled ground visitor, replaced only beyond the viewport."""
import hashlib
import math
import random

from population import walking_distance, walking_time


class RandomVisitors:
    def __init__(self, scene_seed, session_seed, pool, walk_time, bounds, start_in_view, extents):
        key = f'omarchasaurus-visitors-v1:{scene_seed}:{session_seed}'.encode('ascii')
        self.rng = random.Random(int.from_bytes(hashlib.sha256(key).digest(), 'big'))
        self.pool = tuple(pool)
        self.bounds = bounds
        self.extents = extents
        self.bounds_changed_at = walk_time
        self.species = None
        self.generation = -1
        self.born = walk_time
        self.start_x = 0.0
        self.phase = 0.0
        self.initial_placement = True
        self.start_in_view = start_in_view
        self._spawn(walk_time, start_in_view)

    @property
    def token(self):
        return self.generation, self.species

    def edges(self, species):
        # Reserve the largest possible parallax displacement, even after a
        # strength/reduced-motion change, so a replacement cannot be seen.
        guard = 3.5 * self.extents[species][4]
        return self.bounds[0] - guard, self.bounds[1] + guard

    def _position_at_entry(self, species):
        left, _ = self.edges(species)
        return left - self.extents[species][2] - 1

    def _position_in_view(self, species):
        left, right = self.bounds
        rear, _, nose, _, _ = self.extents[species]
        spare = right - left - (nose - rear)
        # Fit the whole encounter when possible. Narrow views retain the leader,
        # with followers naturally entering from the left rather than resizing.
        return left - rear + .08 * spare if spare >= 0 else right - nose - 1

    def _spawn(self, walk_time, in_view=False):
        previous = self.species
        if not self.pool:
            self.species = None
            return
        choices = tuple(species for species in self.pool if species != previous) or self.pool
        self.species = self.rng.choice(choices)
        self.generation += 1
        self.born = walk_time
        # A new animal starts walking, not already asleep just outside the edge.
        self.phase = self.rng.uniform(0, math.pi)
        self.start_x = (self._position_in_view(self.species)
                        if in_view else self._position_at_entry(self.species))

    def set_viewport(self, bounds, walk_time):
        if bounds != self.bounds:
            self.bounds = bounds
            self.bounds_changed_at = walk_time
        if self.initial_placement:
            if self.species is not None:
                self.start_x = (self._position_in_view(self.species)
                                if self.start_in_view else self._position_at_entry(self.species))
            self.initial_placement = False

    def change_pool(self, pool, walk_time, extents):
        self.pool = tuple(pool)
        if extents != self.extents:
            self.extents = extents
            self.bounds_changed_at = walk_time
        if self.species not in self.pool:
            self._spawn(walk_time)
            self.initial_placement = False

    def current(self, walk_time):
        if self.species is None:
            return None
        age = max(0.0, walk_time - self.born)
        travel = walking_distance(age, self.phase) - walking_distance(0, self.phase)
        return {'species': self.species, 'generation': self.generation,
                'age': age, 'phase': self.phase, 'x': self.start_x + travel}

    def advance(self, walk_time):
        while self.species is not None:
            _, right = self.edges(self.species)
            exit_x = right - self.extents[self.species][0] + 1
            distance = max(0.0, exit_x - self.start_x)
            age_at_exit = walking_time(walking_distance(0, self.phase) + distance, self.phase)
            # A narrower resized viewport can make an animal offscreen now;
            # never backdate that departure and invent missed past visitors.
            departure = max(self.born + age_at_exit, self.bounds_changed_at)
            # Arrival may coincide with a feeding stop: retire at that time,
            # not six seconds later when distance finally increases again.
            if walk_time < departure:
                break
            self._spawn(departure)
            self.initial_placement = False
