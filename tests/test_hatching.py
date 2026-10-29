import copy
from dataclasses import replace
from fractions import Fraction
import math
from pathlib import Path
import random
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from cast import Cast, cast_groups
from configuration import settings
from engine import ACTOR_NAMES, World
from hatching import (SECOND, YOUNG_EXTENTS, YOUNG_HEIGHT,
                      NestHatching, egg_offsets, young_brachiosaurus_bounds)
from layout import generate_layout

YOUNG = 'brachiosaurus:young'
VIEW = (23, 0, 123, 60)


def nest_settings(maximum=2):
    return settings({'animals': {key: False for key in settings()['animals']},
                     'population': {'maxVisible': maximum},
                     'motion': {'speed': 1, 'parallaxStrength': 0}})


class HatchingLifecycle(unittest.TestCase):
    def controller(self, seed=17, nest=True):
        layout = generate_layout(seed, {})
        return NestHatching(layout.nest if nest else None,
                            layout.hatching_seed, layout.hatching_phase)

    def arrive(self, event, rate=1):
        event.advance(event.deadline, event.walk_ns +
                      (event.deadline - event.elapsed_ns) * rate)
        self.assertIsNotNone(event.current())

    def age(self, event, seconds):
        target = event.born + Fraction(str(seconds)) * SECOND
        event.advance(event.elapsed_ns + target - event.walk_ns, target)
        return event.current()

    def test_active_minute_cadence_and_one_recurrent_generation(self):
        for seed in (0, 1, 17, 2026):
            event = self.controller(seed)
            previous = Fraction(0)
            for generation in range(6):
                deadline = event.deadline
                self.assertGreaterEqual(deadline - previous, 480 * SECOND)
                self.assertLessEqual(deadline - previous, 900 * SECOND)
                event.advance(deadline - 1, deadline - 1)
                self.assertIsNone(event.current())
                event.advance(deadline, deadline)
                pose = event.current()
                self.assertEqual(pose['generation'], generation)
                self.assertEqual(pose['state'], 'wobbling')
                self.assertEqual((pose['wobble'], pose['crack'], pose['emerge'], pose['reset']),
                                 (0, 0, 0, 0))
                self.age(event, 33)
                self.assertIsNone(event.current())
                previous = deadline

    def test_budget_disabled_and_busy_skips_do_not_change_future_deadlines(self):
        accepted, blocked, disabled, busy = (self.controller() for _ in range(4))
        disabled.set_nest(None)
        for _ in range(5):
            deadline = accepted.deadline
            accepted.advance(deadline, deadline)
            blocked.advance(deadline, deadline, can_start=False)
            disabled.advance(deadline, deadline)
            busy.advance(deadline, Fraction(0))
            self.assertEqual({item.deadline for item in (accepted, blocked, disabled, busy)},
                             {accepted.deadline})
            self.assertIsNone(blocked.current())
            self.assertIsNone(disabled.current())
        self.assertEqual(busy.generation, 0)
        self.assertEqual(busy.current()['state'], 'wobbling')
        busy.cancel()
        disabled.set_nest(accepted.nest)
        for item in (busy, disabled, blocked):
            item.advance(item.elapsed_ns + SECOND, item.walk_ns + SECOND)
            self.assertIsNone(item.current())
            self.assertEqual(item.deadline, accepted.deadline)

    def test_chronological_replay_and_partitioned_accumulated_rates(self):
        results = []
        for quantum in (None, 17 * SECOND, SECOND // 7):
            event = self.controller()
            for duration, rate in ((800 * SECOND, Fraction(1, 50)),
                                   (1100 * SECOND, Fraction(3, 2)),
                                   (77 * SECOND, Fraction(1, 2))):
                remaining = duration
                while remaining:
                    delta = remaining if quantum is None else min(remaining, quantum)
                    event.advance(event.elapsed_ns + delta, event.walk_ns + delta * rate)
                    remaining -= delta
            results.append((event.current(), event.deadline, event.generation,
                            event.elapsed_ns, event.walk_ns))
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0], results[2])

    def test_stages_rigid_emergence_monotone_land_path_and_parent_cover_target(self):
        event = self.controller()
        self.arrive(event)
        states = {0: 'wobbling', 4: 'cracking', 7: 'hatching',
                  11: 'toddling', 29: 'settling'}
        for age, state in states.items():
            self.assertEqual(self.age(event, age)['state'], state)
        event = self.controller()
        self.arrive(event)
        emergence = []
        for age in (7, 8, 9, 10, 11):
            pose = self.age(event, age)
            emergence.append(pose['foot_y'])
            self.assertAlmostEqual(pose['foot_y'],
                                   event.nest.y + YOUNG_HEIGHT * (1 - pose['emerge']))
            bounds = young_brachiosaurus_bounds(pose)
            self.assertAlmostEqual(bounds[2] - bounds[0], YOUNG_EXTENTS[2] - YOUNG_EXTENTS[0])
            self.assertAlmostEqual(bounds[3] - bounds[1], YOUNG_EXTENTS[3] - YOUNG_EXTENTS[1])
        self.assertEqual(emergence, sorted(emergence, reverse=True))
        start = event.current()
        self.assertEqual((start['x'], start['foot_y'], start['depth']),
                         (start['egg_x'], event.nest.y, .8))
        path = [self.age(event, age) for age in range(11, 30)]
        self.assertEqual([p['x'] for p in path], sorted(p['x'] for p in path))
        self.assertTrue(all(p['foot_y'] > 48 for p in path))
        distance = math.hypot(69 - start['x'], 48.6 - start['foot_y'])
        self.assertAlmostEqual(path[-1]['phase'] - path[0]['phase'], distance * 2.4)
        final = path[-1]
        self.assertEqual((final['x'], final['foot_y'], final['depth']), (69, 48.6, .39))
        left, top, right, bottom, _ = young_brachiosaurus_bounds(final)
        self.assertGreater(left, 60)
        self.assertLess(right, 82)
        self.assertGreater(top, 39)
        self.assertLess(bottom, 50)

    def test_endpoints_and_reset_are_continuous_without_replacing_the_clutch(self):
        for boundary in (4, 7, 11, 29, 33):
            event = self.controller()
            self.arrive(event)
            before = self.age(event, Fraction(boundary) - Fraction(1, 1_000_000))
            after = self.age(event, boundary)
            self.assertEqual(len(egg_offsets(event.nest)), event.nest.eggs)
            if boundary == 33:
                self.assertGreater(before['reset'], .999999)
                self.assertEqual(before['emerge'], 1)
                self.assertIsNone(after)
            else:
                for key in ('x', 'foot_y', 'depth', 'wobble', 'crack', 'emerge', 'reset', 'phase', 'stride'):
                    self.assertAlmostEqual(before[key], after[key], places=5)
        event = self.controller()
        self.arrive(event)
        self.assertEqual(self.age(event, 29)['reset'], 0)
        self.assertAlmostEqual(self.age(event, 31)['reset'], .5)
        first_slot = event.egg_index
        self.age(event, 33)
        self.arrive(event)
        self.assertNotEqual(first_slot, event.egg_index)

    def test_calm_attenuates_only_wobble_and_snapshot_calls_are_pure(self):
        event = self.controller()
        self.arrive(event)
        self.age(event, 1)
        before = event.rng.getstate(), event.deadline, event.walk_ns
        normal = event.current(reaction=.7)
        calm = event.current(reaction=.7, calm=True)
        self.assertAlmostEqual(calm['wobble'], normal['wobble'] * .18)
        self.assertEqual(calm | {'wobble': normal['wobble']}, normal)
        self.assertEqual(before, (event.rng.getstate(), event.deadline, event.walk_ns))
        self.age(event, 9)
        self.assertEqual(event.current(), event.current(calm=True))

    def test_visibility_only_gates_future_events_and_resize_never_moves_live_pose(self):
        event = self.controller()
        event.set_viewport((100, 0, 120, 60))
        first = event.deadline
        event.advance(first, first)
        self.assertIsNone(event.current())
        event.set_viewport(VIEW)
        self.assertIsNone(event.current())
        self.arrive(event)
        pose = self.age(event, 17)
        deadline = event.deadline
        event.set_viewport((0, 0, 10, 20))
        self.assertEqual(event.current(), pose)
        self.assertEqual(event.deadline, deadline)
        event.set_nest(None)
        self.assertIsNone(event.current())
        event.set_nest(generate_layout(17, {}).nest)
        self.assertIsNone(event.current())
        self.assertEqual(event.deadline, deadline)

    def test_nest_must_intersect_the_actual_viewport_for_admission(self):
        for intersects in (False, True):
            event = self.controller()
            edge = event.nest.x + event.nest.radius
            event.set_viewport((edge + (-.01 if intersects else .01), 0, 123, 60))
            event.advance(event.deadline, event.deadline)
            self.assertEqual(event.current() is not None, intersects)

    def test_interval_rng_is_local_and_recurrence_has_constant_storage(self):
        state = random.getstate()
        event = self.controller()
        event.advance(1_000_000 * SECOND, 1_000_000 * SECOND)
        self.assertEqual(random.getstate(), state)
        self.assertGreater(event.deadline, event.elapsed_ns)
        self.assertGreater(event.generation, 100)
        self.assertFalse(any(isinstance(value, (list, dict, set)) for value in vars(event).values()))
        nest = event.nest
        self.assertEqual(egg_offsets(replace(nest, eggs=3)), (-.9, 0, .9))
        self.assertEqual(egg_offsets(replace(nest, eggs=4)), (-1.2, -.4, .4, 1.2))


class HatchingWorld(unittest.TestCase):
    def advance(self, world, duration, fps=4):
        quantum = SECOND // fps
        while duration:
            delta = min(duration, quantum)
            world.advance(delta)
            duration -= delta

    def arrival_world(self, maximum=2, config=None):
        config = nest_settings(maximum) if config is None else config
        first = World(config, visitor_seed=7).hatching.deadline
        world = World(config, first - SECOND, visitor_seed=7)
        world.set_viewport(VIEW)
        return world

    def test_complete_event_reserves_exactly_one_seat_from_wobble_to_reset(self):
        world = self.arrival_world()
        self.assertEqual(ACTOR_NAMES[YOUNG], 'Young Brachiosaurus')
        self.assertFalse(world.react(YOUNG))
        self.advance(world, SECOND)
        self.assertEqual(world.snapshot()['hatching']['state'], 'wobbling')
        self.assertEqual(world.cast.members, ('brachiosaurus', YOUNG))
        self.assertFalse(world.react(YOUNG))
        self.assertFalse(world.spawn_water_jump(30, 44))
        self.advance(world, 8 * SECOND)
        self.assertTrue(world.react(YOUNG))
        self.assertFalse(world.react(YOUNG))
        self.advance(world, 24 * SECOND)
        self.assertEqual(world.snapshot()['hatching']['state'], 'settling')
        self.assertIn(YOUNG, world.cast.members)
        self.advance(world, SECOND)
        self.assertIsNone(world.snapshot()['hatching'])
        self.assertNotIn(YOUNG, world.cast.members)
        self.assertNotIn(YOUNG, world.reactions)
        self.assertFalse(world.react(YOUNG))

    def test_cap_release_and_nest_off_cancel_without_mid_event_readmission(self):
        for setting in ('cap', 'nest'):
            world = self.arrival_world()
            self.advance(world, 9 * SECOND)
            self.assertTrue(world.react(YOUNG))
            generation = world.hatching.generation
            deadline = world.hatching.deadline
            config = copy.deepcopy(world.config)
            if setting == 'cap':
                config['population']['maxVisible'] = 1
            else:
                config['scenery']['nestEnabled'] = False
            world.reconfigure(config)
            self.assertIsNone(world.snapshot()['hatching'])
            self.assertNotIn(YOUNG, world.reactions)
            self.assertNotIn(YOUNG, world.cast.members)
            self.assertFalse(world.react(YOUNG))
            config['population']['maxVisible'] = 2
            config['scenery']['nestEnabled'] = True
            world.reconfigure(config)
            self.assertIsNone(world.snapshot()['hatching'])
            self.assertEqual(world.hatching.deadline, deadline)
            self.advance(world, deadline - world.elapsed_ns)
            self.assertEqual(world.hatching.generation, generation + 1)
            self.assertIn(YOUNG, world.cast.members)
            self.assertNotIn(YOUNG, world.reactions)
            self.advance(world, 8 * SECOND)
            self.assertTrue(world.react(YOUNG))

    def test_zero_capacity_and_incumbent_jump_never_get_preempted(self):
        blocked = self.arrival_world(maximum=1)
        free = self.arrival_world()
        incumbent = self.arrival_world()
        self.assertTrue(incumbent.spawn_water_jump(30, 44))
        for world in (blocked, free, incumbent):
            self.advance(world, SECOND)
        self.assertIsNone(blocked.snapshot()['hatching'])
        self.assertIsNone(incumbent.snapshot()['hatching'])
        self.assertIn('water_jump', incumbent.cast.members)
        self.assertIn(YOUNG, free.cast.members)
        self.assertEqual({w.hatching.deadline for w in (blocked, free, incumbent)},
                         {free.hatching.deadline})
        self.advance(incumbent, 3 * SECOND)
        self.assertIsNone(incumbent.snapshot()['hatching'])

    def test_cast_holds_incumbents_and_gives_young_priority_over_new_arrivals(self):
        world = self.arrival_world(maximum=3)
        self.advance(world, SECOND)
        groups = cast_groups(world.snapshot(), world.config, VIEW)
        young = next(group for group in groups if group['key'] == YOUNG)
        newcomer = dict(key='newcomer', token=0, minimum=1, active=True, entry=True,
                        members=({'id': 'newcomer', 'bounds': (40, 40, 50, 50, .5)},))
        cast = Cast()
        cast.update([young, newcomer], 2, VIEW)
        self.assertEqual(cast.members, ('brachiosaurus', YOUNG))
        cast.update([young, newcomer], 1, VIEW)
        cast.update([young, newcomer], 2, VIEW, refresh=True)
        self.assertNotIn(YOUNG, cast.members)
        cast = Cast()
        cast.update([newcomer], 2, VIEW)
        cast.update([young, newcomer], 2, VIEW)
        self.assertEqual(cast.members, ('brachiosaurus', 'newcomer'))

    def test_history_never_invents_past_budget_and_diagnostics_use_real_admission(self):
        live = self.arrival_world()
        self.advance(live, 10 * SECOND)
        replay = World(live.config, live.elapsed_ns, visitor_seed=7)
        replay.set_viewport(VIEW)
        self.assertIsNone(replay.snapshot()['hatching'])
        self.assertNotIn(YOUNG, replay.cast.members)
        self.assertIsNotNone(live.snapshot()['hatching'])
        self.assertEqual(replay.hatching.deadline, live.hatching.deadline)

    def test_partitioned_frames_pause_and_speed_changes_preserve_walk_history(self):
        results = []
        for fps in (15, 60, 144):
            world = self.arrival_world()
            self.advance(world, 2 * SECOND, fps)
            before = world.snapshot()['hatching']
            clocks = world.elapsed_ns, world._walk_ns, world.hatching.deadline
            world.paused = True
            world.advance(250_000_000)
            self.assertEqual(world.snapshot()['hatching'], before)
            self.assertEqual((world.elapsed_ns, world._walk_ns, world.hatching.deadline), clocks)
            world.paused = False
            config = copy.deepcopy(world.config)
            config['motion']['speed'] = .5
            world.reconfigure(config)
            self.assertEqual(world.snapshot()['hatching'], before)
            self.advance(world, 8 * SECOND, fps)
            config['motion']['speed'] = 2
            config['motion']['reducedMotion'] = True
            world.reconfigure(config)
            self.advance(world, 9 * SECOND, fps)
            results.append((world.snapshot()['hatching'], world._walk_ns,
                            world.hatching.deadline, world.cast.members))
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0], results[2])
        self.assertEqual(results[0][0]['state'], 'toddling')

    def test_scenery_density_preset_resize_keep_pose_but_seed_resets(self):
        world = self.arrival_world()
        self.advance(world, 16 * SECOND)
        controller = world.hatching
        before = world.snapshot()['hatching']
        config = copy.deepcopy(world.config)
        config['scenery']['treeDensity'] = 0
        config['scenery']['flowerDensity'] = 2
        config['preset'] = 'dusk'
        world.reconfigure(config)
        self.assertIs(world.hatching, controller)
        self.assertEqual(world.snapshot()['hatching'], before)
        world.set_viewport((90, 0, 110, 60))
        self.assertEqual(world.snapshot()['hatching'], before)
        self.assertIn(YOUNG, world.cast.members)
        config['seed'] += 1
        world.reconfigure(config)
        self.assertIsNot(world.hatching, controller)
        self.assertIsNone(world.snapshot()['hatching'])
        self.assertNotIn(YOUNG, world.cast.members)
        self.assertGreater(world.hatching.deadline, world.elapsed_ns)

    def test_hatching_activity_does_not_perturb_other_event_or_layout_streams(self):
        first = self.arrival_world(maximum=128)
        second = self.arrival_world(maximum=128)
        second.hatching.set_nest(None)
        self.advance(first, 18 * SECOND)
        self.advance(second, 18 * SECOND)
        self.assertEqual(first.layout, second.layout)
        self.assertEqual(first.hatching.deadline, second.hatching.deadline)
        self.assertEqual(first.diplodocus.rng.getstate(), second.diplodocus.rng.getstate())
        self.assertEqual(first.pteranodon_flocks.rng.getstate(), second.pteranodon_flocks.rng.getstate())
        self.assertEqual(first._routes._records, second._routes._records)
        self.assertEqual(first.snapshot() | {'hatching': None, 'admitted': ()},
                         second.snapshot() | {'hatching': None, 'admitted': ()})


if __name__ == '__main__':
    unittest.main()
