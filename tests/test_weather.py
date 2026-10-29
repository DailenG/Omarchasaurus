import copy
from fractions import Fraction
from pathlib import Path
import random
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from configuration import settings
from cast import cast_groups
from engine import World
from layout import HORIZON_Y, RainDrop, generate_layout
from weather import SECOND, ValleyWeather


def controller(seed=17):
    layout = generate_layout(seed, {})
    return ValleyWeather(layout.rain_drops, layout.weather_seed)


def arrive(event, *, calm=False, rate=1):
    event.advance(event.deadline,
                  event.motion_ns + (event.deadline - event.elapsed_ns) * rate,
                  calm=calm)


def move(event, seconds, *, calm=False, rate=1):
    delta = Fraction(seconds) * SECOND
    event.advance(event.elapsed_ns + delta, event.motion_ns + delta * rate, calm=calm)


def at_age(event, age, *, calm=False):
    move(event, Fraction(age) - Fraction(str(event.current()['age'])), calm=calm)
    return event.current()


class WeatherLifecycle(unittest.TestCase):
    def test_rare_active_time_cadence_and_seeded_sequence_repeat(self):
        sequences = []
        for seed in (0, 1, 17, 2026, 2**53 - 1):
            event, repeated = controller(seed), controller(seed)
            deadlines = []
            previous = 0
            for generation in range(12):
                deadline = event.deadline
                self.assertGreaterEqual(deadline - previous, 600 * SECOND)
                self.assertLessEqual(deadline - previous, 900 * SECOND)
                event.advance(deadline - 1, deadline - 1)
                self.assertIsNone(event.current())
                event.advance(deadline, deadline)
                repeated.advance(deadline, deadline)
                pose = event.current()
                self.assertEqual(pose, repeated.current())
                self.assertEqual(pose['generation'], generation)
                self.assertEqual(pose['age'], 0)
                self.assertEqual(pose['state'], 'shower')
                deadlines.append(deadline)
                move(event, 66)
                move(repeated, 66)
                self.assertIsNone(event.current())
                previous = deadline
            sequences.append(tuple(deadlines))
        self.assertEqual(len(set(sequences)), len(sequences))

    def test_complete_normal_and_calm_stages_have_soft_visible_endpoints(self):
        for calm, stop, clear, end in ((False, 22, 30, 66), (True, 28, 42, 90)):
            with self.subTest(calm=calm):
                event = controller()
                arrive(event, calm=calm)
                initial = event.current()
                for key in ('cloud_strength', 'rain_strength', 'rainbow_strength'):
                    self.assertEqual(initial[key], 0)
                self.assertEqual(initial['rain'], ())
                early = at_age(event, Fraction(1, 1000), calm=calm)
                self.assertGreater(early['cloud_strength'], 0)
                self.assertLess(early['cloud_strength'], 1e-6)
                raining = at_age(event, 23 if calm else 15, calm=calm)
                self.assertEqual(raining['state'], 'shower')
                self.assertEqual(raining['cloud_strength'], 1)
                self.assertTrue(raining['rain'])
                clearing = at_age(event, stop, calm=calm)
                self.assertEqual(clearing['state'], 'clearing')
                self.assertTrue(clearing['rain'])
                almost_clear = at_age(event, Fraction(clear) - Fraction(1, 1000), calm=calm)
                self.assertEqual(almost_clear['rain'], ())
                self.assertLess(almost_clear['cloud_strength'], 1e-6)
                rainbow = at_age(event, clear, calm=calm)
                self.assertEqual(rainbow['state'], 'rainbow')
                self.assertEqual(rainbow['cloud_strength'], 0)
                self.assertEqual(rainbow['rain_strength'], 0)
                self.assertEqual(rainbow['rainbow_strength'], 0)
                self.assertEqual(rainbow['rain'], ())
                growing = at_age(event, clear + Fraction(1, 1000), calm=calm)
                self.assertGreater(growing['rainbow_strength'], 0)
                self.assertLess(growing['rainbow_strength'], 1e-6)
                full = at_age(event, clear + (8 if calm else 4), calm=calm)
                self.assertEqual(full['rainbow_strength'], 1)
                held = at_age(event, end - (12 if calm else 8), calm=calm)
                self.assertEqual(held['rainbow_strength'], 1)
                ending = at_age(event, Fraction(end) - Fraction(1, 1000), calm=calm)
                self.assertLess(ending['rainbow_strength'], 1e-6)
                self.assertEqual(ending['rain'], ())
                at_age(event, end, calm=calm)
                self.assertIsNone(event.current())

    def test_busy_deadlines_skip_and_never_queue_or_reseed_intervals(self):
        running, stalled = controller(), controller()
        for _ in range(20):
            deadline = running.deadline
            running.advance(deadline, deadline)
            stalled.advance(deadline, 0)
            self.assertEqual(running.deadline, stalled.deadline)
        self.assertEqual(stalled.current()['generation'], 0)
        self.assertEqual(stalled.current()['age'], 0)
        stalled.advance(stalled.elapsed_ns, 66 * SECOND)
        self.assertIsNone(stalled.current())
        move(stalled, 1)
        self.assertIsNone(stalled.current())
        arrive(stalled)
        self.assertEqual(stalled.current()['generation'], 1)
        self.assertEqual(stalled.current()['age'], 0)

    def test_simultaneous_finish_and_deadline_retires_before_next_birth(self):
        event = controller()
        arrive(event, rate=0)
        event.advance(event.deadline, 66 * SECOND, calm=True)
        self.assertEqual(event.current()['generation'], 1)
        self.assertEqual(event.current()['age'], 0)
        self.assertTrue(event.current()['calm'])

    def test_profile_is_captured_at_birth_in_both_toggle_directions(self):
        for calm, duration in ((False, 66), (True, 90)):
            event, unchanged = controller(), controller()
            arrive(event, calm=calm)
            arrive(unchanged, calm=calm)
            for age in (3, 15, 23, 29, 43, duration - 1):
                self.assertEqual(at_age(event, age, calm=not calm),
                                 at_age(unchanged, age, calm=calm))
            at_age(event, duration, calm=not calm)
            self.assertIsNone(event.current())
            arrive(event, calm=not calm)
            self.assertEqual(event.current()['calm'], not calm)

    def test_exact_clock_partitions_preserve_piecewise_speed_and_profile_history(self):
        outcomes = []
        for quantum in (None, 173 * SECOND, Fraction(SECOND, 3)):
            event = controller()
            for duration, rate, calm in ((5000 * SECOND, Fraction(1, 100), False),
                                         (2200 * SECOND, Fraction(3, 2), True),
                                         (900 * SECOND, Fraction(1, 3), False)):
                remaining = duration
                while remaining:
                    delta = remaining if quantum is None else min(remaining, quantum)
                    event.advance(event.elapsed_ns + delta,
                                  event.motion_ns + delta * rate, calm=calm)
                    remaining -= delta
            outcomes.append((event.current(), event.deadline, event.generation))
        self.assertEqual(outcomes[0], outcomes[1])
        self.assertEqual(outcomes[0], outcomes[2])

    def test_snapshots_are_detached_pure_and_rng_isolated(self):
        state = random.getstate()
        untouched, observed = controller(), controller()
        for _ in range(5):
            arrive(untouched)
            arrive(observed)
            move(untouched, 15)
            move(observed, 15)
            expected = untouched.current()
            rng_state = observed.rng.getstate()
            for _ in range(20):
                pose = observed.current()
                self.assertEqual(pose, expected)
                pose['age'] = 999
                pose['rain'][0]['head'] = (999, 999)
            self.assertEqual(observed.rng.getstate(), rng_state)
            self.assertEqual(observed.current(), expected)
            move(untouched, 51)
            move(observed, 51)
            self.assertEqual(observed.deadline, untouched.deadline)
        self.assertEqual(random.getstate(), state)

    def test_constructor_clocks_are_fresh_origin_and_recurrence_has_bounded_state(self):
        layout = generate_layout(17, {})
        fresh = controller()
        offset = ValleyWeather(layout.rain_drops, layout.weather_seed,
                               4000 * SECOND, 1234 * SECOND)
        self.assertEqual(offset.deadline - 4000 * SECOND, fresh.deadline)
        self.assertIsNone(offset.current())
        original_fields = set(vars(offset))
        for generation in range(150):
            arrive(offset, calm=generation % 2 == 1)
            self.assertEqual(offset.current()['generation'], generation)
            self.assertLessEqual(len(offset.current()['rain']), 48)
            move(offset, 90)
            self.assertIsNone(offset.current())
            self.assertEqual(set(vars(offset)), original_fields)
            # Apart from the fixed candidate tuple there is no event/drop history.
            for value in vars(offset).values():
                if isinstance(value, (list, tuple, dict, set)):
                    self.assertLessEqual(len(value), 48)


class WeatherRain(unittest.TestCase):
    def test_every_seed_drains_before_rainbow_and_stays_within_sky(self):
        for seed in (*range(64), 2**53 - 1):
            for calm, stop, clear in ((False, 22, 30), (True, 28, 42)):
                event = controller(seed)
                arrive(event, calm=calm)
                max_count = 0
                for quarter in range(clear * 4 + 1):
                    pose = at_age(event, Fraction(quarter, 4), calm=calm)
                    rain = pose['rain']
                    max_count = max(max_count, len(rain))
                    self.assertLessEqual(len(rain), 16 if calm else 48)
                    self.assertEqual(len({(drop['id'], drop['cycle']) for drop in rain}), len(rain))
                    for drop in rain:
                        self.assertGreaterEqual(drop['tail'][1], pose['cloud_y'])
                        self.assertGreaterEqual(drop['head'][1], drop['tail'][1])
                        self.assertLessEqual(drop['head'][1], HORIZON_Y)
                    if quarter / 4 >= stop + (8.28 if calm else 4.6):
                        self.assertEqual(rain, ())
                self.assertEqual(max_count, 16 if calm else 48)
                self.assertEqual(pose['state'], 'rainbow')
                self.assertEqual(pose['rain'], ())

    def test_natural_birth_admission_never_materializes_halfway_down(self):
        drops = tuple(RainDrop(f'drop:{index}', index / 48, 0, 4, .1, .8)
                      for index in range(48))
        event = ValleyWeather(drops, 123)
        arrive(event)
        # All candidates were born at age 4, when birth intensity is still zero.
        for age in (4, 5, 6, 7, Fraction(7999, 1000)):
            self.assertEqual(at_age(event, age)['rain'], ())
        born = at_age(event, 8)
        self.assertTrue(born['rain'])
        identities = {(drop['id'], drop['cycle']) for drop in born['rain']}
        for drop in born['rain']:
            self.assertEqual(drop['head'][1], 8.5)
            self.assertEqual(drop['tail'][1], 8.5)
        for age in (9, 10, 11, Fraction(11999, 1000)):
            falling = at_age(event, age)
            self.assertEqual({(drop['id'], drop['cycle']) for drop in falling['rain']}, identities)
        # At age 20 the taper admits a subset. Later intensity must not delete it.
        admitted = at_age(event, 20)['rain']
        later = at_age(event, Fraction(21999, 1000))['rain']
        self.assertTrue(admitted)
        self.assertEqual([(drop['id'], drop['cycle']) for drop in admitted],
                         [(drop['id'], drop['cycle']) for drop in later])

    def test_a_drop_keeps_birth_cloud_origin_and_its_full_fall_period(self):
        for calm, age in ((False, 15), (True, 23)):
            event = controller()
            arrive(event, calm=calm)
            first = at_age(event, age, calm=calm)
            second = at_age(event, Fraction(age) + Fraction(1, 100), calm=calm)
            descriptors = {drop.id: drop for drop in event.descriptors}
            newer = {(drop['id'], drop['cycle']): drop for drop in second['rain']}
            checked = 0
            for drop in first['rain']:
                following = newer.get((drop['id'], drop['cycle']))
                if following is None:
                    continue
                descriptor = descriptors[drop['id']]
                dy = following['head'][1] - drop['head'][1]
                period = descriptor.period * (1.8 if calm else 1)
                self.assertAlmostEqual(dy, (HORIZON_Y - 8.5) * .01 / period)
                slant = descriptor.slant * (.65 if calm else 1)
                self.assertAlmostEqual(following['head'][0] - drop['head'][0], slant * dy)
                self.assertLessEqual(drop['head'][1] - drop['tail'][1],
                                     descriptor.length * (.65 if calm else 1) + 1e-12)
                checked += 1
            self.assertGreater(checked, 0)
            if calm:
                self.assertLessEqual({drop['id'] for drop in first['rain']},
                                     {drop.id for drop in event.descriptors[:16]})


class WeatherWorld(unittest.TestCase):
    def advance(self, world, duration):
        remaining = Fraction(duration)
        while remaining:
            delta = min(remaining, SECOND // 4)
            world.advance(delta)
            remaining -= delta

    def active_world(self, *, calm=False, speed=1, age=15):
        config = settings({'seed': 17, 'motion': {'speed': speed, 'reducedMotion': calm}})
        first = controller().deadline
        return World(config, first + Fraction(age) * SECOND / Fraction(str(speed)), visitor_seed=23)

    def test_initial_history_matches_real_world_advancement_for_both_profiles(self):
        for calm, speed in ((False, Fraction(5, 4)), (True, Fraction(1, 2))):
            config = settings({'seed': 17,
                               'motion': {'speed': float(speed), 'reducedMotion': calm},
                               'population': {'maxVisible': 1}})
            first = controller().deadline
            live = World(config, first - SECOND, visitor_seed=23)
            self.advance(live, 8 * SECOND)
            replay = World(config, first + 7 * SECOND, visitor_seed=23)
            self.assertEqual(live.snapshot()['weather'], replay.snapshot()['weather'])
            self.assertEqual(live.weather.deadline, replay.weather.deadline)
            historical = World(config, first + 200 * SECOND, visitor_seed=23)
            self.assertIsNone(historical.snapshot()['weather'])

    def test_real_world_completes_every_stage_without_animal_occupancy_effects(self):
        for calm, stop, clear, end in ((False, 22, 30, 66), (True, 28, 42, 90)):
            config = settings({'seed': 17, 'motion': {'reducedMotion': calm},
                               'population': {'maxVisible': 1},
                               'scenery': {'cloudDensity': 0}})
            world = World(config, controller().deadline, visitor_seed=23)
            previous = 0
            for age, state in ((15, 'shower'), (stop, 'clearing'),
                               (clear + 1, 'rainbow')):
                self.advance(world, (age - previous) * SECOND)
                snapshot = world.snapshot()
                self.assertEqual(snapshot['weather']['state'], state)
                without_weather = snapshot | {'weather': None}
                self.assertEqual(cast_groups(snapshot, config, (23, 0, 123, 60)),
                                 cast_groups(without_weather, config, (23, 0, 123, 60)))
                self.assertLessEqual(len(snapshot['admitted']), 1)
                previous = age
            self.advance(world, (end - previous) * SECOND)
            self.assertIsNone(world.snapshot()['weather'])

    def test_pause_reload_resize_density_and_ceiling_preserve_lifecycle_and_profile(self):
        for calm in (False, True):
            world = self.active_world(calm=calm)
            original = world.snapshot()['weather']
            deadline = world.weather.deadline
            elapsed = world.elapsed_ns
            world.paused = True
            self.advance(world, SECOND)
            self.assertEqual(world.snapshot()['weather'], original)
            self.assertEqual(world.elapsed_ns, elapsed)
            config = copy.deepcopy(world.config)
            config['preset'] = 'dusk'
            config['motion']['reducedMotion'] = not calm
            config['motion']['speed'] = .25
            config['scenery']['cloudDensity'] = 0
            config['scenery']['treeDensity'] = 2
            config['population']['maxVisible'] = 1
            world.reconfigure(config)
            for bounds in ((0, 0, 10, 20), (-100, -10, 300, 90), (23, 0, 123, 60)):
                world.set_viewport(bounds)
                self.assertEqual(world.snapshot()['weather'], original)
                self.assertEqual(world.weather.deadline, deadline)
            world.paused = False
            self.advance(world, SECOND)
            pose = world.snapshot()['weather']
            self.assertEqual(pose['calm'], calm)
            self.assertAlmostEqual(pose['age'], original['age'] + .25)
            config['motion']['speed'] = 2
            world.reconfigure(config)
            self.assertEqual(world.snapshot()['weather'], pose)
            self.advance(world, SECOND)
            self.assertAlmostEqual(world.snapshot()['weather']['age'], original['age'] + 2.25)

    def test_only_scene_seed_establishes_a_fresh_origin_without_overlay(self):
        world = self.active_world()
        old = world.weather
        config = copy.deepcopy(world.config)
        config['seed'] = 2026
        elapsed, motion = world.elapsed_ns, world._motion_ns
        world.reconfigure(config)
        self.assertIsNot(world.weather, old)
        self.assertIsNone(world.snapshot()['weather'])
        fresh = controller(2026)
        self.assertEqual(world.weather.deadline - elapsed, fresh.deadline)
        self.assertEqual(world.weather.motion_ns, motion)
        world.reconfigure(copy.deepcopy(config))
        self.assertEqual(world.weather.deadline - elapsed, fresh.deadline)
        self.assertIsNone(world.snapshot()['weather'])

    def test_cloud_zero_ceiling_one_and_disabled_animals_cannot_suppress_weather(self):
        first = controller().deadline
        baseline = settings({'seed': 17, 'population': {'maxVisible': 128}})
        sparse = copy.deepcopy(baseline)
        sparse['scenery'] = {key: (False if isinstance(value, bool) else 0)
                              for key, value in sparse['scenery'].items()}
        sparse['population']['maxVisible'] = 1
        for key in sparse['animals']:
            sparse['animals'][key] = False
        full = World(baseline, first + 15 * SECOND, visitor_seed=23)
        empty = World(sparse, first + 15 * SECOND, visitor_seed=23)
        self.assertEqual(full.snapshot()['weather'], empty.snapshot()['weather'])
        self.assertEqual(empty.layout.clouds, ())
        self.assertLessEqual(len(empty.snapshot()['admitted']), 1)
        self.assertFalse(any(actor.startswith('rain') for actor in full.snapshot()['admitted']))
        # Weather observation cannot affect Cast, nor can playful clicks retime rain.
        admitted = full.snapshot()['admitted']
        for _ in range(10):
            full.weather.current()
        self.assertEqual(full.snapshot()['admitted'], admitted)
        full.spawn_meteor(40, 4)
        full.spawn_water_jump(50, 42)
        self.assertEqual(full.snapshot()['weather'], empty.snapshot()['weather'])
        self.assertIsNotNone(full.snapshot()['meteor'])
        self.assertIsNotNone(full.snapshot()['water_jump'])

    def test_world_snapshot_reads_do_not_change_other_event_streams(self):
        first = controller().deadline
        config = settings({'seed': 17})
        observed = World(config, first + 15 * SECOND, visitor_seed=23)
        untouched = World(config, first + 15 * SECOND, visitor_seed=23)
        for _ in range(30):
            observed.snapshot()
        self.advance(observed, SECOND)
        self.advance(untouched, SECOND)
        self.assertEqual(observed.snapshot(), untouched.snapshot())
        self.assertEqual(observed.weather.deadline, untouched.weather.deadline)
        self.assertEqual(observed.volcano_puffs.deadline, untouched.volcano_puffs.deadline)


if __name__ == '__main__':
    unittest.main()
