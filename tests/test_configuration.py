import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from configuration import load_document, load_settings, settings


def patch_at(path, value):
    patch = value
    for key in reversed(path.split('.')):
        patch = {key: patch}
    return patch


class ConfigurationResolution(unittest.TestCase):
    def test_family_fields_follow_sparse_precedence(self):
        document = {
            'preset': 'dusk',
            'animals': {'parasaurolophusEnabled': False, 'trexEnabled': False},
            'population': {'maxFamilies': 0, 'maxVisible': 3, 'randomVisitors': True},
        }
        overrides = {
            'preset': 'morning',
            'animals': {'parasaurolophusEnabled': True},
            'population': {'maxFamilies': 2},
        }
        original_document = copy.deepcopy(document)
        original_overrides = copy.deepcopy(overrides)
        resolved = settings(document, overrides)
        self.assertIs(resolved['animals']['parasaurolophusEnabled'], True)
        self.assertIs(resolved['animals']['trexEnabled'], False)
        self.assertEqual(resolved['population'],
                         {'maxFamilies': 2, 'maxVisible': 3, 'randomVisitors': True})
        self.assertEqual(document, original_document)
        self.assertEqual(overrides, original_overrides)
        inherited = settings(document, {'preset': 'morning', 'animals': {}, 'population': {}})
        self.assertIs(inherited['animals']['parasaurolophusEnabled'], False)
        self.assertEqual(inherited['population']['maxFamilies'], 0)

    def test_palette_changes_only_the_palette_field(self):
        document = {'seed': 123, 'scenery': {'fernDensity': .5}}
        morning = settings(document)
        dusk = settings(document | {'preset': 'dusk'})
        self.assertEqual(morning | {'preset': 'dusk'}, dusk)

    def test_explicit_palette_override_wins_without_changing_other_fields(self):
        dusk = settings({'preset': 'morning'}, {'preset': 'dusk'})
        self.assertEqual(dusk['preset'], 'dusk')
        morning = settings({'preset': 'dusk'}, {'preset': 'morning'})
        self.assertEqual(morning['preset'], 'morning')
        self.assertEqual(dusk | {'preset': 'morning'}, morning)

    def test_diplodocus_residency_is_an_independent_strict_boolean(self):
        self.assertIs(settings()['animals']['diplodocusResident'], False)
        for palette in ('morning', 'dusk'):
            resolved = settings({'preset': palette, 'animals': {
                'diplodocusEnabled': False, 'diplodocusResident': True}})
            self.assertIs(resolved['animals']['diplodocusResident'], True)
            self.assertIs(resolved['animals']['diplodocusEnabled'], False)

    def test_preset_switch_preserves_explicit_file_motion(self):
        document = {'preset': 'dusk', 'motion': {'speed': .5, 'reducedMotion': True}}
        resolved = settings(document, {'preset': 'morning'})
        self.assertEqual(resolved['preset'], 'morning')
        self.assertEqual(resolved['motion']['speed'], .5)
        self.assertTrue(resolved['motion']['reducedMotion'])
        dusk = settings({'motion': {'parallaxStrength': 1.25}}, {'preset': 'dusk'})
        self.assertEqual(dusk['motion']['parallaxStrength'], 1.25)

    def test_explicit_overrides_win_only_for_their_sparse_fields(self):
        document = {
            'preset': 'dusk',
            'seed': 5,
            'motion': {'speed': .5, 'reducedMotion': True},
            'scenery': {'treeDensity': 0, 'cloudDensity': .25},
        }
        resolved = settings(document, {
            'seed': 9,
            'motion': {'speed': 1.5},
            'scenery': {'cloudDensity': 2},
        })
        self.assertEqual(resolved['seed'], 9)
        self.assertEqual(resolved['motion']['speed'], 1.5)
        self.assertTrue(resolved['motion']['reducedMotion'])
        self.assertEqual(resolved['scenery']['treeDensity'], 0)
        self.assertEqual(resolved['scenery']['cloudDensity'], 2)

    def test_resolution_preserves_sparse_caller_intent(self):
        document = {'preset': 'dusk', 'motion': {'speed': .5}, 'scenery': {}}
        overrides = {'motion': {'reducedMotion': True}}
        original_document = copy.deepcopy(document)
        original_overrides = copy.deepcopy(overrides)
        resolved = settings(document, overrides)
        resolved['motion']['speed'] = 2
        resolved['scenery']['treeDensity'] = 0
        self.assertEqual(document, original_document)
        self.assertEqual(overrides, original_overrides)
        again = settings(document, overrides)
        self.assertEqual(again['motion']['speed'], .5)
        self.assertEqual(again['scenery']['treeDensity'], 1)
        overrides['preset'] = 'morning'
        switched = settings(document, overrides)
        self.assertEqual(switched['motion']['speed'], .5)
        self.assertEqual(switched['motion']['parallaxStrength'], settings()['motion']['parallaxStrength'])
        self.assertTrue(switched['motion']['reducedMotion'])

    def test_invalid_document_is_not_hidden_by_valid_override(self):
        for document, overrides in (
            ({'seed': -1}, {'seed': 42}),
            ({'preset': 'unknown'}, {'preset': 'morning'}),
            ({'motion': {'speed': 3}}, {'motion': {'speed': 1}}),
            ({'animals': {'parasaurolophusEnabled': 1}},
             {'animals': {'parasaurolophusEnabled': True}}),
            ({'population': {'maxFamilies': 3}}, {'population': {'maxFamilies': 1}}),
            ({'population': {'maxFamilies': 1.0}}, {'population': {'maxFamilies': 1}}),
        ):
            with self.subTest(document=document), self.assertRaises(ValueError):
                settings(document, overrides)


class ConfigurationValidation(unittest.TestCase):
    def assert_rejected_in_each_layer(self, patch):
        with self.assertRaises(ValueError):
            settings(patch)
        with self.assertRaises(ValueError):
            settings(overrides=patch)

    def test_unknown_keys_at_every_level(self):
        for patch in (
            {'unknown': 1},
            {'motion': {'unknown': 1}},
            {'scenery': {'unknown': 1}},
            {'sound': {'unknown': 1}},
            {'integration': {'unknown': 1}},
            {'animals': {'unknown': True}},
            {'population': {'unknown': 8}},
        ):
            with self.subTest(patch=patch):
                self.assert_rejected_in_each_layer(patch)

    def test_root_and_sections_must_be_objects(self):
        for value in ([], '', 1, 1.0, True):
            with self.subTest(root=value):
                self.assert_rejected_in_each_layer(value)
        for section in ('motion', 'scenery', 'sound', 'integration', 'animals', 'population'):
            for value in (None, [], '', 1, True):
                with self.subTest(section=section, value=value):
                    self.assert_rejected_in_each_layer({section: value})

    def test_booleans_are_not_coerced(self):
        for path in ('motion.reducedMotion', 'sound.enabled', 'scenery.nestEnabled',
                     'integration.idleEnabled', 'integration.exitOnPointerMotion',
                     'animals.trexEnabled', 'animals.triceratopsEnabled',
                     'animals.stegosaurusEnabled', 'animals.pteranodonEnabled',
                     'animals.ankylosaurusEnabled', 'animals.parasaurolophusEnabled',
                     'animals.plesiosaurusEnabled', 'animals.diplodocusEnabled',
                     'animals.diplodocusResident',
                     'population.randomVisitors'):
            for value in (0, 1, 'false', 'true', None, [], {}):
                with self.subTest(path=path, value=value):
                    self.assert_rejected_in_each_layer(patch_at(path, value))
        resolved = settings({
            'motion': {'reducedMotion': True},
            'integration': {'exitOnPointerMotion': False},
        })
        self.assertTrue(resolved['motion']['reducedMotion'])
        self.assertFalse(resolved['integration']['exitOnPointerMotion'])


    def test_idle_and_ambience_remain_opt_in_by_default_and_configurable(self):
        defaults = settings()
        self.assertFalse(defaults['integration']['idleEnabled'])
        self.assertTrue(defaults['integration']['exitOnPointerMotion'])
        self.assertFalse(defaults['sound']['enabled'])
        self.assertEqual(defaults['sound']['volume'], 20)
        enabled = settings({'integration': {'idleEnabled': True},
                            'sound': {'enabled': True, 'volume': 35}})
        self.assertTrue(enabled['integration']['idleEnabled'])
        self.assertTrue(enabled['sound']['enabled'])
        self.assertEqual(enabled['sound']['volume'], 35)
        defaults_file = json.loads((ROOT / 'defaults.json').read_text(encoding='utf-8'))
        self.assertEqual(settings(defaults_file), defaults)

    def test_numeric_types_and_nonfinite_values_are_rejected(self):
        paths = ('seed', 'schemaVersion', 'motion.speed', 'motion.parallaxStrength',
                 'sound.volume', 'scenery.treeDensity', 'scenery.fernDensity',
                 'scenery.rockDensity', 'scenery.cloudDensity',
                 'scenery.cycadDensity', 'scenery.flowerDensity',
                 'scenery.lilyPadDensity', 'population.maxVisible',
                 'population.maxFamilies')
        for path in paths:
            for value in (True, False, '1', None, [], {},
                          float('nan'), float('inf'), -float('inf')):
                with self.subTest(path=path, value=value):
                    self.assert_rejected_in_each_layer(patch_at(path, value))

    def test_integer_fields_are_strict_and_bounded(self):
        for value in (1.0, 42.0, .5, -1, 2**53, 10**400):
            with self.subTest(seed=value):
                self.assert_rejected_in_each_layer({'seed': value})
        for seed in (0, 2**53 - 1):
            with self.subTest(seed=seed):
                self.assertEqual(settings({'seed': seed})['seed'], seed)
        for value in (1.0, 0, 2, -1, 10**400):
            with self.subTest(schemaVersion=value):
                self.assert_rejected_in_each_layer({'schemaVersion': value})
        self.assertEqual(settings({'schemaVersion': 1})['schemaVersion'], 1)
        for value in (1.0, 8.0, .5, 0, -1, 129, 10**400):
            with self.subTest(maxVisible=value):
                self.assert_rejected_in_each_layer({'population': {'maxVisible': value}})
        for value in (1, 8, 128):
            self.assertEqual(settings({'population': {'maxVisible': value}})
                             ['population']['maxVisible'], value)
        for value in (0.0, 1.0, 2.0, .5, -1, 3, 10**400):
            with self.subTest(maxFamilies=value):
                self.assert_rejected_in_each_layer({'population': {'maxFamilies': value}})
        for value in (0, 1, 2):
            for document, overrides in (
                ({'population': {'maxFamilies': value}}, None),
                (None, {'population': {'maxFamilies': value}}),
            ):
                with self.subTest(maxFamilies=value, document=document, overrides=overrides):
                    resolved = settings(document, overrides)
                    self.assertEqual(resolved['population']['maxFamilies'], value)
                    self.assertIs(type(resolved['population']['maxFamilies']), int)
        for value in (True, False):
            for document, overrides in (
                ({'animals': {'parasaurolophusEnabled': value}}, None),
                (None, {'animals': {'parasaurolophusEnabled': value}}),
            ):
                with self.subTest(parasaurolophusEnabled=value, document=document, overrides=overrides):
                    self.assertIs(settings(document, overrides)['animals']['parasaurolophusEnabled'],
                                  value)

    def test_numeric_range_boundaries(self):
        ranges = {
            'motion.speed': (.25, 2),
            'motion.parallaxStrength': (0, 2),
            'sound.volume': (0, 100),
            'scenery.treeDensity': (0, 2),
            'scenery.fernDensity': (0, 2),
            'scenery.rockDensity': (0, 2),
            'scenery.cloudDensity': (0, 2),
            'scenery.cycadDensity': (0, 2),
            'scenery.flowerDensity': (0, 2),
            'scenery.lilyPadDensity': (0, 2),
        }
        for path, (low, high) in ranges.items():
            for value in (low, high, (low + high) / 2):
                with self.subTest(path=path, accepted=value):
                    resolved = settings(patch_at(path, value))
                    for key in path.split('.'):
                        resolved = resolved[key]
                    self.assertEqual(resolved, value)
            for value in (low - .000001, high + .000001, 10**400):
                with self.subTest(path=path, rejected=value):
                    self.assert_rejected_in_each_layer(patch_at(path, value))

    def test_preset_requires_a_supported_string(self):
        for value in ('', 'Dusk', 'other', None, 1, True, [], {}):
            with self.subTest(value=value):
                self.assert_rejected_in_each_layer({'preset': value})


class ConfigurationFiles(unittest.TestCase):
    def test_sparse_family_preferences_load_without_rewriting_saved_intent(self):
        document = {
            'animals': {'parasaurolophusEnabled': False},
            'population': {'maxFamilies': 0},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            content = json.dumps(document, indent=2) + '\n'
            path.write_text(content, encoding='utf-8')
            self.assertEqual(load_document(path), document)
            resolved = load_settings(path, {
                'animals': {'parasaurolophusEnabled': True},
                'population': {'maxFamilies': 2},
            })
            self.assertIs(resolved['animals']['parasaurolophusEnabled'], True)
            self.assertEqual(resolved['population']['maxFamilies'], 2)
            self.assertEqual(resolved['population']['maxVisible'], 8)
            self.assertEqual(path.read_text(encoding='utf-8'), content)
            inherited = load_settings(path)
            self.assertIs(inherited['animals']['parasaurolophusEnabled'], False)
            self.assertEqual(inherited['population']['maxFamilies'], 0)

    def test_missing_blank_and_empty_object_files_are_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            for content in (None, '', ' \t\r\n', '{}'):
                with self.subTest(content=content):
                    if content is not None:
                        path.write_text(content, encoding='utf-8')
                    resolved = load_settings(path, {'preset': 'dusk'})
                    self.assertEqual(resolved['preset'], 'dusk')
                    self.assertFalse(resolved['sound']['enabled'])
                    self.assertFalse(resolved['integration']['idleEnabled'])

    def test_sparse_file_and_explicit_cli_preset_preserve_file_intent(self):
        document = {'preset': 'dusk', 'motion': {'speed': .5},
                    'scenery': {'treeDensity': 0}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            path.write_text(json.dumps(document), encoding='utf-8')
            resolved = load_settings(path, {'preset': 'morning'})
            self.assertEqual(resolved['preset'], 'morning')
            self.assertEqual(resolved['motion']['speed'], .5)
            self.assertEqual(resolved['scenery']['treeDensity'], 0)
            self.assertEqual(json.loads(path.read_text(encoding='utf-8')), document)

    def test_loaded_document_retains_sparse_intent_across_preset_switches(self):
        document = {'preset': 'dusk', 'motion': {'speed': .5}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            self.assertEqual(load_document(path), {})
            path.write_text(json.dumps(document), encoding='utf-8')
            loaded = load_document(path)
            path.write_text('{"motion":{"speed":9}}', encoding='utf-8')
            morning = settings(loaded, {'preset': 'morning'})
            dusk = settings(loaded, {'preset': 'dusk'})
            self.assertEqual(morning['motion']['speed'], .5)
            self.assertEqual(dusk['motion']['speed'], .5)
            self.assertEqual(morning['motion'], dusk['motion'])
            self.assertEqual(loaded, document)

    def test_document_loader_rejects_nonobject_and_oversize_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            for content in ('null', '[]', 'true', '"dusk"', '{'):
                with self.subTest(content=content):
                    path.write_text(content, encoding='utf-8')
                    with self.assertRaises(ValueError):
                        load_document(path)
            path.write_bytes(b'{}' + b' ' * (256 * 1024 - 1))
            with self.assertRaises(ValueError):
                load_document(path)
            path.write_text(' \t\n', encoding='utf-8')
            self.assertEqual(load_document(path), {})


    def test_invalid_json_roots_scalars_and_nonfinite_numbers(self):
        contents = ('null', '[]', 'true', '42', '"morning"', '{',
                    '{"motion":{"speed":NaN}}',
                    '{"motion":{"speed":Infinity}}',
                    '{"motion":{"speed":-Infinity}}',
                    '{"motion":{"speed":1e999}}',
                    '{"schemaVersion":1.0}', '{"seed":1.0}',
                    '{"motion":{"speed":true}}', '{"unknown":1}')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            for content in contents:
                with self.subTest(content=content):
                    path.write_text(content, encoding='utf-8')
                    with self.assertRaises(ValueError):
                        load_settings(path)

    def test_size_limit_is_inclusive_and_counts_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            path.write_bytes(b'{}' + b' ' * (256 * 1024 - 2))
            self.assertEqual(load_settings(path, {'seed': 7})['seed'], 7)
            path.write_bytes(b'{}' + b' ' * (256 * 1024 - 1))
            with self.assertRaises(ValueError):
                load_settings(path)


if __name__ == '__main__':
    unittest.main()
