import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from canvas import Canvas
from character_art import _PALETTES, _trex, _trex_pose
from tyrannosaurus import tyrannosaurus_pose


class TyrannosaurusArtwork(unittest.TestCase):
    def pose(self, time, reduced=False, reaction=0):
        pose = tyrannosaurus_pose(time, time, 0, 0, reaction, .7, reduced)
        pose.update(time=time, trex_x=65, trex_blink=False)
        return pose

    def frame(self, pose, motion=1, width=500, height=160, aspect=2):
        canvas = Canvas(width, height, cell_aspect=aspect)
        _trex(canvas, pose, motion, _PALETTES['morning'])
        return canvas

    def owned(self, canvas):
        return {(x, y) for y, row in enumerate(canvas.owners)
                for x, owner in enumerate(row) if owner == 'trex'}

    def test_body_skull_jaw_and_tail_keep_rigid_dimensions_through_every_action(self):
        for time in (1, 19.5, 21, 42.5, 45, 47, 66, 66.5, 67.5, 69, 71, 71.99):
            for reaction in (0, .5, 1):
                pose = self.pose(time, reaction=reaction)
                joints = _trex_pose(pose, 1)
                for part, a, b in (('body', (-4, 41), (5, 46)),
                                    ('head', (3.5, 38.5), (17.8, 35)),
                                    ('jaw', (11.8, 36.8), (18, 39.1)),
                                    ('tail', (-4.8, 43.8), (-16, 47))):
                    self.assertAlmostEqual(math.dist(joints[part](*a), joints[part](*b)),
                                           math.dist(a, b), places=7)
                neutral = _trex_pose(self.pose(time), 1)
                for point in ((-4, 41), (0, 44), (5, 46)):
                    self.assertEqual(joints['body'](*point), neutral['body'](*point))
        standing = _trex_pose(self.pose(21), 1)
        sitting = _trex_pose(self.pose(69), 1)
        drop = sitting['body'](-2, 46.7)[1] - standing['body'](-2, 46.7)[1]
        self.assertTrue(2 < drop < 4)

    def test_seated_legs_fold_with_constant_bones_and_grounded_stationary_feet(self):
        for motion in (1, .18):
            feet = None
            knees = []
            for time in (66, 66.5, 67.5, 69, 71, 72):
                pose = self.pose(time)
                joints = _trex_pose(pose, motion)
                current_feet = tuple(leg['foot'] for leg in joints['legs'])
                if feet is None:
                    feet = current_feet
                self.assertEqual(current_feet, feet)
                for leg in joints['legs']:
                    self.assertAlmostEqual(math.dist(leg['hip'], leg['knee']), 3.4)
                    self.assertAlmostEqual(math.dist(leg['knee'], leg['ankle']), 3.7)
                    self.assertEqual(leg['foot'][1], 54)
                knees.append(joints['legs'][0]['knee'])
                canvas = self.frame(pose, motion)
                for foot in current_feet:
                    px, py = map(round, canvas.project(foot[0]+1.4, foot[1]))
                    self.assertTrue(any(abs(x-px) <= 1 and abs(y-py) <= 1
                                        for x, y in self.owned(canvas)))
            self.assertGreater(knees[3][0], knees[0][0])

    def test_silent_roar_opens_a_real_unowned_mouth_gap_without_enlarging_skull(self):
        ordinary, calm = self.pose(45), self.pose(45, reduced=True)
        open_joints, calm_joints = _trex_pose(ordinary, 1), _trex_pose(calm, .18)
        def gap(joints):
            upper = joints['head'](17.2, 36.8)
            lower = joints['jaw'](18, 37.3)
            return upper, lower, math.dist(upper, lower)
        upper, lower, distance = gap(open_joints)
        self.assertGreater(distance, gap(calm_joints)[2] * 2)
        canvas = self.frame(ordinary)
        mouth = tuple((a+b)/2 for a, b in zip(upper, lower))
        x, y = map(round, canvas.project(*mouth))
        self.assertNotEqual(canvas.owners[y][x], 'trex')
        for point in (upper, lower):
            x, y = map(round, canvas.project(*point))
            self.assertTrue(any(abs(px-x) <= 1 and abs(py-y) <= 1
                                for px, py in self.owned(canvas)))
        self.assertEqual(calm['trex_roar'], 0)

    def test_scaled_intermediate_rasters_remain_in_the_existing_ground_envelope(self):
        for aspect in (1.2, 2, 3):
            for time in (19.5, 45, 66.5, 69, 71):
                pose = self.pose(time)
                small = self.frame(pose, width=240, height=80, aspect=aspect)
                large = self.frame(pose, width=480, height=160, aspect=aspect)
                a, b = small.bounds('trex'), large.bounds('trex')
                self.assertAlmostEqual(b[2] / a[2], 2, delta=.25)
                self.assertAlmostEqual(b[3] / a[3], 2, delta=.25)
                for reaction in (0, .5, 1):
                    canvas = self.frame(self.pose(time, reaction=reaction), aspect=aspect)
                    dx = .51 / (canvas.aspect * canvas.scale)
                    dy = .51 / canvas.scale
                    for x, y in self.owned(canvas):
                        wx, wy = canvas.unproject(x, y, .55)
                        self.assertTrue(65-18-dx <= wx <= 65+23+dx)
                        self.assertTrue(29-dy <= wy <= 55+dy)


if __name__ == '__main__':
    unittest.main()
