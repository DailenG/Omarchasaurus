import copy
from fractions import Fraction
import math
from pathlib import Path
import random
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from configuration import settings
from engine import World
from layout import generate_layout
from volcano import SECOND, VolcanoPuffs


def controller(seed=17):
    return VolcanoPuffs(generate_layout(seed, {}).volcano_puff_seed)


def arrive(event, *, calm=False, rate=1):
    event.advance(event.deadline,
                  event.motion_ns + (event.deadline - event.elapsed_ns) * rate,
                  calm=calm)


def move(event, seconds, *, calm=False, rate=1):
    delta = Fraction(seconds) * SECOND
    event.advance(event.elapsed_ns + delta, event.motion_ns + delta * rate, calm=calm)


class VolcanoLifecycle(unittest.TestCase):
    def test_three_to_seven_active_minute_cadence_repeats(self):
        for seed in (0, 1, 17, 2026):
            event = controller(seed)
            previous = Fraction(0)
            for generation in range(8):
                deadline = event.deadline
                self.assertGreaterEqual(deadline - previous, 180 * SECOND)
                self.assertLessEqual(deadline - previous, 420 * SECOND)
                event.advance(deadline - 1, deadline - 1)
                self.assertIsNone(event.current())
                event.advance(deadline, deadline)
                self.assertEqual(event.current(), dict(generation=generation,
                                 progress=0.0, strength=0.0, calm=False))
                move(event, 24)
                self.assertIsNone(event.current())
                self.assertAlmostEqual(event.smoke_lift, ((generation + 1) * 2.4) % 11)
                previous = deadline

    def test_busy_deadlines_skip_without_changing_cadence_or_creating_backlog(self):
        flowing, busy = controller(), controller()
        for _ in range(6):
            deadline = flowing.deadline
            flowing.advance(deadline, deadline)
            busy.advance(deadline, 0)
            self.assertEqual(flowing.deadline, busy.deadline)
        self.assertEqual(busy.current()['generation'], 0)
        self.assertEqual(busy.current()['progress'], 0)
        # Let the stalled episode retire without advancing active time.
        busy.advance(busy.elapsed_ns, 24 * SECOND)
        self.assertIsNone(busy.current())
        self.assertAlmostEqual(busy.smoke_lift, 2.4)
        move(busy, 1)
        self.assertIsNone(busy.current())
        self.assertEqual(busy.deadline, flowing.deadline)
        arrive(busy)
        self.assertEqual(busy.current()['generation'], 1)
        self.assertEqual(busy.current()['progress'], 0)

    def test_completion_at_a_deadline_retires_before_new_birth(self):
        event = controller()
        arrive(event, rate=0)
        event.advance(event.deadline, 24 * SECOND, calm=True)
        self.assertEqual(event.current(), dict(generation=1, progress=0.0,
                                               strength=0.0, calm=True))
        self.assertAlmostEqual(event.smoke_lift, 2.4)

    def test_birth_profile_survives_live_calm_toggles_in_both_directions(self):
        for birth_calm, duration, total in ((False, 24, 2.4), (True, 32, .8)):
            event = controller()
            arrive(event, calm=birth_calm)
            move(event, duration // 2, calm=not birth_calm)
            pose = event.current()
            self.assertEqual(pose['calm'], birth_calm)
            self.assertEqual(pose['progress'], .5)
            self.assertEqual(pose['strength'], 1)
            self.assertAlmostEqual(event.smoke_lift, total / 2)
            move(event, duration // 2, calm=not birth_calm)
            self.assertIsNone(event.current())
            self.assertAlmostEqual(event.smoke_lift, total)
            arrive(event, calm=not birth_calm)
            self.assertEqual(event.current()['calm'], not birth_calm)
            next_duration = 24 if birth_calm else 32
            move(event, next_duration - 1, calm=birth_calm)
            self.assertIsNotNone(event.current())
            move(event, 1, calm=birth_calm)
            self.assertIsNone(event.current())

    def test_strength_is_soft_at_both_boundaries_and_symmetric(self):
        event = controller()
        arrive(event)
        self.assertEqual(event.current()['strength'], 0.0)
        move(event, Fraction(1, SECOND))
        self.assertLess(event.current()['strength'], 1e-18)
        move(event, Fraction(6) - Fraction(1, SECOND))
        rising = event.current()['strength']
        self.assertAlmostEqual(rising, .5)
        move(event, 6)
        self.assertEqual(event.current()['strength'], 1.0)
        move(event, 6)
        self.assertAlmostEqual(event.current()['strength'], rising)
        move(event, Fraction(6) - Fraction(1, SECOND))
        self.assertLess(event.current()['strength'], 1e-18)
        move(event, Fraction(1, SECOND))
        self.assertIsNone(event.current())

    def test_buoyancy_is_monotone_and_phase_does_not_rewind_at_completion(self):
        for calm, duration, total in ((False, 24, 2.4), (True, 32, .8)):
            event = controller()
            previous_lift = event.smoke_lift
            unwrapped = 0.0
            # Cross the modulo boundary repeatedly, in both motion profiles.
            for generation in range(18):
                arrive(event, calm=calm)
                start_lift = event.smoke_lift
                self.assertAlmostEqual(start_lift, previous_lift)
                for _ in range(duration * 4):
                    move(event, Fraction(1, 4), calm=not calm)
                    lift = event.smoke_lift
                    delta = (lift - previous_lift) % 11
                    self.assertLess(delta, .1)
                    self.assertGreaterEqual(delta, 0)
                    unwrapped += delta
                    self.assertGreaterEqual(lift, 0)
                    self.assertLess(lift, 11)
                    previous_lift = lift
                self.assertIsNone(event.current())
                self.assertAlmostEqual(unwrapped, total * (generation + 1))
                before = event.smoke_lift
                move(event, Fraction(1, SECOND), calm=calm)
                self.assertEqual(event.smoke_lift, before)

    def test_added_rise_matches_integrated_strength_and_starts_with_zero_velocity(self):
        event = controller()
        arrive(event)
        move(event, 6)
        self.assertAlmostEqual(event.smoke_lift, 2.4 * (.25 - 1 / math.tau))
        move(event, 6)
        self.assertAlmostEqual(event.smoke_lift, 1.2)
        move(event, 6)
        self.assertAlmostEqual(event.smoke_lift, 2.4 * (.75 + 1 / math.tau))
        move(event, Fraction(6) - Fraction(1, 1000))
        before = event.smoke_lift
        move(event, Fraction(1, 1000))
        self.assertLess(abs(event.smoke_lift - before), 1e-11)
        self.assertAlmostEqual(event.smoke_lift, 2.4)

    def test_exact_rational_frame_partitions_preserve_speed_history(self):
        outcomes = []
        for quantum in (None, 17 * SECOND, Fraction(SECOND, 7)):
            event = controller()
            for duration, rate, calm in ((1300 * SECOND, Fraction(1, 50), False),
                                         (900 * SECOND, Fraction(3, 2), True),
                                         (211 * SECOND, Fraction(1, 3), False)):
                remaining = duration
                while remaining:
                    delta = remaining if quantum is None else min(remaining, quantum)
                    event.advance(event.elapsed_ns + delta,
                                  event.motion_ns + delta * rate, calm=calm)
                    remaining -= delta
            outcomes.append((event.current(), event.smoke_lift, event.deadline))
        self.assertEqual(outcomes[0], outcomes[1])
        self.assertEqual(outcomes[0], outcomes[2])

    def test_observation_is_pure_and_detached_and_does_not_perturb_rng(self):
        global_state = random.getstate()
        untouched, observed = controller(), controller()
        for _ in range(5):
            arrive(untouched)
            arrive(observed)
            move(untouched, 7)
            move(observed, 7)
            expected = untouched.current()
            for _ in range(30):
                pose = observed.current()
                self.assertEqual(pose, expected)
                pose['progress'] = 123
                self.assertEqual(observed.smoke_lift, untouched.smoke_lift)
            move(untouched, 17)
            move(observed, 17)
            self.assertEqual(observed.deadline, untouched.deadline)
        self.assertEqual(random.getstate(), global_state)
        with self.assertRaises(AttributeError):
            observed.smoke_lift = 0

    def test_constructor_clocks_are_a_fresh_scene_origin_not_an_implicit_replay(self):
        fresh = controller()
        offset = VolcanoPuffs(generate_layout(17, {}).volcano_puff_seed,
                              900 * SECOND, 517 * SECOND)
        self.assertEqual(offset.deadline - 900 * SECOND, fresh.deadline)
        self.assertIsNone(offset.current())
        self.assertEqual(offset.smoke_lift, 0)
        arrive(offset)
        self.assertEqual(offset.current()['generation'], 0)
        self.assertEqual(offset.current()['progress'], 0)


class VolcanoWorld(unittest.TestCase):
    def advance(self, world, duration):
        remaining = Fraction(duration)
        while remaining:
            delta = min(remaining, SECOND // 4)
            world.advance(delta)
            remaining -= delta

    def active_world(self, *, calm=False, speed=1):
        config = settings({'seed': 17, 'motion': {'speed': speed, 'reducedMotion': calm}})
        first = controller().deadline
        world = World(config, first + 6 * SECOND, visitor_seed=23)
        self.assertIsNotNone(world.snapshot()['volcano_puff'])
        return world

    def test_initial_history_replays_live_and_completed_scenery_without_cast_history(self):
        for calm, speed in ((False, Fraction(5, 4)), (True, Fraction(1, 2))):
            config = settings({'seed': 17, 'motion': {'speed': float(speed), 'reducedMotion': calm},
                               'population': {'maxVisible': 1}})
            # Begin just before the first deadline to exercise actual World.advance.
            first = controller().deadline
            live = World(config, first - SECOND, visitor_seed=23)
            self.advance(live, 8 * SECOND)
            replay = World(config, first + 7 * SECOND, visitor_seed=23)
            self.assertEqual(live.snapshot()['volcano_puff'], replay.snapshot()['volcano_puff'])
            self.assertEqual(live.snapshot()['smoke_lift'], replay.snapshot()['smoke_lift'])
            self.assertEqual(live.volcano_puffs.deadline, replay.volcano_puffs.deadline)
            target = first + 150 * SECOND
            historical = World(config, target, visitor_seed=23)
            self.assertIsNone(historical.snapshot()['volcano_puff'])
            self.assertAlmostEqual(historical.snapshot()['smoke_lift'], .8 if calm else 2.4)

    def test_pause_reload_presets_resize_and_density_keep_active_profile(self):
        world = self.active_world()
        original = world.snapshot()
        world.paused = True
        world.advance(SECOND // 4)
        self.assertEqual(world.snapshot(), original)
        config = copy.deepcopy(world.config)
        config['preset'] = 'dusk'
        config['motion']['reducedMotion'] = True
        config['motion']['speed'] = .25
        config['scenery']['cloudDensity'] = 0
        config['scenery']['treeDensity'] = 2
        config['population']['maxVisible'] = 1
        world.reconfigure(config)
        for view in ((0, 0, 10, 20), (-100, -10, 300, 90), (23, 0, 123, 60)):
            world.set_viewport(view)
            snapshot = world.snapshot()
            self.assertEqual(snapshot['volcano_puff'], original['volcano_puff'])
            self.assertEqual(snapshot['smoke_lift'], original['smoke_lift'])
            self.assertEqual(snapshot['time'], original['time'])
        world.advance(SECOND // 4)
        self.assertEqual(world.snapshot()['volcano_puff'], original['volcano_puff'])
        world.paused = False
        self.advance(world, SECOND)
        pose = world.snapshot()['volcano_puff']
        self.assertFalse(pose['calm'])
        self.assertAlmostEqual(pose['progress'], 6.25 / 24)
        config = copy.deepcopy(world.config)
        config['motion']['speed'] = 2
        world.reconfigure(config)
        self.assertEqual(world.snapshot()['volcano_puff'], pose)
        self.advance(world, SECOND)
        self.assertAlmostEqual(world.snapshot()['volcano_puff']['progress'], 8.25 / 24)

    def test_speed_changes_keep_completed_lift_and_next_birth_captures_calm(self):
        world = self.active_world()
        config = copy.deepcopy(world.config)
        config['motion']['speed'] = 2
        config['motion']['reducedMotion'] = True
        world.reconfigure(config)
        self.advance(world, 9 * SECOND)
        self.assertIsNone(world.snapshot()['volcano_puff'])
        self.assertAlmostEqual(world.snapshot()['smoke_lift'], 2.4)
        self.advance(world, world.volcano_puffs.deadline - world.elapsed_ns)
        self.assertEqual(world.snapshot()['volcano_puff'],
                         dict(generation=1, progress=0.0, strength=0.0, calm=True))
        self.advance(world, 8 * SECOND)
        pose = world.snapshot()['volcano_puff']
        self.assertEqual(pose['progress'], .5)
        self.assertAlmostEqual(world.snapshot()['smoke_lift'], 2.8)
        self.advance(world, 8 * SECOND)
        self.assertIsNone(world.snapshot()['volcano_puff'])
        self.assertAlmostEqual(world.snapshot()['smoke_lift'], 3.2)

    def test_scene_seed_change_alone_resets_schedule_without_retiming_world(self):
        world = self.active_world()
        config = copy.deepcopy(world.config)
        config['seed'] = 2026
        before_time = world.snapshot()['time']
        elapsed = world.elapsed_ns
        world.reconfigure(config)
        expected = VolcanoPuffs(world.layout.volcano_puff_seed,
                                elapsed, Fraction(str(before_time)) * SECOND)
        self.assertEqual(world.snapshot()['time'], before_time)
        self.assertEqual(world.elapsed_ns, elapsed)
        self.assertIsNone(world.snapshot()['volcano_puff'])
        self.assertEqual(world.snapshot()['smoke_lift'], 0)
        self.assertEqual(world.volcano_puffs.deadline, expected.deadline)
        self.advance(world, expected.deadline - elapsed)
        self.assertEqual(world.snapshot()['volcano_puff']['generation'], 0)
        self.assertEqual(world.snapshot()['volcano_puff']['progress'], 0)

    def test_cloud_density_and_animal_budget_do_not_gate_or_reseed_puffs(self):
        sparse = settings({'seed': 17, 'scenery': {'cloudDensity': 0},
                           'animals': {key: False for key in settings()['animals']},
                           'population': {'maxVisible': 1}})
        crowded = settings({'seed': 17, 'scenery': {'cloudDensity': 2},
                            'population': {'maxVisible': 128}})
        first = controller().deadline
        worlds = [World(config, first - SECOND, visitor_seed=23)
                  for config in (sparse, crowded)]
        for seconds in (1, 6, 6, 12):
            for world in worlds:
                self.advance(world, seconds * SECOND)
            snapshots = [world.snapshot() for world in worlds]
            self.assertEqual(snapshots[0]['volcano_puff'], snapshots[1]['volcano_puff'])
            self.assertEqual(snapshots[0]['smoke_lift'], snapshots[1]['smoke_lift'])
            self.assertEqual(worlds[0].volcano_puffs.deadline, worlds[1].volcano_puffs.deadline)
        self.assertIsNone(worlds[0].snapshot()['volcano_puff'])
        self.assertAlmostEqual(worlds[0].snapshot()['smoke_lift'], 2.4)
        self.assertEqual(worlds[0].layout.volcano_puff_seed, worlds[1].layout.volcano_puff_seed)


if __name__ == '__main__':
    unittest.main()
