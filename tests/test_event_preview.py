import contextlib
import copy
import io
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from canvas import Canvas
from character_art import draw_scene
from configuration import settings
from dinosaurs import _apply_preview_event, main
from event_preview import EVENTS, event_world, preview_settings
from pteranodon import pteranodon_bounds

SECOND = 1_000_000_000


def advance(world, seconds):
    remaining = round(seconds * SECOND)
    while remaining:
        step = min(250_000_000, remaining)
        world.advance(step)
        remaining -= step


def frame(world, canvas):
    pose = world.snapshot()
    canvas.camera = pose['camera']
    draw_scene(canvas, pose, world.config)
    return pose


class EventPreviews(unittest.TestCase):
    def test_session_overrides_preserve_compatible_intent_and_never_mutate_inputs(self):
        document = {
            'preset': 'dusk', 'seed': 8317,
            'motion': {'speed': .25, 'reducedMotion': True, 'parallaxStrength': .3},
            'scenery': {'treeDensity': .2, 'nestEnabled': False},
            'population': {'maxVisible': 1, 'maxFamilies': 2, 'randomVisitors': True},
        }
        overrides = {'seed': 71}
        original = copy.deepcopy((document, overrides))
        for event in EVENTS:
            with self.subTest(event=event):
                config = preview_settings(document, overrides, event)
                self.assertEqual(config['motion'], settings(document, overrides)['motion'])
                self.assertEqual(config['preset'], 'dusk')
                self.assertEqual(config['seed'], 71)
                self.assertEqual(config['scenery']['treeDensity'], .2)
                self.assertEqual(config['scenery']['nestEnabled'], event == 'hatching')
                enabled = {key for key, value in config['animals'].items() if value}
                expected = ({'pteranodonEnabled'} if event == 'flock' else
                            {'diplodocusEnabled'} if event == 'diplodocus' else set())
                self.assertEqual(enabled, expected)
                self.assertFalse(config['population']['randomVisitors'])
                self.assertEqual(config['population']['maxFamilies'], 0)
                self.assertEqual(config['population']['maxVisible'],
                                 9 if event == 'flock' else 2 if event in ('hatching', 'diplodocus') else 1)
        self.assertEqual((document, overrides), original)

    def world(self, event, document=None, width=240, height=60, aspect=2):
        canvas = Canvas(width, height, cell_aspect=aspect)
        config = preview_settings(document or {'population': {'maxVisible': 1}}, {}, event)
        return event_world(config, event, canvas.world_bounds), canvas

    def test_hatching_crosses_a_live_deadline_and_reserves_a_real_cast_seat(self):
        world, canvas = self.world('hatching')
        self.assertIsNone(world.snapshot()['hatching'])
        self.assertEqual(world.hatching.deadline - world.elapsed_ns, SECOND)
        self.assertEqual(world.cast.members, ('brachiosaurus',))
        advance(world, 1)
        self.assertTrue(world.hatching.active)
        self.assertEqual(world.cast.count('brachiosaurus:young'), 1)
        self.assertEqual(world.hatching.generation, 0)
        self.assertIn('brachiosaurus:young', world.snapshot()['admitted'])
        advance(world, 14)
        pose = frame(world, canvas)
        self.assertEqual(pose['hatching']['state'], 'toddling')
        self.assertGreater(pose['hatching']['emerge'], 0)
        self.assertIsNotNone(canvas.bounds('brachiosaurus:young'))
        self.assertLessEqual(len(world.cast.members), world.config['population']['maxVisible'])

    def test_flock_admits_its_whole_v_outside_the_actual_viewport(self):
        for width, height, aspect in ((160, 48, 2), (360, 72, 1.2)):
            with self.subTest(geometry=(width, height, aspect)):
                world, canvas = self.world('flock', width=width, height=height, aspect=aspect)
                self.assertIsNone(world.snapshot()['pteranodon_flock'])
                self.assertEqual(world.pteranodon_flocks.deadline - world.elapsed_ns, SECOND)
                advance(world, 1)
                flock = world.snapshot()['pteranodon_flock']
                self.assertIsNotNone(flock)
                self.assertEqual(world.cast.count('pteranodon:flock'), 5)
                for bird in flock['members']:
                    bounds = pteranodon_bounds(bird)
                    self.assertLess(bounds[2], canvas.world_bounds[0] - 3.5 * bounds[4])
                advance(world, 25)
                frame(world, canvas)
                self.assertTrue(any(canvas.bounds(f'pteranodon:{index}') is not None
                                    for index in range(3, 8)))
                self.assertLessEqual(len(world.cast.members), world.config['population']['maxVisible'])

    def test_diplodocus_scheduled_arrival_keeps_palette_and_overrides_residency(self):
        world, canvas = self.world('diplodocus', {
            'preset': 'dusk', 'animals': {'diplodocusResident': True},
            'population': {'maxVisible': 1},
        })
        self.assertEqual(world.config['preset'], 'dusk')
        self.assertFalse(world.config['animals']['diplodocusResident'])
        self.assertIsNone(world.snapshot()['diplodocus'])
        self.assertEqual(world.diplodocus.deadline - world.elapsed_ns, SECOND)
        advance(world, 1)
        pose = world.snapshot()['diplodocus']
        self.assertEqual(pose['state'], 'approaching')
        self.assertLess(pose['x'] + 40, canvas.world_bounds[0] - 3.5 * pose['depth'])
        self.assertEqual(world.cast.count('diplodocus'), 1)
        advance(world, 45)
        frame(world, canvas)
        self.assertIsNotNone(canvas.bounds('diplodocus'))
        self.assertLessEqual(len(world.cast.members), world.config['population']['maxVisible'])

    def test_shower_plays_normally_and_rainbow_is_visible_on_its_first_frame(self):
        for calm in (False, True):
            document = {'preset': 'dusk', 'motion': {'speed': .5, 'reducedMotion': calm},
                        'population': {'maxVisible': 1}}
            shower, canvas = self.world('shower', document)
            self.assertIsNone(shower.snapshot()['weather'])
            self.assertEqual(shower.weather.deadline - shower.elapsed_ns, SECOND)
            advance(shower, 1 + (20 if calm else 14) / .5)
            pose = frame(shower, canvas)
            self.assertEqual(pose['weather']['state'], 'shower')
            self.assertTrue(pose['weather']['rain'])
            dry_pose = dict(pose)
            dry_pose['weather'] = dict(pose['weather'], rain=())
            dry_canvas = Canvas(canvas.width, canvas.height, cell_aspect=canvas.aspect)
            dry_canvas.camera = canvas.camera
            draw_scene(dry_canvas, dry_pose, shower.config)
            self.assertNotEqual((canvas.chars, canvas.colors),
                                (dry_canvas.chars, dry_canvas.colors))
            rainbow, canvas = self.world('rainbow', document)
            pose = frame(rainbow, canvas)
            self.assertEqual(pose['weather']['state'], 'rainbow')
            self.assertGreater(pose['weather']['rainbow_strength'], .99)
            clear_pose = dict(pose, weather=None)
            clear_canvas = Canvas(canvas.width, canvas.height, cell_aspect=canvas.aspect)
            clear_canvas.camera = canvas.camera
            draw_scene(clear_canvas, clear_pose, rainbow.config)
            self.assertNotEqual((canvas.chars, canvas.colors),
                                (clear_canvas.chars, clear_canvas.colors))
            self.assertEqual(rainbow.cast.members, ('brachiosaurus',))

    def test_volcano_crosses_the_real_first_puff_deadline(self):
        world, canvas = self.world('volcano')
        self.assertIsNone(world.snapshot()['volcano_puff'])
        self.assertEqual(world.volcano_puffs.deadline - world.elapsed_ns, SECOND)
        advance(world, 13)
        pose = frame(world, canvas)
        self.assertEqual(pose['volcano_puff']['generation'], 0)
        self.assertGreater(pose['volcano_puff']['strength'], .99)
        self.assertEqual(world.cast.members, ('brachiosaurus',))

    def test_reload_and_p_n_r_keep_test_prerequisites_without_writing(self):
        for event in EVENTS:
            with self.subTest(event=event):
                world, canvas = self.world(event)
                document = {'preset': 'dusk',
                            'animals': {name: False for name in settings()['animals']},
                            'scenery': {'nestEnabled': False},
                            'population': {'maxVisible': 1, 'randomVisitors': True}}
                original = copy.deepcopy(document)
                world.reconfigure(preview_settings(document, {}, event))
                session = {}
                for key in (b'p', b'n', b'r'):
                    paused = world.paused
                    action = _apply_preview_event(world, ('key', key), canvas, (0, 0),
                                                  document, {}, session, event)
                    self.assertTrue(action.redraw)
                    expected = ({'pteranodonEnabled'} if event == 'flock' else
                                {'diplodocusEnabled'} if event == 'diplodocus' else set())
                    self.assertEqual({name for name, enabled in world.config['animals'].items() if enabled},
                                     expected)
                    self.assertEqual(world.config['scenery']['nestEnabled'], event == 'hatching')
                    self.assertFalse(world.config['population']['randomVisitors'])
                    self.assertGreaterEqual(world.config['population']['maxVisible'],
                                            9 if event == 'flock' else 2 if event in ('hatching', 'diplodocus') else 1)
                    self.assertEqual(world.paused, paused)
                before = world.elapsed_ns
                _apply_preview_event(world, ('key', b' '), canvas, (0, 0), document, {}, session, event)
                world.advance(SECOND)
                self.assertEqual(world.elapsed_ns, before)
                self.assertEqual(document, original)

    def test_cli_rejects_event_tests_outside_interactive_preview(self):
        for argv in (['--test-event', 'rainbow'],
                     ['--preview', '--test-event', 'rainbow', '--snapshot'],
                     ['--preview', '--test-event', 'rainbow', '--check-config'],
                     ['--preview', '--test-event', 'not-an-event']):
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()) as stderr:
                with self.assertRaises(SystemExit) as error:
                    main(argv)
                self.assertEqual(error.exception.code, 2)
                self.assertIn('--test-event', stderr.getvalue())


if __name__ == '__main__':
    unittest.main()
