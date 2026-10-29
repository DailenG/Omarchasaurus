import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from configuration import settings
from canvas import Canvas
from engine import World
from character_art import draw_scene


class WorldContinuity(unittest.TestCase):
    def test_preset_and_reduced_motion_changes_do_not_retime_existing_walk(self):
        world = World(settings(), elapsed_ns=12_000_000_000)
        world.react('brachiosaurus')
        world.spawn_meteor(50, 4)
        world.advance(250_000_000)
        before = world.snapshot()
        before_elapsed = world.elapsed_ns
        world.reconfigure(settings({'preset': 'dusk', 'motion': {'reducedMotion': True}}))
        after = world.snapshot()
        for field in ('time', 'trex_x', 'phase', 'layout', 'meteor', 'brachiosaurus_reaction'):
            self.assertEqual(after[field], before[field], field)
        self.assertEqual(world.elapsed_ns, before_elapsed)
        self.assertEqual(after['camera'], (0, 0))
        world.advance(250_000_000)
        moved = world.snapshot()
        self.assertGreater(moved['trex_x'], after['trex_x'])
        self.assertLess(moved['trex_x']-after['trex_x'], .225)

    def test_density_reload_preserves_actors_events_and_unrelated_scenery(self):
        world = World(settings(), elapsed_ns=4_000_000_000)
        world.react('trex')
        world.spawn_meteor(55, 4)
        world.advance(250_000_000)
        before = world.snapshot()
        world.reconfigure(settings({'scenery': {'treeDensity': 2}}))
        after = world.snapshot()
        for field in ('time', 'camera', 'trex_x', 'phase', 'trex_reaction', 'meteor'):
            self.assertEqual(after[field], before[field], field)
        for category in ('clouds', 'ferns', 'rocks', 'ripples', 'pteranodons'):
            self.assertEqual(getattr(before['layout'], category), getattr(after['layout'], category))
        before_trees = {tree.id: tree for tree in before['layout'].trees}
        after_trees = {tree.id: tree for tree in after['layout'].trees}
        self.assertLessEqual(before_trees.keys(), after_trees.keys())
        for identity, tree in before_trees.items():
            self.assertEqual(after_trees[identity], tree)

    def test_seed_reload_changes_layout_without_restarting_simulation_or_input_state(self):
        world = World(settings(), elapsed_ns=6_000_000_000)
        world.react('brachiosaurus')
        world.spawn_meteor(55, 4)
        world.paused = True
        before = world.snapshot()
        world.reconfigure(settings({'seed': 43}))
        after = world.snapshot()
        self.assertNotEqual(before['layout'], after['layout'])
        self.assertEqual(before['time'], after['time'])
        self.assertEqual(before['meteor'], after['meteor'])
        self.assertEqual(before['brachiosaurus_reaction'], after['brachiosaurus_reaction'])
        self.assertTrue(world.paused)
        self.assertFalse(world.react('brachiosaurus'))

    def test_rendering_at_multiple_sizes_does_not_mutate_world_or_layout(self):
        world = World(settings(), elapsed_ns=12_000_000_000)
        before = world.snapshot()
        small = None
        for width, height in ((160, 48), (320, 96), (500, 120), (160, 48)):
            canvas = Canvas(width, height, before['camera'])
            draw_scene(canvas, world.snapshot(), world.config)
            if small is None:
                small = canvas.plain()
            self.assertEqual(world.snapshot(), before)
        self.assertEqual(canvas.plain(), small)

    def test_single_column_resize_does_not_teleport_the_focal_group(self):
        previous = None
        for width in range(180, 241):
            point = Canvas(width, 60).project(80, 20)
            if previous is not None:
                self.assertLess(abs(point[0]-previous[0]), 3)
            previous = point

    def test_maximum_scenery_keeps_focal_group_visible_at_camera_extremes(self):
        for seed in (0, 42, 2026):
            config = settings({'seed': seed, 'motion': {'parallaxStrength': 2},
                               'scenery': dict.fromkeys(('treeDensity', 'fernDensity', 'rockDensity', 'cloudDensity',
                                                       'cycadDensity', 'flowerDensity', 'lilyPadDensity'), 2)})
            for seconds in (0, 27.5, 82.5):
                world = World(config, elapsed_ns=round(seconds*1e9))
                pose = world.snapshot()
                for width, height in ((80, 24), (80, 80), (120, 36), (160, 48), (320, 96), (500, 40), (500, 200)):
                    with self.subTest(seed=seed, seconds=seconds, size=(width, height)):
                        canvas = Canvas(width, height, pose['camera'])
                        draw_scene(canvas, pose, world.config)
                        self.assertIsNotNone(canvas.bounds('brachiosaurus'))
                        canvas.depth = .4
                        left, top, right, bottom = pose['layout'].focal_bounds
                        for x, y in ((left, top), (right, bottom)):
                            px, py = canvas.project(x, y)
                            self.assertGreaterEqual(px, -.5)
                            self.assertLess(px, width-.5)
                            self.assertGreaterEqual(py, -.5)
                            self.assertLess(py, height-.5)
                        self.assertEqual(world.snapshot(), pose)

    def test_disabling_optional_scenery_keeps_focal_brachiosaurus(self):
        world = World(settings(), elapsed_ns=12_000_000_000)
        before = Canvas(320, 96, world.snapshot()['camera'])
        draw_scene(before, world.snapshot(), world.config)
        world.reconfigure(settings({'scenery': dict.fromkeys(
            ('treeDensity', 'fernDensity', 'rockDensity', 'cloudDensity',
             'cycadDensity', 'flowerDensity', 'lilyPadDensity'), 0) | {'nestEnabled': False}}))
        after = Canvas(320, 96, world.snapshot()['camera'])
        draw_scene(after, world.snapshot(), world.config)
        self.assertEqual(before.bounds('brachiosaurus'), after.bounds('brachiosaurus'))
        self.assertNotEqual(before.plain(), after.plain())


if __name__ == '__main__':
    unittest.main()
