import copy
from dataclasses import replace
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from configuration import settings
from canvas import Canvas
from engine import World
from character_art import (_PALETTES, _foreground, _triceratops,
                           _triceratops_pose, draw_scene, visible_cast_members)
from layout import Rock
from population import triceratops_poses


class HornCanvas(Canvas):
    def __init__(self):
        super().__init__(500, 200)
        self.horns = []

    def line(self, x0, y0, x1, y1, color, *args, **kwargs):
        if color == _PALETTES['morning']['eye']:
            self.horns.append(math.hypot(x1 - x0, y1 - y0))
        return super().line(x0, y0, x1, y1, color, *args, **kwargs)


class TriceratopsArtwork(unittest.TestCase):
    def setUp(self):
        self.config = settings({
            'animals': {name: name == 'triceratopsEnabled'
                        for name in settings()['animals']},
            'population': {'maxVisible': 3},
            'motion': {'parallaxStrength': 0},
        })
        self.adult, self.calf = triceratops_poses(21, 0, 45, 21, 1.2, 0, 0)
        self.snapshot = World(self.config).snapshot()
        self.snapshot['herbivores']['triceratops'] = self.adult
        self.snapshot['triceratops_calf'] = self.calf
        self.snapshot['admitted'] = ('brachiosaurus', 'triceratops', 'triceratops:calf')

    def frame(self, pose, motion=1, width=500, height=200, aspect=2):
        canvas = Canvas(width, height, cell_aspect=aspect)
        _triceratops(canvas, pose, motion, _PALETTES['morning'])
        return canvas

    def pixels(self, canvas, owner):
        return {(x, y) for y, row in enumerate(canvas.owners)
                for x, value in enumerate(row) if value == owner}

    def test_stop_restart_and_independent_clicks_keep_muzzle_and_silhouettes_apart(self):
        # Sample both sides of settling/restart and the middle of the stop.
        for seconds in (12, 17, 17.999, 18, 18.001, 19, 21, 23, 23.999, 24, 24.001, 25):
            for motion in (1, .18):
                for reactions in ((0, 0), (.5, 0), (1, 0), (0, .5), (0, 1), (1, 1)):
                    with self.subTest(seconds=seconds, motion=motion, reactions=reactions):
                        adult, calf = triceratops_poses(seconds, 0, 45, seconds, 1.2, *reactions)
                        adult_joints = _triceratops_pose(adult, motion)
                        calf_joints = _triceratops_pose(calf, motion)
                        tail_rear = min(adult_joints['tail'](*point)[0] for point in (
                            (-8, 47), (-11, 47.4), (-13, 48), (-14, 49),
                            (-12, 49.8), (-10, 49.5), (-8, 49)))
                        for point in ((12, 48), (14, 49.5), (12, 50.5), (13, 49.8)):
                            self.assertLess(calf_joints['head'](*point)[0], tail_rear - 3)
                        canvas = self.frame(adult, motion, width=240, height=80)
                        child = self.frame(calf, motion, width=240, height=80)
                        parent_pixels = self.pixels(canvas, adult['id'])
                        child_pixels = self.pixels(child, calf['id'])
                        self.assertTrue(parent_pixels)
                        self.assertTrue(child_pixels)
                        self.assertGreaterEqual(min(x for x, y in parent_pixels)
                                                - max(x for x, y in child_pixels), 3)
                        _triceratops(canvas, calf, motion, _PALETTES['morning'])
                        self.assertEqual(self.pixels(canvas, adult['id']), parent_pixels)
                        self.assertEqual(self.pixels(canvas, calf['id']), child_pixels)

    def test_small_terminal_cells_leave_visible_daylight_at_each_cell_aspect(self):
        for aspect in (1.2, 2, 3):
            for motion in (1, .18):
                for reaction in (0, .5, 1):
                    adult = dict(self.adult, reaction=reaction)
                    calf = dict(self.calf, reaction=reaction)
                    parent_pixels = self.pixels(
                        self.frame(adult, motion, width=120, height=48, aspect=aspect), adult['id'])
                    child_pixels = self.pixels(
                        self.frame(calf, motion, width=120, height=48, aspect=aspect), calf['id'])
                    self.assertTrue(parent_pixels)
                    self.assertTrue(child_pixels)
                    self.assertGreaterEqual(min(x for x, y in parent_pixels)
                                            - max(x for x, y in child_pixels), 2)

    def test_stopped_calf_skull_remains_neutral_and_clicks_keep_rigid_anatomy(self):
        for motion in (1, .18):
            for seconds in (17.999, 18, 18.001, 19, 21, 23, 23.999, 24, 24.001):
                calf = triceratops_poses(seconds, 0, 45, seconds, 1.2, 0, 0)[1]
                joints = _triceratops_pose(calf, motion)
                self.assertEqual(joints['head'](14, 49.5), joints['body'](14, 49.5))
        for original in (self.adult, self.calf):
            body_pixels = None
            for reaction in (0, .25, .5, .75, 1):
                pose = dict(original, reaction=reaction)
                joints = _triceratops_pose(pose, 1)
                for part, start, end in (('head', (4, 47), (14, 49.5)),
                                         ('head', (5, 47), (12, 48)),
                                         ('tail', (-8, 48), (-14, 49))):
                    self.assertAlmostEqual(math.dist(joints[part](*start), joints[part](*end)),
                                           math.dist(start, end) * pose['scale'])
                canvas = self.frame(pose)
                canvas.depth = .55
                x0, y0 = map(round, canvas.project(*joints['body'](-5, 45.5)))
                x1, y1 = map(round, canvas.project(*joints['body'](-1, 48)))
                torso = [(canvas.chars[y][x], canvas.colors[y][x], canvas.owners[y][x])
                         for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)]
                if body_pixels is None:
                    body_pixels = torso
                self.assertEqual(torso, body_pixels)
        for motion in (1, .18):
            clicked = _triceratops_pose(dict(self.calf, reaction=1), motion)
            origin = clicked['head'](4, 47)
            forward = clicked['head'](14, 47)
            self.assertAlmostEqual(math.atan2(forward[1] - origin[1], forward[0] - origin[0]),
                                   -.32 * motion)
        rest = _triceratops_pose(self.calf, 1)['head'](14, 49.5)
        clicked = _triceratops_pose(dict(self.calf, reaction=1), 1)['head'](14, 49.5)
        calm = _triceratops_pose(dict(self.calf, reaction=1), .18)['head'](14, 49.5)
        self.assertLess(clicked[1], rest[1])
        self.assertLess(math.dist(calm, rest), math.dist(clicked, rest) / 3)

    def test_calf_has_three_stub_horns_not_merely_scaled_adult_horns(self):
        lengths = []
        for pose in (self.adult, self.calf):
            canvas = HornCanvas()
            _triceratops(canvas, pose, 1, _PALETTES['morning'])
            self.assertEqual(len(canvas.horns), 3)
            lengths.append(sorted(length / pose['scale'] for length in canvas.horns))
        for adult, calf in zip(*lengths):
            self.assertGreater(calf, 0)
            self.assertLess(calf, adult * .6)

    def test_cell_scaling_grounded_feet_and_intermediate_silhouettes_stay_bounded(self):
        for pose in (self.adult, self.calf):
            for aspect in (1.2, 2, 3):
                small = self.frame(pose, width=240, height=80, aspect=aspect)
                large = self.frame(pose, width=480, height=160, aspect=aspect)
                a, b = small.bounds(pose['id']), large.bounds(pose['id'])
                self.assertAlmostEqual(b[2] / a[2], 2, delta=.3)
                self.assertAlmostEqual(b[3] / a[3], 2, delta=.3)
                for reaction in (0, .5, 1):
                    frame = self.frame(dict(pose, reaction=reaction), aspect=aspect)
                    tolerance_x = .51 / (frame.aspect * frame.scale)
                    tolerance_y = .51 / frame.scale
                    owned = self.pixels(frame, pose['id'])
                    for x, y in owned:
                        wx, wy = frame.unproject(x, y, .55)
                        self.assertTrue(pose['x'] - 15 * pose['scale'] - tolerance_x <= wx
                                        <= pose['x'] + 15 * pose['scale'] + tolerance_x)
                        self.assertTrue(pose['foot_y'] - 15 * pose['scale'] - tolerance_y <= wy
                                        <= pose['foot_y'] + tolerance_y)
                    self.assertAlmostEqual(max(frame.unproject(x, y, .55)[1] for x, y in owned),
                                           pose['foot_y'], delta=tolerance_y)

    def test_selected_members_are_individual_and_foreground_replaces_calf_ownership(self):
        for enabled, limit, expected in ((True, 3, {'triceratops', 'triceratops:calf'}),
                                         (True, 2, {'triceratops'}), (False, 3, set())):
            config = copy.deepcopy(self.config)
            config['animals']['triceratopsEnabled'] = enabled
            config['population']['maxVisible'] = limit
            canvas = Canvas(500, 200)
            draw_scene(canvas, self.snapshot, config)
            actual = {owner for row in canvas.owners for owner in row
                      if owner and owner.partition(':')[0] == 'triceratops'}
            self.assertEqual(actual, expected)
            self.assertTrue(actual <= set(visible_cast_members(canvas, self.snapshot, config)))
        baseline = self.frame(self.calf)
        layout = replace(self.snapshot['layout'], rocks=(Rock('front', self.calf['x'], 51, 1, 'pebble'),))
        foreground = Canvas(500, 200)
        _foreground(foreground, 0, 1, layout, _PALETTES['morning'])
        painted = self.frame(self.calf)
        _foreground(painted, 0, 1, layout, _PALETTES['morning'])
        overlap = self.pixels(baseline, 'triceratops:calf') & {
            (x, y) for y, row in enumerate(foreground.colors)
            for x, color in enumerate(row) if color is not None}
        self.assertTrue(overlap, 'Occlusion fixture must cover the actual calf')
        for x, y in overlap:
            self.assertNotEqual(painted.owners[y][x], 'triceratops:calf')
            self.assertEqual((painted.chars[y][x], painted.colors[y][x], painted.owners[y][x]),
                             (foreground.chars[y][x], foreground.colors[y][x], foreground.owners[y][x]))

    def test_depth_clip_and_owner_survive_painting_and_interruption(self):
        canvas = Canvas(500, 200)
        canvas.depth, canvas.clip_bottom, canvas.default_owner = .7, 175, 'scenery'
        _triceratops(canvas, self.calf, 1, _PALETTES['morning'])
        self.assertEqual((canvas.depth, canvas.clip_bottom, canvas.default_owner), (.7, 175, 'scenery'))
        self.assertTrue(all(y <= 175 for x, y in self.pixels(canvas, 'triceratops:calf')))
        with patch.object(canvas, 'polygon', side_effect=RuntimeError('interrupted')):
            with self.assertRaises(RuntimeError):
                _triceratops(canvas, self.calf, 1, _PALETTES['morning'])
        self.assertEqual((canvas.depth, canvas.clip_bottom, canvas.default_owner), (.7, 175, 'scenery'))


if __name__ == '__main__':
    unittest.main()
