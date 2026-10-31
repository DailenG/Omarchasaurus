import copy
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from configuration import settings
from canvas import Canvas
from engine import World
from character_art import (_PALETTES, _parasaurolophus, _parasaurolophus_pose,
                           draw_scene, visible_cast_members)


class ParasaurolophusArtwork(unittest.TestCase):
    def setUp(self):
        self.config = settings({
            'animals': {'trexEnabled': False, 'triceratopsEnabled': False,
                        'stegosaurusEnabled': False, 'ankylosaurusEnabled': False,
                        'pteranodonEnabled': False, 'plesiosaurusEnabled': False,
                        'diplodocusEnabled': False},
            'population': {'maxVisible': 3, 'maxFamilies': 1, 'randomVisitors': False},
            'scenery': {key: False if key == 'nestEnabled' else 0
                        for key in settings()['scenery']},
        })
        self.snapshot = World(self.config).snapshot()
        self.member = dict(self.snapshot['parasaurolophus_families'][0]['members'][0])
        self.member.update(x=70, scale=1, foot_y=49.5, phase=0, stride=0,
                           drink=0, reaction=0, blink=False, state='resting')

    def frame(self, member=None, motion=1, width=400, height=120, aspect=2,
              camera=(0, 0), preset='morning'):
        canvas = Canvas(width, height, camera, cell_aspect=aspect)
        _parasaurolophus(canvas, self.member if member is None else member,
                        motion, _PALETTES[preset])
        return canvas

    def owned(self, canvas, owner=None):
        owner = self.member['id'] if owner is None else owner
        return {(x, y) for y, row in enumerate(canvas.owners)
                for x, value in enumerate(row) if value == owner}

    def assert_owned_near(self, canvas, point, owner):
        px, py = canvas.project(*point)
        self.assertTrue(any(abs(x-px) <= 1.5 and abs(y-py) <= 1.5
                            for x, y in self.owned(canvas, owner)), point)

    def test_reaction_moves_rigid_skull_and_tail_without_changing_rendered_torso(self):
        frames = []
        travel = {}
        for motion in (1, .18):
            poses = []
            for reaction in (0, 1):
                member = dict(self.member, reaction=reaction)
                joints = _parasaurolophus_pose(member, motion)
                frame = self.frame(member, motion)
                poses.append(joints)
                if motion == 1:
                    frames.append(frame)
                for part, a, b in (
                    ('body', (-4, -9), (2, -5)),
                    ('head', (7.8, -11.3), (12.8, -10)),
                    ('head', joints['crest_tip'], (12.8, -10)),
                    ('tail', (-14.3, -8.6), (-6, -7.7)),
                ):
                    self.assertAlmostEqual(math.dist(joints[part](*a), joints[part](*b)),
                                           math.dist(a, b), places=7)
                self.assert_owned_near(frame, joints['head'](7.8, -11.3), member['id'])
            travel[motion] = math.dist(poses[0]['head'](7.8, -11.3),
                                       poses[1]['head'](7.8, -11.3))
        self.assertLess(travel[.18], travel[1] / 2)
        torso = []
        for frame in frames:
            low_x, low_y = map(round, frame.project(66, 41.5))
            high_x, high_y = map(round, frame.project(69, 44.5))
            torso.append([(frame.chars[y][x], frame.owners[y][x])
                          for y in range(low_y, high_y + 1)
                          for x in range(low_x, high_x + 1)])
        self.assertEqual(torso[0], torso[1])
        self.assertNotEqual(frames[0].chars, frames[1].chars)

    def test_click_lifts_a_drinking_head_with_a_smaller_reduced_motion_response(self):
        member = dict(self.member, drink=1, reaction=0)
        resting = _parasaurolophus_pose(member, 1)['head'](12.8, -10)
        normal = _parasaurolophus_pose(dict(member, reaction=1), 1)['head'](12.8, -10)
        calm = _parasaurolophus_pose(dict(member, reaction=1), .18)['head'](12.8, -10)
        self.assertLess(normal[1], resting[1] - 3)
        self.assertLess(calm[1], resting[1])
        self.assertLess(math.dist(resting, calm), math.dist(resting, normal) / 2)

    def test_drinking_lowers_bill_and_rotates_crest_even_without_decorative_motion(self):
        for scale in (1, .72, .6, .5):
            for motion in (1, .18, 0):
                with self.subTest(scale=scale, motion=motion):
                    member = dict(self.member, scale=scale, drink=1, stride=0,
                                  reaction=0, state='drinking')
                    joints = _parasaurolophus_pose(member, motion)
                    upright = _parasaurolophus_pose(dict(member, drink=0, reaction=0), 0)
                    bill = joints['head'](12.8, -10)
                    self.assertGreater(bill[1] - upright['head'](12.8, -10)[1], 3)
                    self.assertGreaterEqual(bill[1], 47)
                    self.assertLessEqual(bill[1], 48.1)
                    for a, b in (((7.8, -11.3), (12.8, -10)),
                                 (joints['crest_tip'], (12.8, -10))):
                        self.assertAlmostEqual(math.dist(joints['head'](*a), joints['head'](*b)),
                                               math.dist(a, b) * scale, places=7)
                    frame = self.frame(member, motion)
                    for landmark in ((12.8, -10), joints['crest_tip']):
                        self.assert_owned_near(frame, joints['head'](*landmark), member['id'])
                    # Motion preferences must not attenuate the functional bend.
                    self.assertEqual(bill, _parasaurolophus_pose(member, 0)['head'](12.8, -10))

    def test_juvenile_has_shorter_crest_and_proportionally_smaller_body(self):
        adult = _parasaurolophus_pose(self.member, 0)
        juvenile_member = dict(self.member, scale=.6)
        juvenile = _parasaurolophus_pose(juvenile_member, 0)
        adult_crest = math.dist(adult['head'](*adult['crest_tip']), adult['head'](5.9, -12.3))
        juvenile_crest = math.dist(juvenile['head'](*juvenile['crest_tip']),
                                   juvenile['head'](5.9, -12.3))
        self.assertLess(juvenile_crest, adult_crest * .4)
        for a, b in (((-6, -7), (3, -9)), ((-4, -10), (1, -4))):
            self.assertAlmostEqual(math.dist(juvenile['body'](*a), juvenile['body'](*b)),
                                   math.dist(adult['body'](*a), adult['body'](*b)) * .6)
        adult_bounds = self.frame(motion=0).bounds(self.member['id'])
        juvenile_bounds = self.frame(juvenile_member, motion=0).bounds(self.member['id'])
        self.assertAlmostEqual(juvenile_bounds[2] / adult_bounds[2], .6, delta=.04)
        self.assertLess(juvenile_bounds[3], adult_bounds[3] * .6)
        for preset in ('morning', 'dusk'):
            for aspect in (1.2, 3):
                small = self.frame(width=200, height=60, aspect=aspect, preset=preset)
                large = self.frame(width=400, height=120, aspect=aspect, preset=preset)
                a, b = small.bounds(self.member['id']), large.bounds(self.member['id'])
                self.assertAlmostEqual(b[2] / a[2], 2, delta=.12)
                self.assertAlmostEqual(b[3] / a[3], 2, delta=.12)

    def test_all_articulation_stays_inside_member_envelope_and_uses_family_depth(self):
        for scale in (1, .72, .6, .5):
            for phase in (0, math.pi / 2, math.pi, math.pi * 1.5):
                for drink, reaction in ((0, 0), (0, 1), (.45, 0), (1, 0), (1, .4), (1, 1)):
                    member = dict(self.member, scale=scale, phase=phase, stride=1,
                                  drink=drink, reaction=reaction)
                    frame = self.frame(member, camera=(7, -2), aspect=3)
                    self.assertEqual(frame.depth, .32)
                    points = [frame.unproject(x, y, .32) for x, y in self.owned(frame)]
                    joints = _parasaurolophus_pose(member, 1)
                    self.assert_owned_near(frame, joints['head'](7.8, -11.3), member['id'])
                    # Raster rounding is at most half a terminal cell per axis.
                    dx = .51 / (frame.aspect * frame.scale)
                    dy = .51 / frame.scale
                    for x, y in points:
                        self.assertGreaterEqual(x, member['x'] - 15 * scale - dx)
                        self.assertLessEqual(x, member['x'] + 16 * scale + dx)
                        self.assertGreaterEqual(y, member['foot_y'] - 20 * scale - dy)
                        self.assertLessEqual(y, member['foot_y'] + dy)

    def test_four_weight_bearing_limbs_have_grounded_feet_in_rest_drink_and_clicks(self):
        for scale in (1, .72, .6, .5):
            for width, height in ((200, 60), (400, 120)):
                for drink, reaction in ((0, 0), (1, 0), (0, 1), (1, 1)):
                    with self.subTest(scale=scale, grid=(width, height),
                                      drink=drink, reaction=reaction):
                        member = dict(self.member, scale=scale, drink=drink,
                                      reaction=reaction)
                        joints = _parasaurolophus_pose(member, 1)
                        legs = joints['legs']
                        self.assertEqual({(leg['far'], leg['fore']) for leg in legs},
                                         {(far, fore) for far in (True, False)
                                          for fore in (True, False)})
                        frame = self.frame(member, width=width, height=height)
                        for leg in legs:
                            self.assertEqual(leg['foot'][1], member['foot_y'])
                            self.assertEqual(max(y for x, y in leg['points']),
                                             member['foot_y'])
                            self.assert_owned_near(frame, leg['foot'], member['id'])
                        fore = [leg for leg in legs if leg['fore']]
                        hind = [leg for leg in legs if not leg['fore']]
                        # Shorter, narrower forelimbs support the shoulder instead
                        # of hanging as arms beside the chest.
                        self.assertGreater(min(leg['points'][0][1] for leg in fore),
                                           max(leg['points'][0][1] for leg in hind))
                        self.assertGreater(min(leg['foot'][0] for leg in fore),
                                           max(leg['foot'][0] for leg in hind) + 4 * scale)
                        px, py = map(round, frame.project(member['x'] + 2 * scale,
                                                         member['foot_y']))
                        self.assertNotEqual(frame.owners[py][px], member['id'])

    def test_gait_lifts_only_swing_feet_and_keeps_clicks_out_of_the_support_geometry(self):
        for phase in (0, .7, math.pi / 2, math.pi, math.pi * 1.5):
            member = dict(self.member, stride=1, phase=phase)
            legs = _parasaurolophus_pose(member, 1)['legs']
            clicked = _parasaurolophus_pose(dict(member, reaction=1), 1)['legs']
            self.assertEqual(legs, clicked)
            self.assertGreaterEqual(sum(abs(leg['foot'][1] - member['foot_y']) < 1e-8
                                        for leg in legs), 2)
            frame = self.frame(member)
            for leg in legs:
                self.assertGreaterEqual(leg['foot'][1], member['foot_y'] - .45)
                self.assertLessEqual(leg['foot'][1], member['foot_y'])
                self.assert_owned_near(frame, leg['foot'], member['id'])
            next_legs = _parasaurolophus_pose(dict(member, phase=phase + .001), 1)['legs']
            for leg, next_leg in zip(legs, next_legs):
                self.assertLess(math.dist(leg['foot'], next_leg['foot']), .002)
        still = _parasaurolophus_pose(dict(self.member, stride=1, phase=.7), 0)['legs']
        self.assertTrue(all(leg['foot'][1] == self.member['foot_y'] for leg in still))

    def test_adult_crest_sweeps_back_above_a_horizontal_counterweight(self):
        joints = _parasaurolophus_pose(self.member, 0)
        base = joints['head'](5.9, -12.3)
        tip = joints['head'](*joints['crest_tip'])
        self.assertLess(tip[0], base[0] - 8)
        self.assertGreater(tip[1], base[1] - 4)
        tail_tip = joints['tail'](-14.3, -8.6)
        tail_base = joints['tail'](-6, -7.7)
        self.assertLess(abs(tail_tip[1] - tail_base[1]), 1)
        self.assertLess(tail_tip[1], self.member['foot_y'] - 8)

    def test_real_cast_renders_only_selected_individuals_and_clips_at_viewport_edge(self):
        snapshot = copy.deepcopy(self.snapshot)
        for family_index, family in enumerate(snapshot['parasaurolophus_families']):
            for index, member in enumerate(family['members']):
                member.update(x=38 - index * 18 + family_index * 5,
                              drink=0, reaction=0, phase=0, stride=0)
        canvas = Canvas(500, 120, snapshot['camera'])
        selected = set(visible_cast_members(canvas, snapshot, self.config))
        draw_scene(canvas, snapshot, self.config)
        family_ids = {member['id'] for family in snapshot['parasaurolophus_families']
                      for member in family['members']}
        owners = {owner for row in canvas.owners for owner in row if owner in family_ids}
        expected = {member['id'] for member in snapshot['parasaurolophus_families'][0]['members'][:2]}
        self.assertEqual(selected & family_ids, expected)
        self.assertEqual(owners, expected)
        self.assertFalse(any(family['id'] in row for row in canvas.owners
                             for family in snapshot['parasaurolophus_families']))
        # Cropping is a Canvas projection, never a second miniature animal.
        reference = self.frame(width=400, height=120)
        clipped = self.frame(width=400, height=120, camera=(160, 0))
        self.assert_owned_near(clipped, _parasaurolophus_pose(self.member, 1)['head'](12.8, -10),
                               self.member['id'])
        self.assertLess(clipped.bounds(self.member['id'])[2], reference.bounds(self.member['id'])[2])
        offscreen = self.frame(width=400, height=120, camera=(1000, 0))
        self.assertFalse(self.owned(offscreen))

    def test_family_silhouette_is_occluded_by_focal_brachiosaurus(self):
        snapshot = copy.deepcopy(self.snapshot)
        for index, member in enumerate(snapshot['parasaurolophus_families'][0]['members']):
            member.update(x=72 if index == 0 else 20 - index * 16,
                          drink=0, reaction=0, phase=0, stride=0)
        baseline_config = copy.deepcopy(self.config)
        baseline_config['population']['maxFamilies'] = 0
        baseline = Canvas(500, 120, snapshot['camera'])
        draw_scene(baseline, snapshot, baseline_config)
        frame = Canvas(500, 120, snapshot['camera'])
        draw_scene(frame, snapshot, self.config)
        adult = snapshot['parasaurolophus_families'][0]['members'][0]
        isolated = Canvas(500, 120, snapshot['camera'])
        _parasaurolophus(isolated, adult, 1, _PALETTES['morning'])
        focal_pixels = self.owned(baseline, 'brachiosaurus')
        self.assertTrue(focal_pixels & self.owned(isolated, adult['id']))
        remaining = self.owned(frame, adult['id'])
        self.assertTrue(remaining)
        self.assertTrue(remaining <= self.owned(isolated, adult['id']))
        self.assertFalse(remaining & focal_pixels)
        self.assertEqual(self.owned(frame, 'brachiosaurus'), focal_pixels)


if __name__ == '__main__':
    unittest.main()
