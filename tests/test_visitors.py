import math
from pathlib import Path
import random
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from configuration import settings
from canvas import Canvas
from engine import World
from character_art import draw_scene, visible_cast_members
from population import GROUND_EXTENTS, walking_distance, walking_time
from visitors import RandomVisitors


class VisitorBehavior(unittest.TestCase):
    def world(self, pool=tuple(GROUND_EXTENTS), seed=17, limit=8, swimmer=False):
        config = settings({'animals': {species + 'Enabled': species in pool for species in GROUND_EXTENTS}
                           | {'plesiosaurusEnabled': swimmer, 'diplodocusEnabled': False},
                           'population': {'randomVisitors': True, 'maxVisible': limit}})
        world = World(config, visitor_seed=seed)
        world.set_viewport(Canvas(320, 96).world_bounds)
        return world

    def advance(self, world, seconds):
        remaining = round(seconds * 1_000_000_000)
        while remaining:
            delta = min(250_000_000, remaining)
            world.advance(delta)
            remaining -= delta

    def frame(self, world, width=320, height=96):
        pose = world.snapshot()
        canvas = Canvas(width, height, pose['camera'])
        draw_scene(canvas, pose, world.config)
        return canvas

    def has_species(self, canvas, species):
        return any(owner == species or (owner and owner.startswith(species + ':'))
                   for row in canvas.owners for owner in row)

    def test_distance_inverse_handles_easing_stops_and_multiple_cycles(self):
        for phase in (0, .5, 2, math.pi):
            for time in (1, 8, 16.8, 17.5, 18, 19, 23, 24.5, 41.5, 80):
                distance = walking_distance(time, phase)
                first_arrival = walking_time(distance, phase)
                self.assertLessEqual(first_arrival, time + 1e-8)
                self.assertAlmostEqual(walking_distance(first_arrival, phase), distance, places=8)
        self.assertAlmostEqual(walking_time(21.6, 0), 18)
        self.assertAlmostEqual(walking_time(43.2, 0), 42)

    def test_departure_at_the_start_of_a_feeding_stop_does_not_delay_or_age_the_replacement(self):
        visitors = RandomVisitors(42, 17, ('triceratops',), 0, (23, 123), True, GROUND_EXTENTS)
        visitors.set_viewport((23, 123), 0)
        stop = 18 + 5 * 24 - visitors.phase * 24 / math.tau
        exit_x = (visitors.start_x + walking_distance(stop, visitors.phase)
                  - walking_distance(0, visitors.phase))
        left_extent, _, _, _, depth = GROUND_EXTENTS['triceratops']
        right = exit_x + left_extent - 1 - 3.5 * depth
        visitors.set_viewport((23, right), 0)
        visitors.advance(stop + .1)
        replacement = visitors.current(stop + .1)
        self.assertEqual(replacement['generation'], 1)
        self.assertLess(replacement['age'], .101)
        self.assertLess(replacement['x'] + GROUND_EXTENTS['triceratops'][2], 23)

    def test_session_seed_replays_start_and_sequence_without_touching_layout_or_global_rng(self):
        state = random.getstate()
        a, b = self.world(seed=123), self.world(seed=123)
        different = self.world(seed=456)
        self.assertEqual(a.layout, different.layout)
        outcomes = []
        for world in (a, b, different):
            sequence = []
            for _ in range(12):
                self.advance(world, 60)
                sequence.append(world.snapshot()['visitor'])
            outcomes.append(sequence)
        self.assertEqual(outcomes[0], outcomes[1])
        self.assertNotEqual(outcomes[0], outcomes[2])
        self.assertEqual(random.getstate(), state)
        self.assertEqual({self.world(seed=seed).snapshot()['visitor']['species']
                          for seed in range(32)}, set(GROUND_EXTENTS))

    def test_start_is_visible_and_replacements_only_occur_after_full_exit_then_enter_from_left(self):
        world = self.world()
        current = world.snapshot()['visitor']
        self.assertTrue(self.has_species(self.frame(world), current['species']))
        replacements = 0
        entered_after_replacement = False
        for _ in range(2400):
            before = world.snapshot()['visitor']
            self.advance(world, .25)
            after = world.snapshot()['visitor']
            if after['generation'] != before['generation']:
                replacements += 1
                self.assertNotEqual(after['species'], before['species'])
                _, right = world.visitors.edges(before['species'])
                # Crossing happened within this step, never while its rear was in view.
                self.assertGreater(before['x'] + world.visitors.extents[before['species']][0] + .4, right)
                left, _ = world.visitors.edges(after['species'])
                self.assertLess(after['x'] + world.visitors.extents[after['species']][2], left)
                self.assertFalse(self.has_species(self.frame(world), after['species']))
            elif replacements and not entered_after_replacement and self.frame_if_entering(world, after):
                entered_after_replacement = True
            if replacements >= 2 and entered_after_replacement:
                break
        self.assertGreaterEqual(replacements, 2)
        self.assertTrue(entered_after_replacement)

    def frame_if_entering(self, world, visitor):
        left, _, right, _, _ = world.visitors.extents[visitor['species']]
        if visitor['x'] + right > 25 and visitor['x'] + left < 120:
            return self.has_species(self.frame(world), visitor['species'])
        return False

    def test_single_species_reenters_and_empty_pool_has_no_substitute(self):
        world = self.world(pool=('triceratops',))
        initial = world.snapshot()['visitor']
        for _ in range(1200):
            self.advance(world, .25)
            visitor = world.snapshot()['visitor']
            self.assertEqual(visitor['species'], 'triceratops')
            if visitor['generation'] > initial['generation'] and self.frame_if_entering(world, visitor):
                break
        self.assertGreater(visitor['generation'], initial['generation'])
        self.assertIsNotNone(self.frame(world).bounds('triceratops'))
        empty = self.world(pool=())
        self.advance(empty, 300)
        self.assertIsNone(empty.snapshot()['visitor'])
        selected = visible_cast_members(self.frame(empty), empty.snapshot(), empty.config)
        self.assertFalse({identity.partition(':')[0] for identity in selected} & GROUND_EXTENTS.keys())

    def test_pause_resize_and_unrelated_reload_preserve_an_in_view_visitor(self):
        world = self.world()
        self.advance(world, 20)
        before = world.snapshot()['visitor']
        world.paused = True
        self.advance(world, 5)
        for size in ((500, 40), (80, 80), (320, 96)):
            world.set_viewport(Canvas(*size).world_bounds)
            self.assertEqual(world.snapshot()['visitor'], before)
        config = settings({'animals': {'plesiosaurusEnabled': False},
                           'population': {'randomVisitors': True, 'maxVisible': 2},
                           'scenery': {'flowerDensity': 0}, 'motion': {'reducedMotion': True}})
        world.reconfigure(config)
        self.assertEqual(world.snapshot()['visitor'], before)
        world.paused = False
        self.advance(world, 1)
        self.assertGreaterEqual(world.snapshot()['visitor']['x'], before['x'])

    def test_expanded_viewport_prevents_old_edge_replacement_and_shrinking_does_not_backdate_it(self):
        world = self.world(pool=('trex',))
        self.advance(world, 80)
        before = world.snapshot()['visitor']
        world.set_viewport(Canvas(500, 24).world_bounds)
        self.assertEqual(world.snapshot()['visitor'], before)
        self.advance(world, 100)
        extended = world.snapshot()['visitor']
        self.assertEqual(extended['generation'], before['generation'])
        world.set_viewport(Canvas(80, 80).world_bounds)
        self.assertEqual(world.snapshot()['visitor'], extended)
        self.advance(world, .1)
        replaced = world.snapshot()['visitor']
        self.assertEqual(replaced['generation'], extended['generation'] + 1)
        self.assertLessEqual(replaced['age'], .1 + 1e-8)

    def test_disabling_current_replaces_offscreen_and_changing_future_pool_keeps_current(self):
        world = self.world()
        current = world.snapshot()['visitor']
        remaining = next(species for species in GROUND_EXTENTS if species != current['species'])
        config = settings({'animals': {species + 'Enabled': species in (current['species'], remaining)
                                      for species in GROUND_EXTENTS} | {'plesiosaurusEnabled': False},
                           'population': {'randomVisitors': True}})
        world.reconfigure(config)
        self.assertEqual(world.snapshot()['visitor'], current)
        config['animals'][current['species'] + 'Enabled'] = False
        world.reconfigure(config)
        replacement = world.snapshot()['visitor']
        self.assertEqual(replacement['species'], remaining)
        self.assertFalse(self.has_species(self.frame(world), remaining))
        self.assertFalse(world.react(current['species']))

    def test_ceiling_includes_visitor_flyers_and_lake_and_reserves_the_entry_slot(self):
        for limit in (1, 2, 3, 8, 128):
            world = self.world(limit=limit, swimmer=True)
            for _ in range(4):
                world.spawn_water_jump(20, 44)
                frame = self.frame(world)
                selected = visible_cast_members(frame, world.snapshot(), world.config)
                self.assertLessEqual(len(selected), limit)
                self.assertLessEqual(len({identity.partition(':')[0] for identity in selected}
                                         & GROUND_EXTENTS.keys()), 1)
                self.advance(world, 60)
        world = self.world(pool=('trex',), limit=2)
        for _ in range(800):
            self.advance(world, .25)
            if world.snapshot()['visitor']['generation'] > 0:
                break
        visitor = world.snapshot()['visitor']
        self.assertGreater(visitor['generation'], 0)
        self.assertLess(visitor['x'] + GROUND_EXTENTS['trex'][2], 23)
        self.assertIsNone(self.frame(world).bounds('trex'))
        self.assertEqual(visible_cast_members(self.frame(world), world.snapshot(), world.config), ('brachiosaurus',))

    def test_replacements_are_elapsed_time_not_frame_rate_dependent(self):
        snapshots = []
        for fps in (15, 60, 144):
            world = self.world(seed=88)
            for frame in range(fps * 300):
                world.advance((frame + 1) * 1_000_000_000 // fps - frame * 1_000_000_000 // fps)
            snapshots.append(world.snapshot()['visitor'])
        self.assertGreater(snapshots[0]['generation'], 0)
        for snapshot in snapshots[1:]:
            self.assertEqual(snapshot['species'], snapshots[0]['species'])
            self.assertEqual(snapshot['generation'], snapshots[0]['generation'])
            self.assertAlmostEqual(snapshot['x'], snapshots[0]['x'], places=7)
            self.assertAlmostEqual(snapshot['age'], snapshots[0]['age'], places=7)

    def test_a_new_ankylosaurus_does_not_inherit_a_departed_animals_wake(self):
        world = self.world(pool=('ankylosaurus',))
        for _ in range(1200):
            if world.snapshot()['ankylosaurus']['state'] == 'napping':
                break
            self.advance(world, .25)
        self.assertTrue(world.react('ankylosaurus'))
        old_generation = world.snapshot()['visitor']['generation']
        for _ in range(1600):
            self.advance(world, .25)
            pose = world.snapshot()
            if pose['visitor']['generation'] > old_generation and pose['ankylosaurus']['state'] == 'napping':
                self.assertEqual(pose['ankylosaurus']['sleep'], 1)
                return
        self.fail('replacement Ankylosaurus never reached its own nap')

    def test_regular_roamers_leave_and_return_on_the_existing_routes(self):
        for species in GROUND_EXTENTS:
            # Isolate route returns from budget-driven skipped passes.
            config = settings({
                'animals': {key + 'Enabled': key == species for key in GROUND_EXTENTS}
                | {'plesiosaurusEnabled': False},
                'population': {'maxVisible': 128},
            })
            world = World(config)
            seen = departed = returned = False
            for _ in range(4000):
                self.advance(world, .25)
                if world.tick % 60:
                    continue
                pose = world.snapshot()
                present = any(identity == species or identity.startswith(species + ':')
                              for identity in visible_cast_members(Canvas(320, 96), pose, config))
                if present and departed:
                    returned = True
                    break
                if not present and seen:
                    departed = True
                seen |= present
            self.assertTrue(returned, species)


if __name__ == '__main__':
    unittest.main()
