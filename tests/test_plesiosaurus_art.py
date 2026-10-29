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
from character_art import (_PALETTES, _distance_and_lake, _foreground, _lily_pad,
                           _plesiosaurus, _plesiosaurus_pose, _water_jump,
                           draw_scene, visible_cast_members)
from layout import WATER_DEPTH, LilyPad, Rock


class PlesiosaurusArtwork(unittest.TestCase):
    def setUp(self):
        self.config = settings({
            'animals': {'trexEnabled': False, 'triceratopsEnabled': False,
                        'stegosaurusEnabled': False, 'ankylosaurusEnabled': False,
                        'parasaurolophusEnabled': False, 'pteranodonEnabled': False,
                        'plesiosaurusEnabled': True, 'diplodocusEnabled': False},
            'population': {'maxVisible': 8, 'maxFamilies': 0, 'randomVisitors': False},
            'scenery': {key: False if key == 'nestEnabled' else 0
                        for key in settings()['scenery']},
        })
        self.snapshot = World(self.config).snapshot()
        self.pose = dict(self.snapshot['plesiosaurus'], x=35, water_y=42.5,
                         body_y=43, emergence=1, look=0, reaction=0, blink=False,
                         visible=True, state='looking', depth=WATER_DEPTH)
        self.snapshot['plesiosaurus'] = self.pose

    @staticmethod
    def owned(canvas, owner='plesiosaurus'):
        return {(x, y) for y, row in enumerate(canvas.owners)
                for x, value in enumerate(row) if value == owner}

    def frame(self, pose=None, motion=1, width=480, height=120, aspect=2,
              camera=(0, 0), preset='morning'):
        canvas = Canvas(width, height, camera, cell_aspect=aspect)
        _plesiosaurus(canvas, self.pose if pose is None else pose,
                      motion, _PALETTES[preset])
        return canvas

    def assert_owned_near(self, canvas, point):
        previous = canvas.depth
        canvas.depth = WATER_DEPTH
        px, py = canvas.project(*point)
        canvas.depth = previous
        self.assertTrue(any(abs(x-px) <= 1.5 and abs(y-py) <= 1.5
                            for x, y in self.owned(canvas)), point)

    def test_rigid_head_neck_and_torso_survive_look_click_and_dive_translation(self):
        travel = {}
        for motion in (1, .18):
            neutral = _plesiosaurus_pose(self.pose, motion)
            reacting = _plesiosaurus_pose(dict(self.pose, reaction=1), motion)
            travel[motion] = math.dist(neutral['neck'](4.6, -11.7),
                                      reacting['neck'](4.6, -11.7))
            for look in (-.15, 0, .15):
                for reaction in (0, 1):
                    for descent in (0, 4.25, 8.5, 17):
                        pose = dict(self.pose, look=look, reaction=reaction,
                                    body_y=self.pose['body_y'] + descent)
                        joints = _plesiosaurus_pose(pose, motion)
                        for part, a, b in (
                            ('body', (-5.3, -1.2), (3.8, -2.1)),
                            ('body', (-4, -2.1), (-11.4, -.4)),
                            ('neck', (1.5, -1.6), (3, -10.4)),
                            ('neck', (4.6, -11.7), (7.7, -11.2)),
                        ):
                            self.assertAlmostEqual(math.dist(joints[part](*a),
                                                             joints[part](*b)),
                                                   math.dist(a, b), places=7)
                        for part in ('body', 'neck'):
                            surface = _plesiosaurus_pose(dict(pose, body_y=43), motion)
                            for point in ((1.5, -1.6), (4.6, -11.7)):
                                a, b = surface[part](*point), joints[part](*point)
                                self.assertAlmostEqual(a[0], b[0])
                                self.assertAlmostEqual(b[1] - a[1], descent)
        self.assertGreater(travel[1], 3)
        self.assertLess(travel[.18], travel[1] / 3)
        frames = [self.frame(dict(self.pose, reaction=value)) for value in (0, 1)]
        for frame in frames:
            joints = _plesiosaurus_pose(self.pose, 1)
            self.assert_owned_near(frame, joints['body'](-2, -2))
            self.assert_owned_near(frame, joints['body'](-8, -.8))
        for reaction, frame in zip((0, 1), frames):
            joints = _plesiosaurus_pose(dict(self.pose, reaction=reaction), 1)
            self.assert_owned_near(frame, joints['neck'](4.6, -11.7))
        # The left torso is outside the neck pivot, so a click must leave its
        # actual opaque raster (including blank interiors) unchanged.
        x0, y0 = map(round, frames[0].project(31.5, 40.7))
        x1, y1 = map(round, frames[0].project(34, 42))
        regions = [[(frame.chars[y][x], frame.colors[y][x], frame.owners[y][x])
                    for y in range(y0, y1+1) for x in range(x0, x1+1)]
                   for frame in frames]
        self.assertEqual(regions[0], regions[1])
        self.assertNotEqual(frames[0].chars, frames[1].chars)
        self.assertTrue(any(frame.chars[y][x] == ' '
                            for frame in frames for x, y in self.owned(frame)))

    def test_progressive_dives_clip_at_one_fixed_plane_without_stealing_underwater(self):
        counts = []
        for emergence in (1, .75, .5, .35, 0):
            body_y = self.pose['water_y'] + .5 + 17 * (1-emergence)
            pose = dict(self.pose, body_y=body_y, emergence=emergence,
                        visible=emergence > 0 and body_y-14 <= self.pose['water_y'])
            canvas = Canvas(480, 160, (7, -2))
            canvas.depth = WATER_DEPTH
            plane = math.floor(canvas.project(0, pose['water_y'])[1])
            # Real underwater scenery is deliberately present before drawing.
            canvas.line(20, 45, 50, 45, (11, 22, 33), glyph='~', owner='water')
            canvas.char(30, 25, '*', (44, 55, 66), owner='sky')
            sx, sy = map(round, canvas.project(30, 25))
            before = [(list(canvas.chars[y]), list(canvas.colors[y]),
                       list(canvas.owners[y])) for y in range(plane+1, canvas.height)]
            _plesiosaurus(canvas, pose, 1, _PALETTES['morning'])
            points = self.owned(canvas)
            counts.append(len(points))
            self.assertTrue(all(y <= plane for x, y in points))
            reduced = self.frame(pose, motion=.18, width=480, height=160, camera=(7, -2))
            self.assertEqual(self.owned(reduced), points)
            self.assertEqual((canvas.chars[sy][sx], canvas.colors[sy][sx],
                              canvas.owners[sy][sx]), ('*', (44, 55, 66), 'sky'))
            after = [(canvas.chars[y], canvas.colors[y], canvas.owners[y])
                     for y in range(plane+1, canvas.height)]
            self.assertEqual(after, before)
            # A tiny head remains late in the dive; it cannot jump to a new x.
            if emergence == .35:
                self.assert_owned_near(canvas, _plesiosaurus_pose(pose, 1)['neck'](4.6, -11.7))
        self.assertTrue(all(a > b for a, b in zip(counts, counts[1:])), counts)
        self.assertEqual(counts[-1], 0)

    def test_clip_depth_owner_are_restored_for_following_scenery_even_on_error(self):
        for old_clip in (None, 95):
            canvas = Canvas(480, 160)
            canvas.depth = .61
            canvas.default_owner = 'scenery'
            canvas.clip_bottom = old_clip
            _plesiosaurus(canvas, self.pose, 1, _PALETTES['morning'])
            self.assertEqual((canvas.depth, canvas.clip_bottom, canvas.default_owner),
                             (.61, old_clip, 'scenery'))
            if old_clip is None:
                canvas.char(75, 55, '#', (1, 2, 3))
                x, y = map(round, canvas.project(75, 55))
                self.assertEqual((canvas.chars[y][x], canvas.owners[y][x]), ('#', 'scenery'))
            else:
                self.assertTrue(all(y <= old_clip for x, y in self.owned(canvas)))
                canvas.put(10, old_clip, '#', (1, 2, 3))
                canvas.put(10, old_clip+1, '#', (1, 2, 3))
                self.assertEqual(canvas.owners[old_clip][10], 'scenery')
                self.assertNotEqual(canvas.chars[old_clip+1][10], '#')
            with patch.object(canvas, 'polygon', side_effect=RuntimeError('paint interrupted')):
                with self.assertRaises(RuntimeError):
                    _plesiosaurus(canvas, self.pose, 1, _PALETTES['morning'])
            self.assertEqual((canvas.depth, canvas.clip_bottom, canvas.default_owner),
                             (.61, old_clip, 'scenery'))

    def test_world_scaling_aspect_palettes_and_articulation_stay_inside_envelope(self):
        for preset in ('morning', 'dusk'):
            for aspect in (1.2, 2, 3):
                small = self.frame(width=240, height=40, aspect=aspect, preset=preset)
                large = self.frame(width=480, height=80, aspect=aspect, preset=preset)
                a, b = small.bounds('plesiosaurus'), large.bounds('plesiosaurus')
                self.assertAlmostEqual(b[2] / a[2], 2, delta=.3)
                self.assertAlmostEqual(b[3] / a[3], 2, delta=.3)
                for look in (-.15, .15):
                    for reaction in (0, 1):
                        pose = dict(self.pose, look=look, reaction=reaction)
                        frame = self.frame(pose, height=80, aspect=aspect,
                                           camera=(7, -2), preset=preset)
                        dx = .51 / (frame.aspect * frame.scale)
                        dy = .51 / frame.scale
                        for px, py in self.owned(frame):
                            x, y = frame.unproject(px, py, WATER_DEPTH)
                            self.assertGreaterEqual(x, pose['x']-12-dx)
                            self.assertLessEqual(x, pose['x']+12+dx)
                            self.assertGreaterEqual(y, pose['body_y']-14-dy)
                            self.assertLessEqual(y, pose['water_y'])

    def test_unselected_disabled_and_submerged_emit_no_silhouette_or_wake(self):
        for enabled, cap, visible in ((True, 8, True), (False, 8, True),
                                      (True, 1, True), (True, 8, False)):
            config = copy.deepcopy(self.config)
            config['animals']['plesiosaurusEnabled'] = enabled
            config['population']['maxVisible'] = cap
            snapshot = copy.deepcopy(self.snapshot)
            if not visible:
                snapshot['plesiosaurus'].update(emergence=0, body_y=60, visible=False,
                                                state='submerged')
            canvas = Canvas(480, 160, snapshot['camera'])
            selected = set(visible_cast_members(canvas, snapshot, config))
            expected = enabled and cap > 1 and visible
            self.assertEqual('plesiosaurus' in selected, expected)
            self.assertLessEqual(len(selected), cap)
            draw_scene(canvas, snapshot, config)
            if expected:
                self.assert_owned_near(canvas, _plesiosaurus_pose(snapshot['plesiosaurus'], 1)['neck'](4.6, -11.7))
                self.assertEqual({name for row in canvas.owners for name in row
                                  if isinstance(name, str) and name.startswith('plesiosaurus')},
                                 {'plesiosaurus'})
            else:
                self.assertFalse(self.owned(canvas))
                baseline_config = copy.deepcopy(config)
                baseline_config['animals']['plesiosaurusEnabled'] = False
                baseline = Canvas(480, 160, snapshot['camera'])
                draw_scene(baseline, snapshot, baseline_config)
                self.assertEqual(canvas.chars, baseline.chars)
                self.assertEqual(canvas.colors, baseline.colors)
                self.assertEqual(canvas.owners, baseline.owners)

    def test_lily_pads_jump_and_foreground_replace_swimmer_click_ownership(self):
        layout = replace(self.snapshot['layout'], lily_pads=(
            LilyPad('occluding_pad', 33, 41.4, 2, 0, False),))
        jump = {'origin': (35, 42.5), 'x': 39.6, 'y': 31.8, 'progress': .5}
        isolated = self.frame()
        pad = Canvas(480, 120)
        pad.depth = WATER_DEPTH
        _lily_pad(pad, layout.lily_pads[0], 0, _PALETTES['morning'])
        fish = Canvas(480, 120)
        fish.depth = WATER_DEPTH
        _water_jump(fish, jump, _PALETTES['morning'])
        frame = Canvas(480, 120)
        _distance_and_lake(frame, jump, self.pose, None, 0, 1, layout, _PALETTES['morning'])
        for occluder in (pad, fish):
            overlap = self.owned(isolated) & self.owned(occluder, 'water')
            self.assertTrue(overlap)
            self.assertTrue(all(frame.owners[y][x] == 'water' for x, y in overlap))
        # Use an actual foreground rock, whose blank interior must remove both
        # visible strokes and click ownership, not merely draw over their edges.
        layout = replace(layout, rocks=(Rock('occluding_rock', 35, 42, 1, 'pebble'),))
        foreground = Canvas(480, 120)
        _foreground(foreground, 0, 1, layout, _PALETTES['morning'])
        rock_pixels = {(x, y) for y, row in enumerate(foreground.colors)
                       for x, color in enumerate(row) if color is not None}
        overlap = rock_pixels & self.owned(isolated)
        self.assertTrue(overlap)
        _foreground(frame, 0, 1, layout, _PALETTES['morning'])
        for x, y in overlap:
            self.assertIsNone(frame.owners[y][x])
            self.assertEqual((frame.chars[y][x], frame.colors[y][x]),
                             (foreground.chars[y][x], foreground.colors[y][x]))


if __name__ == '__main__':
    unittest.main()
