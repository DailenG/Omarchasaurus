import copy
from pathlib import Path
import random
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from cast import Cast, cast_groups
from configuration import settings
from canvas import Canvas
from engine import World
from character_art import visible_cast_members
from population import (triceratops_extents, triceratops_poses,
                        walking_distance, walking_time)

SECOND = 1_000_000_000


class TriceratopsBehavior(unittest.TestCase):
    def config(self, limit=3, random_visitors=False):
        return settings({
            'animals': {name: name == 'triceratopsEnabled'
                        for name in settings()['animals']},
            'population': {'maxVisible': limit, 'randomVisitors': random_visitors},
            'motion': {'speed': 1, 'reducedMotion': False, 'parallaxStrength': 0},
        })

    def poses(self, seconds, phase=0):
        return triceratops_poses(seconds, phase, 0, seconds, 1.2, 0, 0)

    def advance(self, world, nanoseconds):
        while nanoseconds > 0:
            delta = min(nanoseconds, 250_000_000)
            world.advance(delta)
            nanoseconds -= delta

    def test_following_is_forward_only_and_stops_and_cycle_boundaries_are_continuous(self):
        previous = self.poses(0)
        for index in range(1, 4801):
            pair = self.poses(index / 100)
            self.assertGreaterEqual(pair[0]['x'], previous[0]['x'] - 1e-10)
            self.assertGreaterEqual(pair[1]['x'], previous[1]['x'] - 1e-10)
            self.assertGreaterEqual(pair[1]['x'] - 15 * pair[1]['scale'],
                                    pair[0]['x'] + triceratops_extents(2)[0])
            self.assertLess(pair[1]['x'] + 8 * pair[1]['scale'], pair[0]['x'] - 9)
            previous = pair
        for boundary in (12, 18, 24):
            before, at, after = (self.poses(boundary + delta)[1]
                                 for delta in (-1e-5, 0, 1e-5))
            left_speed = (at['x'] - before['x']) / 1e-5
            right_speed = (after['x'] - at['x']) / 1e-5
            self.assertAlmostEqual(left_speed, right_speed, delta=1e-4)
        stopped = [self.poses(seconds) for seconds in (18, 19, 21, 23, 24)]
        for pair in stopped:
            self.assertEqual(pair[0]['x'], stopped[0][0]['x'])
            self.assertEqual(pair[1]['x'], stopped[0][1]['x'])
            self.assertEqual(pair[1]['stride'], 0)
        self.assertEqual(stopped[2][1]['nuzzle'], 1)
        self.assertEqual(stopped[-1][1]['nuzzle'], 0)

    def test_calf_wraps_with_parent_but_gait_distance_does_not_reset(self):
        world = World(self.config())
        pose = world.snapshot()
        previous = pose['herbivores']['triceratops'], pose['triceratops_calf']
        wrapped = False
        for _ in range(2200):
            world.advance(250_000_000)
            pose = world.snapshot()
            pair = pose['herbivores']['triceratops'], pose['triceratops_calf']
            if pair[0]['x'] < previous[0]['x'] - 500:
                wrapped = True
                self.assertLess(pair[1]['x'], previous[1]['x'] - 500)
                self.assertGreaterEqual(pair[1]['phase'], previous[1]['phase'])
                self.assertAlmostEqual(pair[0]['x'] - previous[0]['x'],
                                       pair[1]['x'] - previous[1]['x'], delta=.6)
            self.assertGreaterEqual(pair[1]['x'] - 15 * pair[1]['scale'],
                                    pair[0]['x'] + triceratops_extents(2)[0])
            self.assertLess(pair[1]['x'] + 8 * pair[1]['scale'], pair[0]['x'] - 9)
            previous = pair
        self.assertTrue(wrapped, 'The route must actually cross its common wrap')

    def test_frame_rates_pause_and_motion_reload_preserve_accumulated_pair_history(self):
        outcomes = []
        for fps in (4, 15, 60):
            world = World(self.config())
            for frame in range(35 * fps):
                world.advance((frame + 1) * SECOND // fps - frame * SECOND // fps)
            outcomes.append((world.snapshot()['herbivores']['triceratops'],
                             world.snapshot()['triceratops_calf']))
        self.assertEqual(outcomes[0], outcomes[1])
        self.assertEqual(outcomes[0], outcomes[2])
        world.paused = True
        self.advance(world, 7 * SECOND)
        frozen = world.snapshot()
        changed = copy.deepcopy(world.config)
        changed['motion'].update(speed=.5, reducedMotion=True)
        world.reconfigure(changed)
        self.assertEqual(world.snapshot()['triceratops_calf'], frozen['triceratops_calf'])
        world.paused = False
        self.advance(world, SECOND)
        replay = World(self.config(), elapsed_ns=35 * SECOND + SECOND // 4).snapshot()
        for key in ('x', 'phase', 'stride', 'nuzzle', 'calf_near'):
            self.assertEqual(world.snapshot()['triceratops_calf'][key], replay['triceratops_calf'][key])

    def test_global_ceiling_prefers_parent_and_jump_never_evicts_a_pair(self):
        world = World(self.config(), elapsed_ns=110 * SECOND)
        frame = Canvas(320, 96)
        for limit, expected in ((1, ('brachiosaurus',)),
                                (2, ('brachiosaurus', 'triceratops')),
                                (3, ('brachiosaurus', 'triceratops', 'triceratops:calf'))):
            config = self.config(limit)
            self.assertEqual(visible_cast_members(frame, world.snapshot(), config), expected)
        self.assertFalse(world.spawn_water_jump(40, 44))
        world.reconfigure(self.config(4))
        self.assertTrue(world.spawn_water_jump(40, 44))
        self.assertEqual(visible_cast_members(frame, world.snapshot(), self.config(3)),
                         ('brachiosaurus', 'water_jump', 'triceratops'))
        self.assertEqual(visible_cast_members(frame, world.snapshot(), self.config(4)),
                         ('brachiosaurus', 'water_jump', 'triceratops', 'triceratops:calf'))
        snapshot = World(self.config()).snapshot()
        snapshot['admitted'] = ('brachiosaurus', 'triceratops', 'triceratops:calf')
        right = frame.center + frame.visible_width / 2
        snapshot['herbivores']['triceratops']['x'] = right + 16
        snapshot['triceratops_calf']['x'] = right - 10
        self.assertEqual(visible_cast_members(frame, snapshot, self.config(2)), ('brachiosaurus',))
        self.assertEqual(visible_cast_members(frame, snapshot, self.config(3)),
                         ('brachiosaurus', 'triceratops:calf'))

    def test_offscreen_random_pair_reserves_entry_slots_unlike_an_unseen_ordinary_pair(self):
        world = World(self.config())
        frame = Canvas(320, 96)
        snapshot = world.snapshot()
        snapshot['herbivores']['triceratops']['x'] = -100
        snapshot['triceratops_calf']['x'] = -126
        snapshot['pteranodons'] = tuple(dict(id=f'pteranodon:{i}', x=60+i*10, y=15,
                                           tip_y=13, span=4, depth=.1, bank=0) for i in range(2))
        config = self.config()
        config['animals']['pteranodonEnabled'] = True
        view = (frame.center-frame.visible_width/2, frame.origin_y,
                frame.center+frame.visible_width/2, 60)
        snapshot['admitted'] = Cast().update(cast_groups(snapshot, config, view), 3, view, initial=True)
        self.assertEqual(visible_cast_members(frame, snapshot, config),
                         ('brachiosaurus', 'pteranodon:0', 'pteranodon:1'))
        config['population']['randomVisitors'] = True
        snapshot['visitor'] = dict(species='triceratops', generation=0)
        snapshot['admitted'] = Cast().update(cast_groups(snapshot, config, view), 3, view, initial=True)
        self.assertEqual(visible_cast_members(frame, snapshot, config), ('brachiosaurus',))

    def test_random_pair_initial_fit_full_rear_exit_reentry_and_fresh_reactions(self):
        world = World(self.config(random_visitors=True), visitor_seed=17)
        frame = Canvas(320, 96)
        world.set_viewport(frame.world_bounds)
        visitor = dict(world.snapshot()['visitor'])
        left, right = world._visitor_bounds
        rear, _, nose, _, depth = triceratops_extents(2)
        self.assertGreaterEqual(visitor['x'] + rear, left)
        self.assertLessEqual(visitor['x'] + nose, right)
        origin = world.visitors.start_x
        exit_x = right + 3.5 * depth - rear + 1
        exit_time = walking_time(walking_distance(0, visitor['phase']) + exit_x - origin,
                                 visitor['phase'])
        self.advance(world, int((exit_time - .5) * SECOND))
        self.assertEqual(world.snapshot()['visitor']['generation'], visitor['generation'])
        self.assertTrue(world.react('triceratops'))
        self.assertTrue(world.react('triceratops:calf'))
        self.advance(world, SECOND)
        replacement = world.snapshot()
        self.assertGreater(replacement['visitor']['generation'], visitor['generation'])
        old_x_at_exit = origin + walking_distance(world.visitors.born, visitor['phase']) - walking_distance(0, visitor['phase'])
        self.assertGreaterEqual(old_x_at_exit + rear, right + 3.5 * depth)
        self.assertLess(replacement['herbivores']['triceratops']['x'] + nose, left)
        self.assertEqual(replacement['triceratops_calf']['reaction'], 0)
        self.assertTrue(world.react('triceratops:calf'))
        self.advance(world, 40 * SECOND)
        self.assertIn('triceratops:calf', visible_cast_members(frame, world.snapshot(), world.config))

    def test_widening_extends_pair_exit_and_narrowing_with_adult_only_cap_is_not_backdated(self):
        world = World(self.config(random_visitors=True), visitor_seed=17)
        narrow = Canvas(320, 96)
        world.set_viewport(narrow.world_bounds)
        first = world.snapshot()['visitor']
        rear, _, _, _, depth = triceratops_extents(2)
        exit_x = world._visitor_bounds[1] + 3.5 * depth - rear + 1
        old_exit = walking_time(walking_distance(0, first['phase'])
                                + exit_x - world.visitors.start_x, first['phase'])
        world.set_viewport(Canvas(500, 60).world_bounds)
        self.advance(world, int((old_exit + .5) * SECOND))
        self.assertEqual(world.snapshot()['visitor']['generation'], first['generation'])
        frozen = world.snapshot()
        world.paused = True
        world.reconfigure(self.config(limit=2, random_visitors=True))
        world.set_viewport(narrow.world_bounds)
        self.assertEqual(world.snapshot()['triceratops_calf'], frozen['triceratops_calf'])
        self.assertEqual(world.snapshot()['herbivores']['triceratops'],
                         frozen['herbivores']['triceratops'])
        now = world.elapsed_ns
        world.paused = False
        world.advance(250_000_000)
        self.assertGreater(world.snapshot()['visitor']['generation'], first['generation'])
        self.assertLessEqual(world.snapshot()['visitor']['age'], .250001)
        self.assertGreaterEqual(world.visitors.born, now / SECOND)
        self.advance(world, 15 * SECOND)
        self.assertIn('triceratops', visible_cast_members(narrow, world.snapshot(), world.config))
        self.assertNotIn('triceratops:calf', visible_cast_members(narrow, world.snapshot(), world.config))

    def test_live_cap_disable_density_and_resize_preserve_both_poses_and_private_clicks(self):
        world = World(self.config(), elapsed_ns=110 * SECOND)
        self.assertTrue(world.react('triceratops:calf'))
        self.advance(world, SECOND)
        self.assertGreater(world.snapshot()['triceratops_calf']['reaction'], .9)
        self.assertEqual(world.snapshot()['herbivores']['triceratops']['reaction'], 0)
        self.assertTrue(world.react('triceratops'))
        world.paused = True
        before = world.snapshot()
        changed = copy.deepcopy(world.config)
        changed['population']['maxVisible'] = 2
        changed['scenery']['cloudDensity'] = 2
        world.reconfigure(changed)
        world.set_viewport(Canvas(500, 60).world_bounds)
        self.assertEqual(world.snapshot()['triceratops_calf'], before['triceratops_calf'])
        self.assertEqual(world.snapshot()['herbivores']['triceratops'], before['herbivores']['triceratops'])
        self.assertFalse(world.react('triceratops:calf'))
        changed['animals']['triceratopsEnabled'] = False
        world.reconfigure(changed)
        self.assertFalse(world.react('triceratops'))
        self.assertFalse(world.react('triceratops:calf'))
        changed['animals']['triceratopsEnabled'] = True
        changed['population']['maxVisible'] = 3
        world.reconfigure(changed)
        self.assertEqual(world.snapshot()['triceratops_calf'], before['triceratops_calf'])

    def test_calf_seed_namespace_is_independent_of_other_scenery_and_global_rng(self):
        rng = random.getstate()
        world = World(self.config())
        phase = world.layout.triceratops_calf_phase
        changed = copy.deepcopy(world.config)
        changed['scenery']['treeDensity'] = 2
        world.reconfigure(changed)
        self.assertEqual(world.layout.triceratops_calf_phase, phase)
        changed['seed'] += 1
        world.reconfigure(changed)
        self.assertNotEqual(world.layout.triceratops_calf_phase, phase)
        self.assertEqual(random.getstate(), rng)


if __name__ == '__main__':
    unittest.main()
