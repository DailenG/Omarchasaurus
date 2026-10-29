from dataclasses import FrozenInstanceError, asdict, fields
import json
import math
import os
from pathlib import Path
import random
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from layout import generate_layout


CATEGORIES = {
    'clouds': ('cloudDensity', 3),
    'trees': ('treeDensity', 10),
    'ferns': ('fernDensity', 4),
    'rocks': ('rockDensity', 2),
    'cycads': ('cycadDensity', 3),
    'flowers': ('flowerDensity', 6),
    'lily_pads': ('lilyPadDensity', 6),
}
SCENERY = {key: 1.0 for key, _ in CATEGORIES.values()}
PHASES = (
    'wind_phase', 'smoke_phase', 'brachiosaurus_phase', 'trex_phase',
    'brachiosaurus_blink_phase', 'trex_blink_phase',
    'triceratops_phase', 'stegosaurus_phase', 'ankylosaurus_phase',
    'hatching_phase',
)
SEEDS = (0, 1, 17, 2026, 2**53 - 1)


class LayoutSelection(unittest.TestCase):
    def test_disabled_and_maximum_counts_are_bounded(self):
        for seed in SEEDS:
            for density in (0, 2):
                with self.subTest(seed=seed, density=density):
                    layout = generate_layout(
                        seed, {key: density for key in SCENERY})
                    for category, (_, normal_count) in CATEGORIES.items():
                        self.assertEqual(len(getattr(layout, category)),
                                         density * normal_count)
                    self.assertEqual(len(layout.ripples), 28)

    def test_density_increases_preserve_every_existing_pose(self):
        densities = (0, .01, .125, .25, .5, .75, .99, 1,
                     1.25, 1.5, 1.75, 1.99, 2)
        for seed in SEEDS:
            for category, (key, normal_count) in CATEGORIES.items():
                previous = {}
                maximum = getattr(generate_layout(seed, {key: 2}), category)
                all_poses = {pose.id: pose for pose in maximum}
                for density in densities:
                    with self.subTest(seed=seed, category=category,
                                      density=density):
                        poses = getattr(generate_layout(seed, {key: density}),
                                        category)
                        current = {pose.id: pose for pose in poses}
                        self.assertEqual(len(current), len(poses))
                        self.assertLessEqual(previous.keys(), current.keys())
                        for identity, pose in current.items():
                            self.assertEqual(pose, all_poses[identity])
                        for identity, pose in previous.items():
                            self.assertEqual(pose, current[identity])
                        previous = current

    def test_changing_one_density_leaves_every_other_layout_field_unchanged(self):
        for seed in SEEDS:
            baseline = generate_layout(seed, SCENERY)
            for category, (key, _) in CATEGORIES.items():
                for density in (0, .5, 1.5, 2):
                    with self.subTest(seed=seed, category=category,
                                      density=density):
                        changed = generate_layout(seed, SCENERY | {key: density})
                        for field in fields(baseline):
                            if field.name != category:
                                self.assertEqual(getattr(baseline, field.name),
                                                 getattr(changed, field.name),
                                                 field.name)

    def test_nest_toggle_preserves_every_other_pose_and_reenables_same_nest(self):
        for seed in SEEDS:
            enabled = generate_layout(seed, SCENERY | {'nestEnabled': True})
            disabled = generate_layout(seed, SCENERY | {'nestEnabled': False})
            self.assertIsNone(disabled.nest)
            self.assertEqual(enabled.nest, generate_layout(seed, SCENERY).nest)
            for field in fields(enabled):
                if field.name != 'nest':
                    self.assertEqual(getattr(enabled, field.name),
                                     getattr(disabled, field.name))


    def test_layout_and_every_pose_are_immutable(self):
        layout = generate_layout(17, SCENERY)
        objects = [layout, layout.nest]
        for category in (*CATEGORIES, 'ripples', 'pteranodons', 'pteranodon_flock',
                         'rain_drops'):
            poses = getattr(layout, category)
            self.assertIsInstance(poses, tuple)
            objects.extend(poses)
        for value in objects:
            field = fields(value)[0]
            with self.assertRaises(FrozenInstanceError):
                setattr(value, field.name, getattr(value, field.name))


class LayoutHabitats(unittest.TestCase):
    def bounded(self, value, low, high):
        self.assertGreaterEqual(value, low)
        self.assertLessEqual(value, high)

    def test_full_candidate_pools_obey_terrain_and_focal_exclusions(self):
        maximum = {key: 2 for key in SCENERY}
        for seed in (*range(64), 2**53 - 1):
            with self.subTest(seed=seed):
                layout = generate_layout(seed, maximum)
                for cloud in layout.clouds:
                    self.bounded(cloud.x, -15, 125)
                    self.bounded(cloud.y, 4, 9)
                    self.bounded(cloud.size, 6, 10)
                    self.bounded(cloud.speed, .06, .18)
                for tree in layout.trees:
                    self.bounded(tree.x, -8, 125)
                    self.bounded(tree.base, 35.5, 36.5)
                    self.bounded(tree.height, 6, 10)
                trunks = sorted(tree.x for tree in layout.trees)
                self.assertTrue(all(right - left >= 4
                                    for left, right in zip(trunks, trunks[1:])))
                for fern in layout.ferns:
                    self.bounded(fern.x, -8, 125)
                    self.bounded(fern.y, 57.8, 58.8)
                    self.bounded(fern.height, 3, 5)
                    # Covers the stem, fronds, leaflets and .22 animated sway.
                    self.assertGreaterEqual(fern.y - fern.height - .7, 50.5)
                    half_width = fern.height + .77
                    self.assertTrue(fern.x + half_width < 60 or
                                    fern.x - half_width > 90)
                for rock in layout.rocks:
                    self.bounded(rock.x, -8, 125)
                    self.bounded(rock.y, 50.5, 60)
                    self.bounded(rock.scale, .7, 1.1)
                    self.assertIn(rock.kind, ('boulder', 'pebble'))
                    # Existing silhouettes transformed about their bottom center.
                    if rock.kind == 'boulder':
                        left, right = rock.x - 6*rock.scale, rock.x + 6.2*rock.scale
                        top = rock.y - 5.8*rock.scale
                    else:
                        left, right = rock.x - 3.7*rock.scale, rock.x + 3.7*rock.scale
                        top = rock.y - 2.8*rock.scale
                    self.assertGreaterEqual(top, 50.5)
                    self.assertTrue(right < 60 or left > 90)
                left, top, right, bottom = layout.water_bounds
                for ripple in layout.ripples:
                    self.bounded(ripple.x, -4, 114)
                    self.bounded(ripple.y, 38.2, 46.5)
                    self.bounded(ripple.width, .9, 2.5)
                    self.bounded(ripple.speed, .32, .5)
                    self.assertGreaterEqual(ripple.x - .65, left)
                    self.assertLessEqual(ripple.x + ripple.width + .65, right)
                    self.assertGreaterEqual(ripple.y - .25, top)
                    self.assertLessEqual(ripple.y + .3, bottom)
                for pad in layout.lily_pads:
                    self.assertGreaterEqual(pad.x - pad.radius - .35, left)
                    self.assertLessEqual(pad.x + pad.radius + .35, right)
                    self.assertGreaterEqual(pad.y - pad.radius * .35, top)
                    self.assertLessEqual(pad.y + pad.radius * .35, bottom)
                for cycad in layout.cycads:
                    self.assertGreaterEqual(cycad.y - cycad.height, 50.5)
                    self.assertTrue(cycad.x + cycad.height + .18 < 60 or
                                    cycad.x - cycad.height - .18 > 90)
                for flower in layout.flowers:
                    self.assertGreaterEqual(flower.y - flower.height, 50.5)
                    self.bounded(flower.x - .74, -8, 125)
                    self.bounded(flower.x + .74, -8, 125)
                nest = layout.nest
                self.assertGreaterEqual(nest.y - 1.45, 50.5)
                self.assertLess(nest.x + nest.radius, 52)
                self.assertIn(nest.eggs, (3, 4))

    def test_individual_flight_and_ambient_phases_are_seeded_and_bounded(self):
        for seed in SEEDS:
            layout = generate_layout(seed, SCENERY)
            for bird in layout.pteranodons:
                self.bounded(bird.start_x, -8, 125)
                self.bounded(bird.y, 0, 30)
                self.bounded(bird.span, 2, 5)
                self.bounded(bird.depth, 0, 1)
                self.bounded(bird.speed, .01, 1)
            phases = [getattr(layout, name) for name in PHASES]
            for category in ('clouds', 'trees', 'cycads', 'ferns', 'flowers',
                             'lily_pads', 'ripples', 'pteranodons', 'pteranodon_flock'):
                phases.extend(pose.phase for pose in getattr(layout, category))
            for phase in phases:
                self.bounded(phase, 0, math.tau)
            self.assertEqual(len(set(phases)), len(phases))
            self.bounded(layout.trex_start, -2, 2)

    def test_flock_is_a_bounded_independently_phased_leader_first_v(self):
        for seed in SEEDS:
            layout = generate_layout(seed, SCENERY)
            flock = layout.pteranodon_flock
            self.assertEqual(tuple(bird.id for bird in flock),
                             tuple(f'pteranodon:{index}' for index in range(3, 8)))
            self.assertEqual(tuple(bird.start_x for bird in flock), (0, -11, -11, -22, -22))
            self.assertEqual(tuple(bird.y - 16 for bird in flock), (0, -4.5, 4.5, -9, 9))
            self.assertEqual(len({bird.phase for bird in (*layout.pteranodons, *flock)}), 8)
            self.assertTrue(all(bird.depth == .18 and bird.speed == 1.2 for bird in flock))

    def test_rain_candidates_are_bounded_seeded_and_density_independent(self):
        for seed in SEEDS:
            layout = generate_layout(seed, SCENERY)
            self.assertEqual(len(layout.rain_drops), 48)
            self.assertEqual(len({drop.id for drop in layout.rain_drops}), 48)
            for drop in layout.rain_drops:
                self.bounded(drop.offset, 0, 1)
                self.bounded(drop.phase, 0, 1)
                self.bounded(drop.period, 3.2, 4.6)
                self.bounded(drop.slant, -.15, .2)
                self.bounded(drop.length, .5, 1)
            empty = generate_layout(seed, {key: 0 for key in SCENERY})
            self.assertEqual(layout.rain_drops, empty.rain_drops)
            self.assertEqual(layout.weather_seed, empty.weather_seed)
        self.assertNotEqual(generate_layout(1, SCENERY).rain_drops,
                            generate_layout(2, SCENERY).rain_drops)
        self.assertNotEqual(generate_layout(1, SCENERY).weather_seed,
                            generate_layout(2, SCENERY).weather_seed)


class LayoutReproducibility(unittest.TestCase):
    def test_same_seed_is_pure_and_does_not_mutate_input_or_global_rng(self):
        scenery = SCENERY.copy()
        original = scenery.copy()
        state = random.getstate()
        first = generate_layout(2026, scenery)
        self.assertEqual(random.getstate(), state)
        self.assertEqual(scenery, original)
        try:
            random.seed(918273)
            for _ in range(30):
                random.random()
            changed_state = random.getstate()
            second = generate_layout(2026, scenery)
            self.assertEqual(random.getstate(), changed_state)
            self.assertEqual(first, second)
        finally:
            random.setstate(state)

    def test_seed_changes_each_generated_category_and_actor(self):
        first = generate_layout(1, SCENERY)
        second = generate_layout(2, SCENERY)
        for category in (*CATEGORIES, 'ripples', 'pteranodons', 'pteranodon_flock',
                         'pteranodon_visit_seed', 'hatching_seed', 'volcano_puff_seed',
                         *PHASES, 'trex_start'):
            self.assertNotEqual(getattr(first, category), getattr(second, category),
                                category)

    def test_cross_process_and_hash_seed_reproducibility(self):
        scenery = SCENERY | {'treeDensity': 1.5, 'rockDensity': .5}
        seed = 2**53 - 1
        expected = json.dumps(asdict(generate_layout(seed, scenery)),
                              sort_keys=True, separators=(',', ':'))
        program = (
            'from dataclasses import asdict; import json; '
            'from layout import generate_layout; '
            f'print(json.dumps(asdict(generate_layout({seed}, {scenery!r})), '
            'sort_keys=True, separators=(",", ":")))'
        )
        for hash_seed in ('0', '1', '193817', 'random'):
            with self.subTest(hash_seed=hash_seed):
                env = os.environ.copy()
                env['PYTHONHASHSEED'] = hash_seed
                env['PYTHONPATH'] = str(ROOT / 'scripts')
                result = subprocess.run([sys.executable, '-c', program],
                                        env=env, capture_output=True, text=True,
                                        check=True, timeout=15)
                self.assertEqual(result.stdout.strip(), expected)


if __name__ == '__main__':
    unittest.main()
