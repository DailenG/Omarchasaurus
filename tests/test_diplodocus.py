import copy
from dataclasses import replace
from fractions import Fraction
from pathlib import Path
import random
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from configuration import settings
from diplodocus import DiplodocusVisits, SECOND
from canvas import Canvas
from engine import World
from character_art import draw_scene, visible_cast_members


class DiplodocusBehavior(unittest.TestCase):
    def test_palette_changes_only_rendered_colors_at_cold_start_and_reload(self):
        for resident in (False, True):
            for rotating in (False, True):
                document = {'animals': {'diplodocusResident': resident},
                            'population': {'randomVisitors': rotating},
                            'motion': {'speed': 1.25, 'parallaxStrength': 1.5}}
                morning = World(settings(document), elapsed_ns=11 * SECOND, visitor_seed=17)
                dusk = World(settings(dict(document, preset='dusk')),
                             elapsed_ns=11 * SECOND, visitor_seed=17)
                frames = []
                for world in (morning, dusk):
                    world.set_viewport(Canvas(160, 48).world_bounds)
                    canvas = Canvas(160, 48, camera=world.snapshot()['camera'])
                    draw_scene(canvas, world.snapshot(), world.config)
                    frames.append(canvas)
                self.assertEqual(morning.snapshot(), dusk.snapshot())
                self.assertEqual(frames[0].chars, frames[1].chars)
                self.assertEqual(frames[0].owners, frames[1].owners)
                self.assertNotEqual(frames[0].colors, frames[1].colors)
                before = morning.snapshot()
                morning.reconfigure(dict(morning.config, preset='dusk'))
                self.assertEqual(morning.snapshot(), before)
                self.advance_world(morning, 3 * SECOND)
                self.advance_world(dusk, 3 * SECOND)
                self.assertEqual(morning.snapshot(), dusk.snapshot())
                self.assertEqual(morning.diplodocus.deadline, dusk.diplodocus.deadline)
                self.assertEqual(morning.pteranodon_flocks.deadline, dusk.pteranodon_flocks.deadline)
                self.assertEqual(morning.weather.deadline, dusk.weather.deadline)
                self.assertEqual(morning.hatching.deadline, dusk.hatching.deadline)
                self.assertEqual(morning.volcano_puffs.deadline, dusk.volcano_puffs.deadline)

    def test_residency_changes_in_either_palette_finish_visible_transitions(self):
        for preset in ('morning', 'dusk'):
            with self.subTest(preset=preset):
                config = settings({
                    'preset': preset,
                    'animals': {key: key == 'diplodocusEnabled' for key in settings()['animals']},
                    'population': {'maxVisible': 2},
                })
                world = World(config, visitor_seed=17)
                world.set_viewport(Canvas(320, 96).world_bounds)
                self.assertIsNone(world.snapshot()['diplodocus'])
                config['animals']['diplodocusResident'] = True
                world.reconfigure(config)
                entry = world.snapshot()['diplodocus']
                self.assertEqual(entry['state'], 'approaching')
                self.assertLess(entry['x'] + 40, world._visitor_bounds[0])
                self.advance_world(world, world.diplodocus.approach_duration + 9 * SECOND)
                before = world.snapshot()['diplodocus']
                self.assertEqual(before['state'], 'drinking')
                self.assertIn('diplodocus', world.snapshot()['admitted'])
                config['animals']['diplodocusResident'] = False
                world.reconfigure(config)
                self.assertEqual(world.snapshot()['diplodocus'], before)
                self.advance_world(world, world.diplodocus.exit_at - world.diplodocus.walk_ns + SECOND)
                leaving = world.snapshot()['diplodocus']
                self.assertEqual(leaving['state'], 'departing')
                config['animals']['diplodocusResident'] = True
                world.reconfigure(config)
                self.assertEqual(world.snapshot()['diplodocus'], leaving)
                self.advance_world(world, world.diplodocus._departure_boundary() - world.diplodocus.walk_ns)
                returning = world.snapshot()['diplodocus']
                self.assertEqual(returning['generation'], leaving['generation'] + 1)
                self.assertEqual(returning['state'], 'approaching')
                self.assertLess(returning['x'] + 40, world._visitor_bounds[0])
                self.advance_world(world, world.diplodocus.approach_duration + 12 * SECOND)
                resident = world.snapshot()['diplodocus']
                self.assertEqual(resident['x'], world.layout.diplodocus.shore_x)
                self.assertEqual(resident['drink'], 1)
                self.assertIn('diplodocus', world.snapshot()['admitted'])

    def controller(self, resident=False, bounds=(23, 123)):
        return DiplodocusVisits(World(settings()).layout.diplodocus, resident, bounds)

    def pose(self, visits):
        return visits.current(float(visits.walk_ns / SECOND))

    def step(self, visits, seconds, rate=1):
        delta = Fraction(str(seconds)) * SECOND
        visits.advance(visits.elapsed_ns + delta, visits.walk_ns + delta * rate)

    def arrive(self, visits):
        visits.advance(visits.deadline, visits.deadline)
        return visits.born

    def advance_world(self, world, nanoseconds, fps=4):
        # Exact final elapsed time, including a fractional last frame.
        quantum = SECOND // fps
        while nanoseconds:
            delta = min(quantum, nanoseconds)
            world.advance(delta)
            nanoseconds -= delta

    def test_visitor_cadence_is_active_minutes_not_walk_speed(self):
        for rate in (Fraction(1, 10), Fraction(1, 2), 1, 2):
            visits = self.controller()
            first = visits.deadline
            self.assertGreaterEqual(first, 600 * SECOND)
            self.assertLessEqual(first, 1200 * SECOND)
            visits.advance(first - 1, (first - 1) * rate)
            self.assertIsNone(self.pose(visits))
            visits.advance(first, first * rate)
            self.assertEqual(self.pose(visits)['state'], 'approaching')
            self.assertEqual(self.pose(visits)['stride'], 0)
            self.assertLess(self.pose(visits)['x'] + 40, visits.bounds[0] - .735)
            for _ in range(5):
                previous = visits.deadline
                visits.advance(previous, previous * rate)
                self.assertGreaterEqual(visits.deadline - previous, 600 * SECOND)
                self.assertLessEqual(visits.deadline - previous, 1200 * SECOND)

    def test_coincident_arrival_and_approach_end_complete_at_the_same_endpoint(self):
        descriptor = replace(self.controller().descriptor, shore_x=65.0)
        left = descriptor.shore_x + 3.5 * descriptor.depth + 41 - 450
        with patch.object(DiplodocusVisits, '_interval', return_value=600 * SECOND):
            visits = DiplodocusVisits(descriptor, False, (left, 110 - left))
            self.arrive(visits)
            boundary = visits.born + visits.approach_duration
            self.assertEqual(boundary, visits.deadline, 'Fixture must align both events')
            visits.advance(boundary, boundary)
            pose = self.pose(visits)
            self.assertEqual(pose['state'], 'drinking')
            self.assertEqual(pose['x'], descriptor.shore_x)
            self.assertEqual(pose['stride'], 0)
            self.assertEqual(pose['drink'], 0)

    def test_fractional_approach_and_drink_boundaries_carry_overshoot(self):
        visits = self.controller()
        start = self.arrive(visits)
        arrival = start + visits.approach_duration
        visits.advance(arrival - 1, arrival - 1)
        before = self.pose(visits)
        visits.advance(arrival + SECOND / 2, arrival + SECOND / 2)
        after = self.pose(visits)
        self.assertEqual(after['state'], 'drinking')
        self.assertAlmostEqual(after['x'], before['x'])
        self.assertAlmostEqual(after['drink'], (1 / 12) ** 2 * (3 - 2 / 12))
        visits.advance(arrival + 24 * SECOND, arrival + 24 * SECOND)
        leaving = self.pose(visits)
        self.assertEqual(leaving['state'], 'departing')
        self.assertEqual(leaving['drink'], 0)
        self.assertEqual(leaving['stride'], 0)
        self.step(visits, 1)
        self.assertAlmostEqual(self.pose(visits)['x'] - leaving['x'], .1875)
        self.step(visits, 2)
        self.assertAlmostEqual(self.pose(visits)['x'] - leaving['x'], 1.5)

    def test_overdue_visits_are_skipped_without_overlap_or_catchup_queue(self):
        visits = self.controller(bounds=(-2000, 2000))
        first = visits.deadline
        visits.advance(first, first / 10)
        generation = self.pose(visits)['generation']
        # This deliberately slow, wide approach spans many scheduled arrivals.
        visits.advance(first + 20_000 * SECOND, (first + 20_000 * SECOND) / 10)
        self.assertEqual(self.pose(visits)['generation'], generation)
        self.assertEqual(self.pose(visits)['state'], 'approaching')
        self.assertGreater(visits.deadline, visits.elapsed_ns)
        # Completing it does not immediately release a queued arrival.
        arrival_walk = visits.born + visits.approach_duration
        target_walk = arrival_walk + 24 * SECOND + 3000 * SECOND
        target_elapsed = target_walk * 10
        visits.advance(target_elapsed, target_walk)
        self.assertGreater(visits.deadline, visits.elapsed_ns)
        # A fresh constant-config replay agrees despite skipped arrivals.
        fresh = self.controller(bounds=(-2000, 2000))
        fresh.advance(target_elapsed, target_walk)
        self.assertEqual(self.pose(visits), self.pose(fresh))

    def test_resident_starts_drinking_and_remains_without_episodes(self):
        visits = self.controller(True)
        initial = self.pose(visits)
        self.assertEqual(initial['drink'], 1)
        self.assertEqual(initial['stride'], 0)
        self.step(visits, 86400)
        after = self.pose(visits)
        for field in ('x', 'drink', 'stride', 'phase', 'state', 'generation'):
            self.assertEqual(after[field], initial[field])
        self.assertIsNone(visits.deadline)

    def test_waiting_approach_and_drink_become_resident_without_teleport(self):
        visits = self.controller()
        visits.set_resident(True)
        entry = self.pose(visits)
        self.assertEqual(entry['state'], 'approaching')
        self.assertLess(entry['x'] + 40, visits.bounds[0])
        self.step(visits, 20)
        before = self.pose(visits)
        visits.set_resident(False)
        self.assertEqual(self.pose(visits), before)
        visits.set_resident(True)
        self.assertEqual(self.pose(visits), before)
        arrival = visits.born + visits.approach_duration
        visits.advance(arrival + 9 * SECOND, arrival + 9 * SECOND)
        before = self.pose(visits)
        visits.set_resident(False)
        self.assertEqual(self.pose(visits), before)
        self.step(visits, 10)
        before = self.pose(visits)
        visits.set_resident(True)
        self.assertEqual(self.pose(visits), before)
        self.step(visits, 100)
        self.assertEqual(self.pose(visits)['x'], visits.descriptor.shore_x)
        self.assertEqual(self.pose(visits)['generation'], entry['generation'])

    def test_visitor_drink_promotes_to_matching_resident_cycle(self):
        visits = self.controller()
        self.arrive(visits)
        arrival = visits.born + visits.approach_duration
        visits.advance(arrival + 21 * SECOND, arrival + 21 * SECOND)
        before = self.pose(visits)
        visits.set_resident(True)
        self.assertEqual(self.pose(visits), before)
        self.step(visits, 4)
        self.assertEqual(self.pose(visits)['state'], 'looking')
        self.assertEqual(self.pose(visits)['drink'], 0)
        self.step(visits, 15)
        self.assertGreater(self.pose(visits)['drink'], 0)

    def test_resident_exit_is_at_next_cycle_and_can_be_cancelled(self):
        visits = self.controller(True)
        before = self.pose(visits)
        visits.set_resident(False)
        self.assertEqual(self.pose(visits), before)
        self.assertGreaterEqual(visits.deadline - visits.elapsed_ns, 600 * SECOND)
        self.step(visits, 15)
        self.assertEqual(self.pose(visits)['state'], 'looking')
        before = self.pose(visits)
        visits.set_resident(True)
        self.assertEqual(self.pose(visits), before)
        self.step(visits, 20)
        self.assertEqual(self.pose(visits)['x'], before['x'])
        visits.set_resident(False)
        exit_at = visits.exit_at
        elapsed = visits.elapsed_ns + exit_at - visits.walk_ns
        visits.advance(elapsed, exit_at)
        self.assertEqual(self.pose(visits)['state'], 'departing')
        self.assertEqual(self.pose(visits)['drink'], 0)

    def test_departing_to_resident_finishes_rightward_then_enters_from_left(self):
        visits = self.controller(True)
        visits.set_resident(False)
        self.step(visits, 25)
        before = self.pose(visits)
        visits.set_resident(True)
        self.assertEqual(self.pose(visits), before)
        self.step(visits, 1)
        self.assertGreater(self.pose(visits)['x'], before['x'])
        exit_at = visits._departure_boundary()
        elapsed = visits.elapsed_ns + exit_at - visits.walk_ns
        visits.advance(elapsed, exit_at)
        after = self.pose(visits)
        self.assertEqual(after['generation'], before['generation'] + 1)
        self.assertEqual(after['state'], 'approaching')
        self.assertLess(after['x'] + 40, visits.bounds[0])

    def test_resize_extends_departure_without_moving_or_backdating(self):
        visits = self.controller(True)
        visits.set_resident(False)
        self.step(visits, 120)
        before = self.pose(visits)
        visits.set_viewport((-200, 500))
        self.assertEqual(self.pose(visits), before)
        self.step(visits, 100)
        self.assertEqual(self.pose(visits)['generation'], before['generation'])
        self.assertEqual(self.pose(visits)['state'], 'departing')
        before = self.pose(visits)
        visits.set_resident(True)
        visits.set_viewport((23, 80))
        self.assertEqual(self.pose(visits), before)
        self.step(visits, .1)
        after = self.pose(visits)
        self.assertEqual(after['generation'], before['generation'] + 1)
        # A narrower viewport retires now, not at a historical geometric edge.
        self.assertAlmostEqual(float((visits.walk_ns - visits.born) / SECOND), .1)

    def test_world_snapshot_history_and_first_viewport_match_live_frames(self):
        config = settings({'motion': {'speed': 1.25, 'reducedMotion': True}})
        target = 1500 * SECOND + 123456789
        canvas = Canvas(500, 40)
        live = World(config, visitor_seed=17)
        live.set_viewport(canvas.world_bounds)
        self.advance_world(live, target)
        replay = World(config, elapsed_ns=target, visitor_seed=17)
        replay.set_viewport(canvas.world_bounds)
        self.assertEqual(replay.snapshot()['diplodocus'], live.snapshot()['diplodocus'])
        before = replay.snapshot()['diplodocus']
        replay.set_viewport(Canvas(80, 80).world_bounds)
        self.assertEqual(replay.snapshot()['diplodocus'], before)

    def test_fps_and_pause_preserve_exact_pose_and_schedule(self):
        config = settings({'animals': {'diplodocusResident': True},
                           'motion': {'speed': .75, 'reducedMotion': True}})
        poses = []
        for fps in (15, 60, 144):
            world = World(config)
            world.set_viewport(Canvas(320, 96).world_bounds)
            for frame in range(fps * 5):
                world.advance((frame + 1) * SECOND // fps - frame * SECOND // fps)
            before = world.snapshot()['diplodocus']
            world.paused = True
            world.advance(250_000_000)
            self.assertEqual(world.snapshot()['diplodocus'], before)
            poses.append(before)
        self.assertEqual(poses[0], poses[1])
        self.assertEqual(poses[0], poses[2])

    def test_waiting_deadline_survives_pause_reload_and_disabled_future_slope(self):
        config = settings({'motion': {'speed': .5}})
        deadline = World(config).diplodocus.deadline
        world = World(config, elapsed_ns=deadline - 1)
        world.set_viewport(Canvas(320, 96).world_bounds)
        before_walk = world.diplodocus.walk_ns
        world.paused = True
        world.advance(250_000_000)
        changed = copy.deepcopy(config)
        changed['animals']['diplodocusEnabled'] = False
        changed['scenery']['flowerDensity'] = 0
        changed['motion'].update(speed=2, reducedMotion=True)
        world.reconfigure(changed)
        self.assertEqual(world.diplodocus.deadline, deadline)
        self.assertEqual(world.diplodocus.walk_ns, before_walk)
        self.assertIsNone(world.snapshot()['diplodocus'])
        world.paused = False
        world.advance(1)
        self.assertEqual(world.snapshot()['diplodocus']['state'], 'approaching')
        self.assertEqual(world.diplodocus.born, before_walk + 1)
        self.assertFalse(world.react('diplodocus'))
        before = world.snapshot()['diplodocus']
        changed['animals']['diplodocusEnabled'] = True
        world.reconfigure(changed)
        self.assertEqual(world.snapshot()['diplodocus'], before)
        self.assertTrue(world.react('diplodocus'))

    def test_reload_preserves_history_disabled_schedule_and_rng_namespaces(self):
        state = random.getstate()
        config = settings({'animals': {'diplodocusResident': True},
                           'population': {'randomVisitors': True}})
        a, b = (World(config, visitor_seed=17) for _ in range(2))
        self.advance_world(a, 3 * SECOND)
        self.advance_world(b, 3 * SECOND)
        before = a.snapshot()['diplodocus']
        changed = copy.deepcopy(config)
        changed['scenery']['treeDensity'] = 0
        changed['animals']['diplodocusEnabled'] = False
        changed['population']['maxVisible'] = 1
        changed['motion'] = dict(config['motion'], speed=2, reducedMotion=True)
        a.reconfigure(changed)
        self.assertEqual(a.snapshot()['diplodocus'], before)
        self.assertFalse(a.react('diplodocus'))
        self.assertNotIn('diplodocus', visible_cast_members(Canvas(320, 96), a.snapshot(), a.config))
        b.reconfigure(dict(changed, animals=dict(changed['animals'], diplodocusEnabled=True)))
        previous_walk = a.diplodocus.walk_ns
        self.advance_world(a, SECOND)
        self.advance_world(b, SECOND)
        self.assertEqual(a.diplodocus.walk_ns - previous_walk, SECOND)
        self.assertEqual(a.layout.diplodocus, b.layout.diplodocus)
        a.reconfigure(config)
        self.assertEqual(a.snapshot()['visitor'], b.snapshot()['visitor'])
        self.assertTrue(a.react('diplodocus'))
        self.assertEqual(random.getstate(), state)

    def test_admission_singleton_and_random_mode_independence_without_preemption(self):
        config = settings({'animals': {'diplodocusResident': True},
                           'population': {'maxVisible': 4, 'randomVisitors': True}})
        world = World(config, visitor_seed=17)
        world.set_viewport(Canvas(320, 96).world_bounds)
        before = world.snapshot()['admitted']
        accepted = world.spawn_water_jump(20, 44)
        snapshot = world.snapshot()
        self.assertTrue(set(before) <= set(snapshot['admitted']))
        self.assertEqual('water_jump' in snapshot['admitted'], accepted)
        canvas = Canvas(320, 96)
        for limit in (1, 2, 3, 4):
            config['population']['maxVisible'] = limit
            cast = visible_cast_members(canvas, snapshot, config)
            self.assertLessEqual(len(cast), limit)
            self.assertLessEqual(cast.count('diplodocus'), 1)
            self.assertTrue(set(cast) <= set(snapshot['admitted']))
        snapshot['diplodocus']['x'] = -1000
        self.assertNotIn('diplodocus', visible_cast_members(canvas, snapshot, config))
        world.reconfigure(dict(config, animals=dict(config['animals'], diplodocusEnabled=False)))
        self.assertFalse(world.react('diplodocus'))

    def test_snapshots_are_read_only_and_new_generations_clear_reaction_cooldown(self):
        world = World(settings({'animals': {'diplodocusResident': True}}))
        world.set_viewport(Canvas(320, 96).world_bounds)
        self.assertTrue(world.react('diplodocus'))
        self.advance_world(world, SECOND)
        self.assertGreater(world.snapshot()['diplodocus']['reaction'], .9)
        state = world.diplodocus.rng.getstate()
        before = world.snapshot()
        for _ in range(5):
            self.assertEqual(world.snapshot(), before)
        self.assertEqual(world.diplodocus.rng.getstate(), state)
        config = copy.deepcopy(world.config)
        config['seed'] += 1
        world.reconfigure(config)
        self.assertEqual(world.snapshot()['diplodocus']['reaction'], 0)
        self.assertTrue(world.react('diplodocus'))
        waiting = World(settings())
        self.assertFalse(waiting.react('diplodocus'))
        waiting.set_viewport(Canvas(320, 96).world_bounds)
        self.advance_world(waiting, waiting.diplodocus.deadline)
        self.assertTrue(waiting.react('diplodocus'))
        config = copy.deepcopy(waiting.config)
        config['animals']['diplodocusResident'] = True
        waiting.reconfigure(config)
        config['animals']['diplodocusResident'] = False
        waiting.reconfigure(config)
        # Retire beyond a narrow edge, then naturally wait until the next visit.
        self.advance_world(waiting, 400 * SECOND)
        self.assertIsNone(waiting.snapshot()['diplodocus'])
        self.assertNotIn('diplodocus', waiting.reactions)
        self.advance_world(waiting, waiting.diplodocus.deadline - waiting.elapsed_ns)
        self.assertTrue(waiting.react('diplodocus'))


if __name__ == '__main__':
    unittest.main()
