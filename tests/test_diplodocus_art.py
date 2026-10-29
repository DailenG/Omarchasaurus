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
from character_art import (_PALETTES, _brachiosaurus, _diplodocus,
                           _diplodocus_pose, _distance_and_lake, _focal_tree,
                           _foreground, _lily_pad, _plesiosaurus, _water_jump,
                           draw_scene, visible_cast_members)
from layout import FOCAL_OFFSET_X, WATER_DEPTH, LilyPad, Rock, Tree


class DiplodocusArtwork(unittest.TestCase):
    def setUp(self):
        self.config = settings({
            'preset': 'dusk',
            'animals': {'trexEnabled': False, 'triceratopsEnabled': False,
                        'stegosaurusEnabled': False, 'ankylosaurusEnabled': False,
                        'parasaurolophusEnabled': False, 'pteranodonEnabled': False,
                        'plesiosaurusEnabled': False, 'diplodocusEnabled': True,
                        'diplodocusResident': True},
            'population': {'maxVisible': 8, 'maxFamilies': 0, 'randomVisitors': False},
            'scenery': {key: False if key == 'nestEnabled' else 0
                        for key in settings()['scenery']},
        })
        self.snapshot = World(self.config).snapshot()
        self.pose = dict(id='diplodocus', x=65, foot_y=36.5, depth=.21,
                         phase=0, stride=0, drink=1, look=0, reaction=0,
                         blink=False, state='drinking', generation=1)
        self.snapshot['diplodocus'] = self.pose
        self.layout = replace(self.snapshot['layout'], trees=(), ripples=(),
                              lily_pads=(), rocks=(), ferns=(), cycads=(),
                              flowers=(), nest=None)
        self.snapshot['layout'] = self.layout

    @staticmethod
    def owned(canvas, owner='diplodocus'):
        return {(x, y) for y, row in enumerate(canvas.owners)
                for x, value in enumerate(row) if value == owner}

    def frame(self, pose=None, motion=1, width=480, height=120, aspect=2,
              camera=(0, 0), preset='dusk'):
        canvas = Canvas(width, height, camera, cell_aspect=aspect)
        _diplodocus(canvas, self.pose if pose is None else pose,
                    motion, _PALETTES[preset])
        return canvas

    def pixel(self, canvas, point, depth=.21):
        old_depth = canvas.depth
        canvas.depth = depth
        result = tuple(map(round, canvas.project(*point)))
        canvas.depth = old_depth
        return result

    def assert_owned_near(self, canvas, point):
        x, y = self.pixel(canvas, point)
        self.assertTrue(any(abs(px-x) <= 1 and abs(py-y) <= 1
                            for px, py in self.owned(canvas)), point)

    def lake_frame(self, pose=None, layout=None, swimmer=None, jump=None):
        canvas = Canvas(480, 120)
        _distance_and_lake(canvas, jump, swimmer,
                           self.pose if pose is None else pose,
                           0, 1, self.layout if layout is None else layout,
                           _PALETTES['dusk'])
        return canvas

    def test_drinking_mouth_reaches_actual_water_while_feet_and_body_remain_on_land(self):
        left, top, right, bottom = self.layout.water_bounds
        for motion in (1, .18):
            for camera in ((0, 0), (3.5, -2)):
                canvas = Canvas(480, 120, camera)
                _distance_and_lake(canvas, None, None, None, 0, motion,
                                   self.layout, _PALETTES['dusk'])
                joints = _diplodocus_pose(self.pose, motion)
                mouth = joints['neck'](35, -12)
                self.assertTrue(left < mouth[0] < right)
                self.assertTrue(top < mouth[1] < bottom)
                self.assertAlmostEqual(math.dist(joints['neck'](7, -12), mouth), 28)
                mx, my = self.pixel(canvas, mouth)
                self.assertEqual(canvas.owners[my][mx], 'water')
                _diplodocus(canvas, self.pose, motion, _PALETTES['dusk'])
                self.assertEqual(canvas.owners[my][mx], 'diplodocus')
                for far, leg in joints['legs']:
                    for point in leg[5:7]:
                        self.assertAlmostEqual(point[1], self.pose['foot_y'])
                        self.assertLess(point[1], top)
                        self.assert_owned_near(canvas, point)
                self.assert_owned_near(canvas, joints['body'](-3, -10))
                for state in ('approaching', 'looking', 'departing'):
                    dry = dict(self.pose, drink=0, state=state)
                    dry_joints = _diplodocus_pose(dry, motion)
                    self.assertLess(dry_joints['neck'](35, -12)[1], top - 8)
                    dry_frame = self.frame(dry, motion=motion, camera=camera)
                    water_pixels = [dry_frame.unproject(x, y, .21)
                                    for x, y in self.owned(dry_frame)]
                    self.assertTrue(all(y < top for x, y in water_pixels))

    def test_rigid_neck_skull_and_tail_links_and_fixed_torso_during_intermediate_reactions(self):
        neutral = _diplodocus_pose(self.pose, 1)
        travels = {}
        for motion in (1, .18):
            rest = _diplodocus_pose(self.pose, motion)
            clicked = _diplodocus_pose(dict(self.pose, reaction=1), motion)
            travels[motion] = math.dist(rest['neck'](35, -12), clicked['neck'](35, -12))
            self.assertLess(clicked['neck'](35, -12)[1], rest['neck'](35, -12)[1])
            self.assertNotEqual(rest['whip'](-40, -10.6), clicked['whip'](-40, -10.6))
            for drink in (0, .25, .5, .75, 1):
                for reaction in (0, .35, .7, 1):
                    for look in (-.04, .04):
                        joints = _diplodocus_pose(dict(self.pose, drink=drink,
                                                      reaction=reaction, look=look), motion)
                        for part, a, b in (
                            ('neck', (7, -12), (35, -12)),
                            ('neck', (31.1, -13.5), (35.2, -12.1)),
                            ('tail', (-9, -11), (-25, -12)),
                            ('whip', (-25, -12), (-40, -10.6)),
                        ):
                            self.assertAlmostEqual(math.dist(joints[part](*a), joints[part](*b)),
                                                   math.dist(a, b), places=7)
                        self.assertEqual(joints['body'](-5, -10), neutral['body'](-5, -10))
                        self.assertGreater(joints['neck'](35, -12)[0], joints['body'](7, -12)[0])
                        self.assertLess(joints['whip'](-40, -10.6)[0], joints['body'](-9, -11)[0])
        self.assertLess(travels[.18], travels[1] / 3)
        frames = [self.frame(dict(self.pose, reaction=reaction))
                  for reaction in (0, .5, 1)]
        x0, y0 = self.pixel(frames[0], (60, 24.5))
        x1, y1 = self.pixel(frames[0], (65, 27.5))
        torso = [[(frame.chars[y][x], frame.colors[y][x], frame.owners[y][x])
                  for y in range(y0, y1+1) for x in range(x0, x1+1)]
                 for frame in frames]
        self.assertEqual(torso[0], torso[1])
        self.assertEqual(torso[0], torso[2])
        self.assertNotEqual(frames[0].chars, frames[-1].chars)
        self.assertTrue(any(frames[0].chars[y][x] == ' ' for x, y in self.owned(frames[0])))

    def test_four_equal_height_legs_have_small_independent_gait_without_body_bounce(self):
        for motion in (1, .18):
            foot_positions = []
            for phase in (0, math.pi/2, math.pi, 3*math.pi/2):
                joints = _diplodocus_pose(dict(self.pose, phase=phase, stride=1), motion)
                self.assertEqual(len(joints['legs']), 4)
                self.assertEqual(sum(far for far, leg in joints['legs']), 2)
                self.assertEqual(joints['body'](0, -10), (65, 26.5))
                feet = [leg[5] for far, leg in joints['legs']]
                self.assertTrue(all(36.5 - .65*motion <= y <= 36.5 for x, y in feet))
                self.assertGreater(max(y for x, y in feet), min(y for x, y in feet))
                foot_positions.append(feet)
                frame = self.frame(dict(self.pose, phase=phase, stride=1), motion=motion)
                for foot in feet:
                    self.assert_owned_near(frame, foot)
            self.assertNotEqual(foot_positions[0], foot_positions[1])
        resting = _diplodocus_pose(dict(self.pose, stride=0), 1)
        self.assertEqual({leg[0][1] for far, leg in resting['legs']}, {27.5})
        self.assertEqual({leg[5][1] for far, leg in resting['legs']}, {36.5})

    def test_scaling_aspect_and_intermediate_rasters_stay_in_conservative_bounds(self):
        for preset in ('morning', 'dusk'):
            for aspect in (1.2, 2, 3):
                small = self.frame(width=240, height=40, aspect=aspect, preset=preset)
                large = self.frame(width=480, height=80, aspect=aspect, preset=preset)
                a, b = small.bounds('diplodocus'), large.bounds('diplodocus')
                self.assertIsNotNone(a)
                self.assertAlmostEqual(b[2] / a[2], 2, delta=.2)
                self.assertAlmostEqual(b[3] / a[3], 2, delta=.2)
                self.assertGreater(a[2] / (aspect * a[3]), 3)
                for fraction in (0, .25, .5, .75, 1):
                    pose = dict(self.pose, drink=fraction, reaction=1-fraction,
                                look=.04, stride=1, phase=fraction*math.tau)
                    frame = self.frame(pose, height=80, aspect=aspect,
                                       camera=(3.5, -2), preset=preset)
                    dx = .51 / (frame.aspect * frame.scale)
                    dy = .51 / frame.scale
                    self.assertTrue(self.owned(frame))
                    for px, py in self.owned(frame):
                        x, y = frame.unproject(px, py, pose['depth'])
                        self.assertGreaterEqual(x, pose['x'] - 42 - dx)
                        self.assertLessEqual(x, pose['x'] + 40 + dx)
                        self.assertGreaterEqual(y, pose['foot_y'] - 20 - dy)
                        self.assertLessEqual(y, pose['foot_y'] + 5 + dy)

    def test_clip_depth_and_default_owner_are_preserved_including_paint_failure(self):
        full = self.frame()
        for clip in (None, 50):
            canvas = Canvas(480, 120)
            canvas.depth, canvas.clip_bottom, canvas.default_owner = .63, clip, 'scenery'
            _diplodocus(canvas, self.pose, 1, _PALETTES['dusk'])
            self.assertEqual((canvas.depth, canvas.clip_bottom, canvas.default_owner),
                             (.63, clip, 'scenery'))
            if clip is not None:
                self.assertTrue(all(y <= clip for x, y in self.owned(canvas)))
                self.assertLess(len(self.owned(canvas)), len(self.owned(full)))
            canvas.char(50, 20, '*', (1, 2, 3))
            x, y = self.pixel(canvas, (50, 20), .63)
            self.assertEqual(canvas.owners[y][x], 'scenery')
            with patch.object(canvas, 'polygon', side_effect=RuntimeError('interrupted')):
                with self.assertRaises(RuntimeError):
                    _diplodocus(canvas, self.pose, 1, _PALETTES['dusk'])
            self.assertEqual((canvas.depth, canvas.clip_bottom, canvas.default_owner),
                             (.63, clip, 'scenery'))
        swimmer = dict(self.snapshot['plesiosaurus'], visible=True, x=30,
                       water_y=42, body_y=43, look=0, reaction=0)
        canvas = Canvas(480, 120)
        _plesiosaurus(canvas, swimmer, 1, _PALETTES['dusk'])
        self.assertIsNone(canvas.clip_bottom)
        _diplodocus(canvas, self.pose, 1, _PALETTES['dusk'])
        self.assert_owned_near(canvas, (58, 36.5))

    def test_far_trees_are_behind_but_lake_focal_and_foreground_replace_ownership(self):
        isolated = self.frame()
        layout = replace(self.layout, trees=(Tree('behind', 62, 37, 18, 0),))
        far = Canvas(480, 120)
        _distance_and_lake(far, None, None, None, 0, 1, layout, _PALETTES['dusk'])
        backdrop = {(x, y) for y, row in enumerate(far.colors)
                    for x, color in enumerate(row) if color is not None}
        overlap = backdrop & self.owned(isolated)
        self.assertTrue(overlap)
        painted = self.lake_frame(layout=layout)
        self.assertTrue(all(painted.owners[y][x] == 'diplodocus' for x, y in overlap))
        mouth = _diplodocus_pose(self.pose, 1)['neck'](35, -12)
        pad = LilyPad('over_head', mouth[0]-.7, mouth[1], 2, 0, False)
        jump = dict(origin=mouth, x=mouth[0], y=mouth[1], progress=.5)
        swimmer = dict(self.snapshot['plesiosaurus'], x=mouth[0]-.5,
                       body_y=mouth[1]+1.2, water_y=42.5, visible=True,
                       reaction=0, look=0)
        for kind in ('pad', 'jump', 'swimmer'):
            occluder = Canvas(480, 120)
            occluder.depth = WATER_DEPTH
            if kind == 'pad':
                _lily_pad(occluder, pad, 0, _PALETTES['dusk'])
                painted = self.lake_frame(layout=replace(self.layout, lily_pads=(pad,)))
                owner = 'water'
            elif kind == 'jump':
                _water_jump(occluder, jump, _PALETTES['dusk'])
                painted = self.lake_frame(jump=jump)
                owner = 'water'
            else:
                _plesiosaurus(occluder, swimmer, 1, _PALETTES['dusk'])
                painted = self.lake_frame(swimmer=swimmer)
                owner = 'plesiosaurus'
            overlap = self.owned(isolated) & self.owned(occluder, owner)
            self.assertTrue(overlap, kind)
            self.assertTrue(all(painted.owners[y][x] == owner for x, y in overlap), kind)
        for kind in ('tree', 'brachiosaurus', 'rock'):
            occluder = Canvas(480, 120)
            # Place the swimmer under the focal group, independently of where
            # the scene composition authors that group.
            pose = dict(self.pose, x=self.pose['x'] + FOCAL_OFFSET_X) if kind != 'rock' else self.pose
            foreground_isolated = self.frame(pose)
            painted = self.frame(pose)
            if kind == 'tree':
                paint = lambda c: _focal_tree(c, 0, 1, 0, _PALETTES['dusk'])
            elif kind == 'brachiosaurus':
                paint = lambda c: _brachiosaurus(c, self.snapshot, 1, _PALETTES['dusk'])
            else:
                front_layout = replace(self.layout, rocks=(Rock('over_body', 63, 29, 1, 'pebble'),))
                paint = lambda c: _foreground(c, 0, 1, front_layout, _PALETTES['dusk'])
            paint(occluder)
            paint(painted)
            pixels = {(x, y) for y, row in enumerate(occluder.colors)
                      for x, color in enumerate(row) if color is not None}
            overlap = pixels & self.owned(foreground_isolated)
            self.assertTrue(overlap, kind)
            for x, y in overlap:
                self.assertNotEqual(painted.owners[y][x], 'diplodocus', kind)
                self.assertEqual((painted.chars[y][x], painted.colors[y][x], painted.owners[y][x]),
                                 (occluder.chars[y][x], occluder.colors[y][x], occluder.owners[y][x]))
            if kind == 'rock':
                self.assertTrue(any(occluder.chars[y][x] == ' ' for x, y in overlap))

    def test_singleton_selection_absence_and_random_mode_have_real_raster_effects(self):
        for random in (False, True):
            for enabled, cap, active, x in ((True, 8, True, 65), (False, 8, True, 65),
                                             (True, 1, True, 65), (True, 8, False, 65),
                                             (True, 8, True, -100)):
                config = copy.deepcopy(self.config)
                config['animals']['diplodocusEnabled'] = enabled
                config['population'].update(maxVisible=cap, randomVisitors=random)
                snapshot = copy.deepcopy(self.snapshot)
                snapshot['diplodocus'] = dict(self.pose, x=x) if active else None
                canvas = Canvas(480, 120, snapshot['camera'])
                selected = visible_cast_members(canvas, snapshot, config)
                expected = enabled and cap > 1 and active and x == 65
                self.assertEqual('diplodocus' in selected, expected)
                self.assertLessEqual(len(selected), cap)
                draw_scene(canvas, snapshot, config)
                owners = {owner for row in canvas.owners for owner in row
                          if isinstance(owner, str) and owner.startswith('diplodocus')}
                self.assertEqual(owners, {'diplodocus'} if expected else set())
                if expected:
                    self.assert_owned_near(canvas, (60, 26.5))
                else:
                    baseline_config = copy.deepcopy(config)
                    baseline_config['animals']['diplodocusEnabled'] = False
                    baseline = Canvas(480, 120, snapshot['camera'])
                    draw_scene(baseline, snapshot, baseline_config)
                    self.assertEqual(canvas.chars, baseline.chars)
                    self.assertEqual(canvas.colors, baseline.colors)
                    self.assertEqual(canvas.owners, baseline.owners)


if __name__ == '__main__':
    unittest.main()
