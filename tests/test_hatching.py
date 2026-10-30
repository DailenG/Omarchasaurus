import copy
from dataclasses import replace
from fractions import Fraction
from pathlib import Path
import random
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from cast import Cast, cast_groups
from configuration import settings
from engine import ACTOR_NAMES, World
from hatching import (DEPARTURE_AT, NEST_DEPTH, SECOND, YOUNG_EXTENTS, YOUNG_HEIGHT,
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

    def test_manual_start_validates_selection_and_never_changes_schedule(self):
        event = self.controller()
        original = event.deadline, event.rng.getstate(), event.elapsed_ns, event.walk_ns
        for invalid in (-1, event.nest.eggs, 1.5, True):
            self.assertFalse(event.start(invalid))
            self.assertIsNone(event.current())
        selected = event.nest.eggs - 1
        self.assertTrue(event.start(selected))
        first = event.current()
        self.assertEqual(first['egg_index'], selected)
        self.assertEqual(first['egg_x'], event.nest.x + egg_offsets(event.nest)[selected])
        self.assertEqual(first['generation'], 0)
        self.assertEqual(first['state'], 'wobbling')
        self.assertEqual(event.born, original[3])
        self.assertFalse(event.start(0))
        self.assertFalse(event.start())
        self.assertEqual(event.current(), first)
        self.assertEqual((event.deadline, event.rng.getstate(),
                          event.elapsed_ns, event.walk_ns), original)
        self.age(event, 120)
        self.assertIsNone(event.current())
        event.advance(event.elapsed_ns + SECOND, event.walk_ns + SECOND)
        self.assertIsNone(event.current())
        self.assertTrue(event.start(0))
        self.assertEqual(event.current()['generation'], 1)
        self.assertEqual(event.current()['egg_index'], 0)
        self.assertEqual((event.deadline, event.rng.getstate()), original[:2])

    def test_manual_start_requires_enabled_visible_nest_without_retiming(self):
        event = self.controller()
        nest = event.nest
        original = event.deadline, event.rng.getstate()
        event.set_nest(None)
        self.assertFalse(event.start())
        event.set_nest(nest)
        event.set_viewport((1000, 0, 1100, 60))
        self.assertFalse(event.start())
        event.set_viewport(VIEW)
        event.advance(13 * SECOND, 3 * SECOND)
        self.assertTrue(event.start())
        self.assertEqual(event.born, 3 * SECOND)
        event.set_nest(None)
        self.assertIsNone(event.current())
        event.set_nest(nest)
        event.advance(14 * SECOND, 4 * SECOND)
        self.assertIsNone(event.current())
        self.assertEqual((event.deadline, event.rng.getstate()), original)

    def test_manual_generations_and_busy_deadlines_leave_automatic_rng_unchanged(self):
        clicked, automatic = self.controller(), self.controller()
        for selected in (0, 1, None):
            self.assertTrue(clicked.start(selected))
            self.age(clicked, 120)
        deadline = clicked.deadline
        clicked.advance(deadline - SECOND, deadline - SECOND)
        self.assertTrue(clicked.start())
        generation = clicked.generation
        clicked.advance(deadline, deadline)
        automatic.advance(deadline, deadline)
        self.assertEqual(clicked.generation, generation)
        self.assertEqual(clicked.current()['state'], 'wobbling')
        self.assertEqual(clicked.deadline, automatic.deadline)
        self.assertEqual(clicked.rng.getstate(), automatic.rng.getstate())
        clicked.advance(automatic.deadline, automatic.deadline)
        automatic.advance(automatic.deadline, automatic.deadline)
        self.assertEqual(clicked.current()['state'], 'wobbling')
        self.assertEqual(clicked.deadline, automatic.deadline)
        self.assertEqual(clicked.rng.getstate(), automatic.rng.getstate())

    def test_scurry_accelerates_smoothly_then_holds_speed_without_changing_rigid_pose(self):
        event = self.controller()
        self.assertTrue(event.start())
        poses = [self.age(event, age) for age in (30, 30.5, 31, 31.5, 32, 33, 34)]
        origin = event.nest.x + 8
        for pose, distance in zip(poses, (0, .5, 2, 4.5, 8, 16, 24)):
            self.assertAlmostEqual(pose['x'], origin + distance)
            self.assertEqual(pose['foot_y'], event.nest.y)
            self.assertEqual(pose['depth'], NEST_DEPTH)
            bounds = young_brachiosaurus_bounds(pose)
            self.assertAlmostEqual(bounds[2] - bounds[0], YOUNG_EXTENTS[2] - YOUNG_EXTENTS[0])
        self.assertEqual(poses[0]['stride'], 0)
        self.assertGreater(poses[2]['stride'], poses[1]['stride'])
        self.assertEqual(poses[-1]['stride'], 1)

    def test_retirement_uses_entire_guarded_footprint_and_analytic_ramp_crossing(self):
        for distance, exit_age in ((2, 31), (80, 41)):
            event = self.controller()
            self.assertTrue(event.start())
            waiting_left = event.nest.x + 8 + YOUNG_EXTENTS[0]
            guard = 4 * NEST_DEPTH + 2
            right = waiting_left + distance - guard
            event.set_viewport((right - 100, 0, right, 60))
            before = self.age(event, Fraction(exit_age) - Fraction(1, 1_000_000))
            self.assertEqual(before['state'], 'scurrying')
            self.assertEqual(before['reset'], 1)
            self.assertLess(young_brachiosaurus_bounds(before)[0], right + guard)
            self.assertFalse(event.start())
            self.age(event, Fraction(exit_age) + Fraction(1, 1_000_000))
            self.assertIsNone(event.current())
        event = self.controller()
        self.assertTrue(event.start())
        right = event.bounds[2]
        age = 30 + 1 + (right + 1 - (event.nest.x + 8)) / 8
        pose = self.age(event, age)
        self.assertGreater(pose['x'], right)
        self.assertLess(young_brachiosaurus_bounds(pose)[0], right + 4 * NEST_DEPTH + 2)
        self.assertFalse(event.start())

    def test_resize_preserves_scurry_position_but_recomputes_retirement(self):
        event = self.controller()
        self.assertTrue(event.start())
        pose = self.age(event, 33)
        deadline = event.deadline
        event.set_viewport((0, 0, 1000, 60))
        self.assertEqual(event.current(), pose)
        later = self.age(event, 100)
        self.assertEqual(later['state'], 'scurrying')
        self.assertGreater(later['x'], VIEW[2] + 4 * NEST_DEPTH + 2 - YOUNG_EXTENTS[0])
        event.set_viewport(VIEW)
        self.assertEqual(event.current(), later)
        event.advance(event.elapsed_ns, event.walk_ns)
        self.assertIsNone(event.current())
        self.assertEqual(event.deadline, deadline)

    def test_reduced_walk_clock_delays_departure_without_delaying_automatic_time(self):
        normal, reduced = self.controller(), self.controller()
        self.assertTrue(normal.start())
        self.assertTrue(reduced.start())
        normal.advance(40 * SECOND, 40 * SECOND)
        reduced.advance(40 * SECOND, 20 * SECOND)
        self.assertEqual(normal.current()['state'], 'scurrying')
        self.assertEqual(reduced.current()['state'], 'lingering')
        reduced.advance(60 * SECOND, DEPARTURE_AT)
        self.assertEqual(reduced.current()['state'], 'scurrying')
        self.assertEqual(reduced.current()['x'], reduced.nest.x + 8)
        normal.advance(120 * SECOND, 120 * SECOND)
        reduced.advance(120 * SECOND, 60 * SECOND)
        self.assertIsNone(normal.current())
        self.assertIsNone(reduced.current())
        self.assertEqual(normal.deadline, reduced.deadline)

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
                self.age(event, 120)
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

    def test_stages_rigid_emergence_and_near_nest_linger(self):
        event = self.controller()
        self.arrive(event)
        states = {0: 'wobbling', 4: 'cracking', 7: 'hatching',
                  11: 'toddling', 17: 'lingering', 30: 'scurrying'}
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
        self.assertTrue(all(p['foot_y'] == event.nest.y for p in path))
        self.assertTrue(all(p['depth'] == NEST_DEPTH for p in path))
        distance = event.nest.x + 8 - start['x']
        self.assertAlmostEqual(path[-1]['phase'] - path[0]['phase'], distance * 2.4)
        self.assertEqual(path[-1]['x'], event.nest.x + 8)
        self.assertTrue(all(p['stride'] == 0 for p in path[6:]))

    def test_endpoints_and_reset_are_continuous_without_replacing_the_clutch(self):
        for boundary in (4, 7, 11, 17, 26, 30, 32):
            event = self.controller()
            self.arrive(event)
            before = self.age(event, Fraction(boundary) - Fraction(1, 10_000_000))
            after = self.age(event, boundary)
            for key in ('x', 'foot_y', 'depth', 'wobble', 'crack', 'emerge', 'reset', 'phase', 'stride'):
                self.assertAlmostEqual(before[key], after[key], places=5)
        event = self.controller()
        self.arrive(event)
        self.assertEqual(self.age(event, 26)['reset'], 0)
        self.assertAlmostEqual(self.age(event, 28)['reset'], .5)
        self.assertEqual(self.age(event, 30)['reset'], 1)
        first_slot = event.egg_index
        slots = egg_offsets(event.nest)
        self.age(event, 120)
        self.assertEqual(egg_offsets(event.nest), slots)
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

    def test_click_selects_nearest_egg_and_reserves_seat_without_advancing_clocks(self):
        world = World(nest_settings(), visitor_seed=7)
        world.set_viewport(VIEW)
        nest = world.layout.nest
        selected = nest.eggs - 1
        clocks = world.elapsed_ns, world._walk_ns, world.hatching.deadline
        rng = world.hatching.rng.getstate()
        world.reactions[YOUNG] = world.tick
        self.assertTrue(world.hatch_egg(nest.x + egg_offsets(nest)[selected] - .05))
        pose = world.snapshot()['hatching']
        self.assertEqual(pose['egg_index'], selected)
        self.assertEqual(pose['generation'], 0)
        self.assertEqual(pose['state'], 'wobbling')
        self.assertEqual(world.cast.members, ('brachiosaurus', YOUNG))
        self.assertNotIn(YOUNG, world.reactions)
        self.assertEqual((world.elapsed_ns, world._walk_ns, world.hatching.deadline), clocks)
        self.assertEqual(world.hatching.rng.getstate(), rng)

    def test_busy_clicks_never_queue_and_departed_baby_allows_one_new_generation(self):
        world = World(nest_settings(), visitor_seed=7)
        world.set_viewport(VIEW)
        nest = world.layout.nest
        offsets = egg_offsets(nest)
        self.assertTrue(world.hatch_egg(nest.x + offsets[0]))
        first = world.snapshot()['hatching']
        deadline, rng = world.hatching.deadline, world.hatching.rng.getstate()
        for _ in range(8):
            self.assertFalse(world.hatch_egg(nest.x + offsets[-1]))
        self.assertEqual(world.snapshot()['hatching'], first)
        self.advance(world, 28 * SECOND)
        refilling = world.snapshot()['hatching']
        self.assertEqual(refilling['reset'], .5)
        self.assertEqual(refilling['state'], 'lingering')
        self.assertGreater(young_brachiosaurus_bounds(refilling)[0], nest.x + nest.radius)
        self.assertFalse(world.hatch_egg(nest.x))
        self.advance(world, 2 * SECOND)
        pose = world.snapshot()['hatching']
        self.assertEqual(pose['reset'], 1)
        self.assertEqual(pose['state'], 'scurrying')
        self.assertFalse(world.hatch_egg(nest.x))
        self.assertIn(YOUNG, world.cast.members)
        self.advance(world, 90 * SECOND)
        self.assertIsNone(world.snapshot()['hatching'])
        self.assertNotIn(YOUNG, world.cast.members)
        self.advance(world, SECOND)
        self.assertIsNone(world.snapshot()['hatching'])
        self.assertTrue(world.hatch_egg(nest.x + offsets[-1]))
        second = world.snapshot()['hatching']
        self.assertEqual(second['generation'], first['generation'] + 1)
        self.assertEqual(second['egg_index'], nest.eggs - 1)
        self.assertEqual(second['state'], 'wobbling')
        self.assertEqual(world.hatching.born, world._walk_ns)
        self.assertEqual(world.hatching.deadline, deadline)
        self.assertEqual(world.hatching.rng.getstate(), rng)

    def test_cast_seat_and_busy_click_survive_until_entire_guarded_body_departs(self):
        world = World(nest_settings(), visitor_seed=7)
        world.set_viewport(VIEW)
        nest = world.layout.nest
        self.assertTrue(world.hatch_egg(nest.x))
        # Past the viewport center crossing, but the tail still needs its seat.
        target_age = (31 * SECOND
                      + int((VIEW[2] + 1 - (nest.x + 8)) * SECOND / 8))
        self.advance(world, target_age)
        pose = world.snapshot()['hatching']
        self.assertGreater(pose['x'], VIEW[2])
        self.assertLess(young_brachiosaurus_bounds(pose)[0], VIEW[2] + 4 * NEST_DEPTH + 2)
        self.assertIn(YOUNG, world.cast.members)
        self.assertFalse(world.hatch_egg(nest.x))
        self.advance(world, 4 * SECOND)
        self.assertIsNone(world.snapshot()['hatching'])
        self.assertNotIn(YOUNG, world.cast.members)
        self.assertTrue(world.hatch_egg(nest.x))

    def test_click_cannot_preempt_full_budget_or_incumbent_water_jump(self):
        blocked = World(nest_settings(maximum=1), visitor_seed=7)
        occupied = World(nest_settings(), visitor_seed=7)
        for world in (blocked, occupied):
            world.set_viewport(VIEW)
        self.assertTrue(occupied.spawn_water_jump(30, 44))
        for world in (blocked, occupied):
            members = world.cast.members
            clocks = world.elapsed_ns, world._walk_ns, world.hatching.deadline
            rng = world.hatching.rng.getstate()
            self.assertFalse(world.hatch_egg(world.layout.nest.x))
            self.assertEqual(world.cast.members, members)
            self.assertIsNone(world.snapshot()['hatching'])
            self.assertEqual((world.elapsed_ns, world._walk_ns, world.hatching.deadline), clocks)
            self.assertEqual(world.hatching.rng.getstate(), rng)
        self.assertIn('water_jump', occupied.cast.members)
        self.advance(occupied, 4 * SECOND)
        self.assertIsNone(occupied.snapshot()['hatching'])
        self.assertTrue(occupied.hatch_egg(occupied.layout.nest.x))
        self.assertIn(YOUNG, occupied.cast.members)

    def test_paused_click_is_rejected_and_does_not_create_a_later_hatch(self):
        world = World(nest_settings(), visitor_seed=7)
        world.set_viewport(VIEW)
        clocks = world.elapsed_ns, world._walk_ns, world.hatching.deadline
        world.paused = True
        self.assertFalse(world.hatch_egg(world.layout.nest.x))
        world.advance(250_000_000)
        self.assertIsNone(world.snapshot()['hatching'])
        self.assertEqual((world.elapsed_ns, world._walk_ns, world.hatching.deadline), clocks)
        world.paused = False
        self.advance(world, SECOND)
        self.assertIsNone(world.snapshot()['hatching'])
        self.assertTrue(world.hatch_egg(world.layout.nest.x))

    def test_manual_hatch_uses_reduced_speed_walk_clock_through_departure(self):
        config = nest_settings()
        config['motion']['speed'] = .5
        config['motion']['reducedMotion'] = True
        world = World(config, visitor_seed=7)
        world.set_viewport(VIEW)
        deadline = world.hatching.deadline
        self.assertTrue(world.hatch_egg(world.layout.nest.x))
        self.advance(world, 120 * SECOND)
        pose = world.snapshot()['hatching']
        self.assertEqual(world._walk_ns, DEPARTURE_AT)
        self.assertEqual(pose['state'], 'scurrying')
        self.assertEqual(pose['x'], world.layout.nest.x + 8)
        self.assertIn(YOUNG, world.cast.members)
        self.assertFalse(world.hatch_egg(world.layout.nest.x))
        self.advance(world, 60 * SECOND)
        self.assertIsNone(world.snapshot()['hatching'])
        self.assertNotIn(YOUNG, world.cast.members)
        self.assertEqual(world.hatching.deadline, deadline)

    def test_complete_event_reserves_exactly_one_seat_until_full_departure(self):
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
        self.assertEqual(world.snapshot()['hatching']['state'], 'scurrying')
        self.assertIn(YOUNG, world.cast.members)
        self.advance(world, 90 * SECOND)
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
