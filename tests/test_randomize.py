import copy
from pathlib import Path
import random
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from canvas import Canvas
from character_art import visible_cast_members
from configuration import settings
from engine import World
from population import GROUND_EXTENTS
from randomize import DENSITIES, randomize_document

SECOND = 1_000_000_000


class RandomizedValley(unittest.TestCase):
    def test_choices_preserve_sparse_preferences_and_do_not_mutate_inputs(self):
        document = {
            'schemaVersion': 1, 'preset': 'dusk', 'seed': 2**53 - 1,
            'motion': {'speed': .25, 'parallaxStrength': .3, 'reducedMotion': True},
            'population': {'maxVisible': 3, 'maxFamilies': 0, 'randomVisitors': False},
            'sound': {'enabled': False, 'volume': 71},
            'integration': {'idleEnabled': False, 'exitOnPointerMotion': False},
            'animals': {'trexEnabled': False}, 'scenery': {'treeDensity': 2},
        }
        original = copy.deepcopy(document)
        rng_state = random.getstate()
        result = randomize_document(document, 37)
        self.assertEqual(document, original)
        self.assertEqual(random.getstate(), rng_state)
        self.assertEqual(result, randomize_document(document, 37))
        for key in ('schemaVersion', 'preset', 'seed', 'motion', 'sound', 'integration'):
            self.assertEqual(result[key], original[key])
        for key in ('maxVisible', 'maxFamilies'):
            self.assertEqual(result['population'][key], original['population'][key])
        self.assertTrue(result['population']['randomVisitors'])
        self.assertNotEqual(result, randomize_document(document, 38))
        result['motion']['speed'] = 2
        result['integration']['exitOnPointerMotion'] = True
        self.assertEqual(document, original)
        sparse = randomize_document({}, 37)
        self.assertEqual(set(sparse), {'scenery', 'animals', 'population'})
        self.assertEqual(sparse['population'], {'randomVisitors': True})
        self.assertEqual(settings(sparse)['seed'], settings()['seed'])

    def test_invalid_input_is_rejected_before_any_random_choices(self):
        for document in (None, [], {'preset': 'sunset'}, {'motion': {'speed': 0}},
                         {'population': {'maxVisible': True}}, {'scenery': {'treeDensity': 3}},
                         {'animals': {'diplodocusResident': 'true'}}, {'unknown': 1}):
            with self.subTest(document=document):
                original = copy.deepcopy(document)
                with self.assertRaises(ValueError):
                    randomize_document(document, 1)
                self.assertEqual(document, original)

    def test_densities_and_rotation_pool_respect_every_capacity_boundary(self):
        seen_residency, seen_nests, seen_densities = set(), set(), set()
        for maximum in (1, 2, 3, 8, 128):
            for families in (0, 1, 2):
                for seed in range(24):
                    document = {'population': {'maxVisible': maximum, 'maxFamilies': families}}
                    result = randomize_document(document, seed)
                    config = settings(result)
                    self.assertEqual(config['population']['maxVisible'], maximum)
                    self.assertEqual(config['population']['maxFamilies'], families)
                    self.assertTrue(config['population']['randomVisitors'])
                    densities = [result['scenery'][key] for key in DENSITIES]
                    self.assertTrue(all(0 <= value <= 2 for value in densities))
                    self.assertLessEqual(sum(densities), 9)
                    seen_densities.update(densities)
                    seen_nests.add(result['scenery']['nestEnabled'])
                    seen_residency.add(result['animals']['diplodocusResident'])
                    pool = {species for species in GROUND_EXTENTS
                            if config['animals'][species + 'Enabled']}
                    if maximum > 1:
                        self.assertGreaterEqual(len(pool), 2)
                    else:
                        self.assertFalse(pool)
                    if maximum < 3 or families == 0:
                        self.assertNotIn('parasaurolophus', pool)
                    world = World(config, visitor_seed=17)
                    canvas = Canvas(160, 48)
                    world.set_viewport(canvas.world_bounds)
                    self.assertIn('brachiosaurus', world.snapshot()['admitted'])
                    self.assertLessEqual(len(world.snapshot()['admitted']), maximum)
                    self.assertLessEqual(len(visible_cast_members(canvas, world.snapshot(), config)), maximum)
                    if maximum == 1:
                        self.assertEqual(world.snapshot()['admitted'], ('brachiosaurus',))
                        self.assertFalse(world.spawn_water_jump(30, 44))
        self.assertEqual(seen_residency, {False, True})
        self.assertEqual(seen_nests, {False, True})
        self.assertIn(0, seen_densities)
        self.assertIn(2, seen_densities)

    def test_staged_choices_do_not_change_a_running_world_until_apply(self):
        document = {'preset': 'dusk', 'motion': {'speed': .5, 'reducedMotion': True}}
        world = World(settings(document), visitor_seed=17)
        world.set_viewport(Canvas(160, 48).world_bounds)
        before = world.snapshot()
        result = randomize_document(document, 81)
        self.assertEqual(world.snapshot(), before)
        self.assertFalse(world.config['population']['randomVisitors'])
        world.reconfigure(settings(result))
        applied = copy.deepcopy(world.config)
        self.assertTrue(world.config['population']['randomVisitors'])
        for _ in range(100):
            world.advance(250_000_000)
        self.assertEqual(world.config, applied)
        self.assertEqual(world.config['motion'], settings(document)['motion'])
        self.assertEqual(world.config['preset'], 'dusk')
        self.assertEqual(world.config['population']['maxVisible'], 8)

    def test_tight_budget_really_admits_different_rotating_ground_encounters(self):
        for seed in (7, 81):
            with self.subTest(seed=seed):
                config = settings(randomize_document({
                    'population': {'maxVisible': 2, 'maxFamilies': 0},
                    'motion': {'speed': 2},
                }, seed))
                world = World(config, visitor_seed=17)
                canvas = Canvas(160, 48)
                world.set_viewport(canvas.world_bounds)
                admitted_ground = set()
                for _ in range(2400):
                    snapshot = world.snapshot()
                    self.assertLessEqual(len(snapshot['admitted']), 2)
                    self.assertIn('brachiosaurus', snapshot['admitted'])
                    admitted_ground.update(identity.partition(':')[0]
                                           for identity in visible_cast_members(canvas, snapshot, config)
                                           if identity.partition(':')[0] in GROUND_EXTENTS)
                    world.advance(250_000_000)
                self.assertGreaterEqual(len(admitted_ground), 2)
                self.assertEqual(world.config['population']['maxVisible'], 2)


if __name__ == '__main__':
    unittest.main()
