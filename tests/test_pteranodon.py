import copy
from dataclasses import replace
from fractions import Fraction
import math
from pathlib import Path
import random
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from cast import Cast, cast_groups
from configuration import settings
from engine import World
from layout import generate_layout
from pteranodon import (PACE, SECOND, PteranodonFlocks, flight_radius,
                        pteranodon_bounds, pteranodon_pose)


def flight_settings(maximum=128):
    return settings({'animals': {key: key == 'pteranodonEnabled'
                                 for key in settings()['animals']},
                     'population': {'maxVisible': maximum},
                     'motion': {'speed': 1, 'parallaxStrength': 0}})


class FlyingSilhouettes(unittest.TestCase):
    def bird(self):
        return replace(generate_layout(17, {}).pteranodons[0], phase=0, y=16)

    def test_flap_bank_and_cycle_boundaries_are_continuous(self):
        bird = self.bird()
        for boundary in (0, 2, 4, 6, 9, 18):
            time = boundary / .53
            before = pteranodon_pose(bird, time - 1e-7, 1, 30)
            after = pteranodon_pose(bird, time + 1e-7, 1, 30)
            for key in ('y', 'tip_y', 'bank'):
                self.assertAlmostEqual(before[key], after[key], places=5)
        for cycle in (2.5, 3, 6.5, 8):
            pose = pteranodon_pose(bird, cycle / .53, 1, 30)
            self.assertEqual(pose['bank'], 0)
            self.assertAlmostEqual(pose['tip_y'] - pose['y'], -.7)
        self.assertGreater(abs(pteranodon_pose(bird, 5 / .53, 1, 30)['bank']), .2)
        self.assertNotAlmostEqual(pteranodon_pose(bird, .7 / .53, 1, 30)['tip_y']
                                  - pteranodon_pose(bird, .7 / .53, 1, 30)['y'], -.7)

    def test_bank_and_flap_are_bounded_and_reduced_motion_attenuates_both(self):
        bird = self.bird()
        for index in range(1801):
            time = index / 100
            normal = pteranodon_pose(bird, time, 1, 30)
            calm = pteranodon_pose(bird, time, .18, 30)
            self.assertLessEqual(abs(normal['bank']), .28)
            self.assertLessEqual(abs(normal['tip_y'] - normal['y']), 2.8)
            self.assertAlmostEqual(calm['bank'], normal['bank'] * .18)
            self.assertAlmostEqual(calm['y'] - bird.y, (normal['y'] - bird.y) * .18)
            self.assertAlmostEqual(calm['tip_y'] - calm['y'] + .7,
                                   (normal['tip_y'] - normal['y'] + .7) * .18)

    def test_rotation_bounds_are_pure_and_follow_mutated_roots(self):
        pose = pteranodon_pose(self.bird(), 5 / .53, 1, 30)
        before = dict(pose)
        radius = math.hypot(pose['span'], 2.8)
        self.assertEqual(pteranodon_bounds(pose),
                         (30 - radius, pose['y'] - radius, 30 + radius,
                          pose['y'] + radius, pose['depth']))
        self.assertEqual(pose, before)
        pose.update(x=-100, y=25)
        self.assertEqual(pteranodon_bounds(pose),
                         (-100 - radius, 25 - radius, -100 + radius,
                          25 + radius, pose['depth']))


class FlockLifecycle(unittest.TestCase):
    def controller(self, bounds=(23, 123), enabled=True):
        layout = generate_layout(17, {})
        return PteranodonFlocks(layout.pteranodon_flock,
                               layout.pteranodon_visit_seed, bounds, enabled=enabled)

    def pose(self, visits):
        return visits.current(float(visits.motion_ns / SECOND))

    def arrive(self, visits, rate=1):
        visits.advance(visits.deadline, visits.deadline * rate)
        return visits.born

    def step(self, visits, seconds, rate=1):
        delta = Fraction(str(seconds)) * SECOND
        visits.advance(visits.elapsed_ns + delta, visits.motion_ns + delta * rate)

    def test_independent_active_minute_schedule_and_common_forward_pace(self):
        for rate in (Fraction(1, 10), Fraction(1, 2), 1, 2):
            visits = self.controller()
            first = visits.deadline
            self.assertGreaterEqual(first, 240 * SECOND)
            self.assertLessEqual(first, 540 * SECOND)
            visits.advance(first - 1, (first - 1) * rate)
            self.assertIsNone(self.pose(visits))
            visits.advance(first, first * rate)
            before = self.pose(visits)
            self.assertEqual(before['generation'], 0)
            for bird in before['members']:
                self.assertLess(pteranodon_bounds(bird)[2], 23 - 3.5 * bird['depth'])
            self.step(visits, 2, rate)
            after = self.pose(visits)
            for a, b in zip(before['members'], after['members']):
                self.assertAlmostEqual(b['x'] - a['x'], float(PACE * 2 * rate))
            self.assertGreaterEqual(visits.deadline - first, 240 * SECOND)
            self.assertLessEqual(visits.deadline - first, 540 * SECOND)

    def test_ordered_v_spacing_and_rotated_envelopes_stay_in_sky(self):
        visits = self.controller()
        self.arrive(visits)
        self.step(visits, 30)
        birds = self.pose(visits)['members']
        leader = birds[0]
        for follower in birds[1:]:
            self.assertLess(follower['x'], leader['x'])
        for upper, lower in zip(birds[1::2], birds[2::2]):
            self.assertAlmostEqual(upper['x'], lower['x'])
            self.assertLess(upper['y'], leader['y'])
            self.assertGreater(lower['y'], leader['y'])
        for index, bird in enumerate(birds):
            bounds = pteranodon_bounds(bird)
            self.assertGreater(bounds[1], 0)
            self.assertLess(bounds[3], 35)
            for other in birds[index + 1:]:
                distance = math.hypot(bird['x'] - other['x'], bird['y'] - other['y'])
                self.assertGreater(distance, flight_radius(bird['span'])
                                   + flight_radius(other['span']))

    def test_busy_deadlines_skip_without_queue_and_replay_matches(self):
        visits = self.controller((-2000, 2000))
        self.arrive(visits, Fraction(1, 10))
        generation = visits.generation
        target = visits.elapsed_ns + 10_000 * SECOND
        visits.advance(target, target / 10)
        self.assertEqual(visits.generation, generation)
        self.assertTrue(visits.active)
        self.assertGreater(visits.deadline, target)
        replay = self.controller((-2000, 2000))
        replay.advance(target, target / 10)
        self.assertEqual(self.pose(visits), self.pose(replay))
        self.assertEqual(visits.deadline, replay.deadline)
        finish = visits._departure_boundary()
        visits.advance(finish * 10, finish)
        self.assertIsNone(self.pose(visits))
        self.assertGreater(visits.deadline, visits.elapsed_ns)

    def test_disabled_arrivals_do_not_retime_schedule_and_live_pass_keeps_moving(self):
        enabled, disabled = self.controller(), self.controller(enabled=False)
        deadline = enabled.deadline
        enabled.advance(deadline, deadline)
        disabled.advance(deadline, deadline)
        self.assertIsNone(self.pose(disabled))
        self.assertEqual(enabled.deadline, disabled.deadline)
        enabled.set_enabled(False)
        before = self.pose(enabled)
        self.step(enabled, 1)
        after = self.pose(enabled)
        self.assertGreater(after['members'][0]['x'], before['members'][0]['x'])
        enabled.set_enabled(True)
        self.assertEqual(self.pose(enabled), after)
        disabled.set_enabled(True)
        self.assertIsNone(self.pose(disabled))
        self.assertEqual(enabled.deadline, disabled.deadline)

    def test_latched_prefix_retires_only_after_its_rear_and_never_changes_midpass(self):
        for count in (2, 3, 4, 5):
            visits = self.controller()
            self.arrive(visits)
            full_end = visits._departure_boundary()
            visits.latch_prefix(count)
            end = visits._departure_boundary()
            self.assertLessEqual(end, full_end)
            visits.latch_prefix(0)
            visits.latch_prefix(5)
            self.assertEqual(visits.admitted_count, count)
            visits.advance(end - 1, end - 1)
            members = self.pose(visits)['members'][:count]
            rear = min(pteranodon_bounds(bird)[0] - 3.5 * bird['depth'] for bird in members)
            self.assertGreater(rear, 123)
            self.assertLess(rear, 124)
            visits.advance(end, end)
            self.assertIsNone(self.pose(visits))
            self.assertGreater(visits.deadline, visits.elapsed_ns)
            self.arrive(visits)
            self.assertEqual(visits.generation, 1)
            self.assertIsNone(visits.admitted_count)
            self.assertTrue(all(pteranodon_bounds(bird)[2] < 23
                                for bird in self.pose(visits)['members']))

    def test_never_admitted_flock_uses_full_candidate_rear(self):
        visits = self.controller()
        self.arrive(visits)
        full = visits._departure_boundary()
        short = self.controller()
        self.arrive(short)
        short.latch_prefix(2)
        self.assertGreater(full, short._departure_boundary())
        visits.advance(short._departure_boundary(), short._departure_boundary())
        self.assertIsNotNone(self.pose(visits))
        visits.advance(full, full)
        self.assertIsNone(self.pose(visits))

    def test_resize_preserves_pose_and_does_not_backdate_retirement_or_replacement(self):
        visits = self.controller((-200, 500))
        self.arrive(visits)
        self.step(visits, 350)
        before = self.pose(visits)
        deadline = visits.deadline
        visits.set_viewport((0, 50))
        self.assertEqual(self.pose(visits), before)
        self.assertEqual(visits.deadline, deadline)
        self.step(visits, .1)
        self.assertIsNone(self.pose(visits))
        self.assertGreater(visits.deadline, visits.elapsed_ns)
        self.arrive(visits)
        self.assertTrue(all(pteranodon_bounds(bird)[2] < 0
                            for bird in self.pose(visits)['members']))
        before = self.pose(visits)
        visits.set_viewport((-100, 1000))
        self.assertEqual(self.pose(visits), before)
        self.step(visits, 100)
        self.assertIsNotNone(self.pose(visits))

    def test_fractional_speed_history_matches_frame_partitions(self):
        results = []
        for quantum in (SECOND // 4, SECOND // 15, SECOND // 144):
            visits = self.controller()
            self.arrive(visits, Fraction(3, 4))
            for seconds, speed in ((3, Fraction(3, 4)), (2, Fraction(7, 5)), (4, Fraction(1, 10))):
                remaining = seconds * SECOND
                while remaining:
                    delta = min(quantum, remaining)
                    visits.advance(visits.elapsed_ns + delta, visits.motion_ns + delta * speed)
                    remaining -= delta
            results.append((self.pose(visits), visits.deadline, visits.motion_ns))
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0], results[2])

    def test_many_events_use_bounded_state_and_do_not_touch_global_rng(self):
        state = random.getstate()
        visits = self.controller()
        keys = set(vars(visits))
        visits.advance(1_000_000 * SECOND, 1_000_000 * SECOND)
        self.assertEqual(set(vars(visits)), keys)
        self.assertEqual(random.getstate(), state)
        self.assertGreater(visits.deadline, visits.elapsed_ns)
        self.assertTrue(all(not isinstance(value, (list, dict, set))
                            for value in vars(visits).values()))


class FlockAdmission(unittest.TestCase):
    def group(self, x=-20, generation=0):
        config = flight_settings()
        snapshot = World(config).snapshot()
        snapshot['pteranodons'] = ()
        snapshot['pteranodon_flock'] = {
            'generation': generation,
            'members': tuple(pteranodon_pose(bird, 0, 1, x + bird.start_x)
                             for bird in snapshot['layout'].pteranodon_flock)}
        return cast_groups(snapshot, config, (0, 0, 100, 60))

    def test_flock_guard_preserves_swimmer_initial_and_refresh_admission(self):
        config = flight_settings()
        config['animals']['plesiosaurusEnabled'] = True
        snapshot = World(config).snapshot()
        snapshot.update(pteranodons=(), pteranodon_flock=None)
        swimmer = snapshot['plesiosaurus']
        swimmer.update(x=50, visible=True, state='looking',
                       body_y=swimmer['water_y'] - 1)
        groups = cast_groups(snapshot, config, (0, 0, 100, 60))
        self.assertFalse(next(group for group in groups
                              if group['key'] == 'plesiosaurus')['entry'])
        for options in ({'initial': True}, {'refresh': True}):
            cast = Cast()
            cast.update(groups, 3, (0, 0, 100, 60), **options)
            self.assertIn('plesiosaurus', cast.members)

    def test_flock_requires_two_seats_and_reserves_only_fixed_prefix(self):
        for maximum, expected in ((1, 0), (2, 0), (3, 2), (4, 3), (128, 5)):
            cast = Cast()
            cast.update(self.group(), maximum, (0, 0, 100, 60), initial=True)
            self.assertEqual(cast.count('pteranodon:flock'), expected)
        cast = Cast()
        cast.update(self.group(), 3, (0, 0, 100, 60))
        cast.update(self.group(x=40), 128, (0, 0, 100, 60))
        self.assertEqual(cast.count('pteranodon:flock'), 2)
        cast.update(self.group(x=40), 128, (0, 0, 100, 60), refresh=True)
        self.assertEqual(cast.count('pteranodon:flock'), 2)
        cast.update(self.group(x=40), 2, (0, 0, 100, 60), refresh=True)
        self.assertEqual(cast.count('pteranodon:flock'), 0)
        cast.update(self.group(x=40), 128, (0, 0, 100, 60), refresh=True)
        self.assertEqual(cast.count('pteranodon:flock'), 0)
        # Even a released pass still completely offleft cannot grow on cap-up.
        cast = Cast()
        cast.update(self.group(), 3, (0, 0, 100, 60))
        cast.update(self.group(), 1, (0, 0, 100, 60), refresh=True)
        cast.update(self.group(), 128, (0, 0, 100, 60), refresh=True)
        self.assertEqual(cast.count('pteranodon:flock'), 0)

    def test_existing_occupant_is_not_evicted_and_inview_arrival_is_never_admitted(self):
        cast = Cast()
        resident = dict(key='incumbent', token=0, minimum=1, active=True, entry=True,
                        members=(dict(id='incumbent', bounds=(40, 10, 50, 20, .2)),))
        cast.update([resident], 3, (0, 0, 100, 60))
        cast.update([resident, *self.group()], 3, (0, 0, 100, 60))
        self.assertIn('incumbent', cast.members)
        self.assertEqual(cast.count('pteranodon:flock'), 0)
        cast.update(self.group(x=40), 128, (0, 0, 100, 60), initial=True, refresh=True)
        self.assertEqual(cast.count('pteranodon:flock'), 0)
        cast.update(self.group(generation=1), 128, (0, 0, 100, 60))
        self.assertEqual(cast.count('pteranodon:flock'), 5)

    def test_full_admitted_rear_holds_seats_until_last_follower_clears(self):
        cast = Cast()
        cast.update(self.group(), 128, (0, 0, 100, 60))
        cast.update(self.group(x=110), 128, (0, 0, 100, 60))
        self.assertEqual(cast.count('pteranodon:flock'), 5)
        cast.update(self.group(x=130), 128, (0, 0, 100, 60))
        self.assertEqual(cast.count('pteranodon:flock'), 0)


class WorldFlightHistory(unittest.TestCase):
    def advance(self, world, nanoseconds, fps=4):
        quantum = SECOND // fps
        while nanoseconds:
            delta = min(quantum, nanoseconds)
            world.advance(delta)
            nanoseconds -= delta

    def arrival_world(self, config=None):
        config = flight_settings() if config is None else config
        first = World(config).pteranodon_flocks.deadline
        world = World(config, elapsed_ns=first - SECOND, visitor_seed=7)
        world.set_viewport((23, 0, 123, 60))
        return world

    def test_fps_pause_and_accumulated_speed_history_preserve_exact_state(self):
        poses = []
        for fps in (15, 60, 144):
            world = self.arrival_world()
            self.advance(world, 2 * SECOND, fps)
            before = world.snapshot()['pteranodon_flock']
            deadline = world.pteranodon_flocks.deadline
            elapsed, motion = world.elapsed_ns, world._motion_ns
            world.paused = True
            world.advance(250_000_000)
            self.assertEqual(world.snapshot()['pteranodon_flock'], before)
            self.assertEqual((world.elapsed_ns, world._motion_ns), (elapsed, motion))
            world.paused = False
            config = copy.deepcopy(world.config)
            config['motion']['speed'] = .5
            world.reconfigure(config)
            self.assertEqual(world.snapshot()['pteranodon_flock'], before)
            self.advance(world, 2 * SECOND, fps)
            after = world.snapshot()['pteranodon_flock']
            self.assertAlmostEqual(after['members'][0]['x'] - before['members'][0]['x'], 1.2)
            self.assertEqual(world.pteranodon_flocks.deadline, deadline)
            poses.append(after)
        self.assertEqual(poses[0], poses[1])
        self.assertEqual(poses[0], poses[2])

    def test_constant_config_replay_matches_live_and_first_wide_viewport(self):
        config = flight_settings()
        first = World(config).pteranodon_flocks.deadline
        target = first + 10 * SECOND + 123456789
        live = World(config, visitor_seed=7)
        live.set_viewport((-100, 0, 500, 60))
        self.advance(live, target)
        replay = World(config, elapsed_ns=target, visitor_seed=7)
        replay.set_viewport((-100, 0, 500, 60))
        self.assertEqual(replay.snapshot()['pteranodon_flock'], live.snapshot()['pteranodon_flock'])
        self.assertEqual(replay.pteranodon_flocks.deadline, live.pteranodon_flocks.deadline)
        before = replay.snapshot()['pteranodon_flock']
        replay.set_viewport((0, 0, 50, 60))
        self.assertEqual(replay.snapshot()['pteranodon_flock'], before)

    def test_off_on_and_cap_changes_do_not_reset_or_inview_readmit_a_pass(self):
        world = self.arrival_world()
        self.advance(world, 25 * SECOND)
        before = world.snapshot()['pteranodon_flock']
        self.assertEqual(world.cast.count('pteranodon:flock'), 5)
        deadline = world.pteranodon_flocks.deadline
        config = copy.deepcopy(world.config)
        config['animals']['pteranodonEnabled'] = False
        world.reconfigure(config)
        self.assertFalse(any(actor.startswith('pteranodon:') for actor in world.cast.members))
        self.assertEqual(world.snapshot()['pteranodon_flock'], before)
        self.advance(world, SECOND)
        hidden = world.snapshot()['pteranodon_flock']
        config['animals']['pteranodonEnabled'] = True
        world.reconfigure(config)
        self.assertEqual(world.snapshot()['pteranodon_flock'], hidden)
        self.assertEqual(world.cast.count('pteranodon:flock'), 0)
        self.assertEqual(world.pteranodon_flocks.admitted_count, 5)
        self.assertEqual(world.pteranodon_flocks.deadline, deadline)
        config['population']['maxVisible'] = 1
        world.reconfigure(config)
        self.assertEqual(world.cast.members, ('brachiosaurus',))
        self.assertEqual(world.snapshot()['pteranodon_flock'], hidden)

    def test_default_budget_and_eight_flyer_hard_limit(self):
        world = self.arrival_world(flight_settings(8))
        for _ in range(600):
            world.advance(250_000_000)
            snapshot = world.snapshot()
            self.assertLessEqual(len(snapshot['admitted']), 8)
            self.assertLessEqual(sum(actor.startswith('pteranodon:')
                                     for actor in snapshot['admitted']), 8)
            flock = snapshot['pteranodon_flock']
            if flock is not None:
                self.assertLessEqual(len(snapshot['pteranodons']) + len(flock['members']), 8)

    def test_scenery_preset_and_reduced_motion_preserve_lifecycle_but_seed_resets_it(self):
        world = self.arrival_world()
        self.advance(world, 2 * SECOND)
        controller = world.pteranodon_flocks
        before = world.snapshot()['pteranodon_flock']
        config = copy.deepcopy(world.config)
        config['scenery']['treeDensity'] = 0
        config['preset'] = 'dusk'
        world.reconfigure(config)
        self.assertIs(world.pteranodon_flocks, controller)
        self.assertEqual(world.snapshot()['pteranodon_flock'], before)
        config['motion']['reducedMotion'] = True
        world.reconfigure(config)
        calm = world.snapshot()['pteranodon_flock']
        self.assertIs(world.pteranodon_flocks, controller)
        self.assertEqual(tuple(bird['x'] for bird in calm['members']),
                         tuple(bird['x'] for bird in before['members']))
        config['seed'] += 1
        world.reconfigure(config)
        self.assertIsNot(world.pteranodon_flocks, controller)
        self.assertIsNone(world.snapshot()['pteranodon_flock'])
        self.assertGreater(world.pteranodon_flocks.deadline, world.elapsed_ns)

    def test_caps_and_disabled_births_keep_future_arrival_deadlines(self):
        baseline = World(flight_settings())
        first = baseline.pteranodon_flocks.deadline
        baseline.pteranodon_flocks.advance(first, first)
        expected = baseline.pteranodon_flocks.deadline
        for cap in (1, 2, 3, 8, 128):
            config = flight_settings(cap)
            world = self.arrival_world(config)
            self.advance(world, 2 * SECOND)
            self.assertEqual(world.pteranodon_flocks.deadline, expected)
            self.assertLessEqual(len(world.cast.members), cap)
            if cap < 3:
                self.assertEqual(world.cast.count('pteranodon:flock'), 0)
                self.assertIsNone(world.pteranodon_flocks.admitted_count)
        config = flight_settings()
        config['animals']['pteranodonEnabled'] = False
        world = self.arrival_world(config)
        self.advance(world, 2 * SECOND)
        self.assertIsNone(world.snapshot()['pteranodon_flock'])
        self.assertEqual(world.pteranodon_flocks.deadline, expected)


    def test_flock_activity_does_not_perturb_unrelated_streams(self):
        config = settings({'population': {'randomVisitors': True}})
        first, second = World(config, visitor_seed=7), World(config, visitor_seed=7)
        with patch.object(PteranodonFlocks, '_interval', return_value=240 * SECOND):
            first.pteranodon_flocks.advance(5000 * SECOND, 5000 * SECOND)
        self.assertEqual(first.layout, second.layout)
        self.assertEqual(first.diplodocus.rng.getstate(), second.diplodocus.rng.getstate())
        self.assertEqual(first.visitors.rng.getstate(), second.visitors.rng.getstate())
        self.assertEqual(first._routes._records, second._routes._records)


if __name__ == '__main__':
    unittest.main()
