import copy
from dataclasses import replace
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from canvas import Canvas
from character_art import (_PALETTES, _brachiosaurus, _brachiosaurus_pose, _egg,
                           _focal_tree, _foreground, _nest, _triceratops, _young_brachiosaurus,
                           _young_brachiosaurus_pose, draw_scene, visible_cast_members)
from configuration import settings
from engine import World
from hatching import NEST_DEPTH, NestHatching, SECOND, YOUNG_EXTENTS, YOUNG_HEIGHT, egg_offsets
from layout import FOCAL_OFFSET_X, Nest, generate_layout


class StrokeCanvas(Canvas):
    """Record the actual world strokes, including sampled curved boundaries."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.points = []

    def line(self, x1, y1, x2, y2, *args, **kwargs):
        self.points.extend(((x1, y1), (x2, y2)))
        return super().line(x1, y1, x2, y2, *args, **kwargs)

    def char(self, x, y, *args, **kwargs):
        self.points.append((x, y))
        return super().char(x, y, *args, **kwargs)


class HatchingArtwork(unittest.TestCase):
    def setUp(self):
        self.config = settings({
            'animals': {name: False for name in settings()['animals']},
            'population': {'maxVisible': 2, 'maxFamilies': 0, 'randomVisitors': False},
            'scenery': {key: True if key == 'nestEnabled' else 0
                        for key in settings()['scenery']},
        })
        self.snapshot = World(self.config).snapshot()
        self.nest = Nest('nest', 86, 54, 2.5, 4)
        self.pose = dict(id='brachiosaurus:young', generation=1, state='toddling',
                         egg_index=3, egg_x=87.2, egg_y=53.2, wobble=0, crack=1,
                         emerge=1, reset=0, x=86, foot_y=54, depth=.8,
                         phase=0, stride=0, blink=False, reaction=0)
        self.palette = _PALETTES['morning']

    def frame(self, pose=None, width=480, height=180, aspect=2, camera=(0, 0), motion=1):
        canvas = Canvas(width, height, camera, cell_aspect=aspect)
        _young_brachiosaurus(canvas, self.pose if pose is None else pose,
                            self.nest, motion, self.palette)
        return canvas

    def owned(self, canvas, owner='brachiosaurus:young'):
        return {(x, y) for y, row in enumerate(canvas.owners)
                for x, value in enumerate(row) if value == owner}

    def nest_frame(self, pose=None, nest=None, width=480, height=180):
        canvas = Canvas(width, height)
        _nest(canvas, self.nest if nest is None else nest, self.palette, pose)
        return canvas

    def test_nest_owner_matches_only_the_actual_opaque_clutch_bowl_and_rim(self):
        for rim_only in (False, True):
            canvas = Canvas(480, 180, camera=(4, 2))
            _nest(canvas, self.nest, self.palette, rim_only=rim_only)
            footprint = {(x, y) for y, row in enumerate(canvas.colors)
                         for x, color in enumerate(row) if color is not None}
            self.assertTrue(footprint)
            self.assertEqual(self.owned(canvas, 'nest'), footprint)
            left, top = map(min, zip(*footprint))
            right, bottom = map(max, zip(*footprint))
            rectangle = {(x, y) for y in range(top, bottom+1)
                         for x in range(left, right+1)}
            self.assertTrue(rectangle-footprint)
            if not rim_only:
                self.assertTrue(any(canvas.chars[y][x] == ' ' for x, y in footprint))
                self.assertTrue(any(canvas.colors[y][x] == self.palette['egg']
                                    for x, y in footprint))
                self.assertTrue(any(canvas.colors[y][x] == self.palette['nest']
                                    for x, y in footprint))

    def test_rigid_parts_and_fixed_length_four_leg_gait_at_intermediate_poses(self):
        travel = {}
        for motion in (1, .18):
            heads = []
            for reaction in (0, .25, .5, .75, 1):
                for phase in (0, .4, 1.3, 2.7, 4.2, 5.8):
                    pose = dict(self.pose, phase=phase, stride=1, reaction=reaction)
                    joints = _young_brachiosaurus_pose(pose, motion)
                    for part, a, b in (('body', (-1, -2), (1, -2)),
                                       ('head', (1, -5), (2, -5)),
                                       ('tail', (-4, -2), (-2, -2))):
                        self.assertAlmostEqual(math.dist(joints[part](*a), joints[part](*b)),
                                               math.dist(a, b), places=9)
                    self.assertEqual(len(joints['legs']), 4)
                    for leg in joints['legs']:
                        self.assertAlmostEqual(math.dist(leg['hip'], leg['knee']), leg['lengths'][0])
                        self.assertAlmostEqual(math.dist(leg['knee'], leg['foot']), leg['lengths'][1])
                        self.assertLessEqual(leg['foot'][1], pose['foot_y'])
                        self.assertGreaterEqual(leg['foot'][1], pose['foot_y']-.17)
                    self.assertTrue(any(abs(leg['foot'][1]-pose['foot_y']) < 1e-9
                                        for leg in joints['legs']))
                heads.append(_young_brachiosaurus_pose(dict(self.pose, reaction=reaction), motion)['head'](2, -5))
            travel[motion] = math.dist(heads[0], heads[-1])
        self.assertGreater(travel[1], .05)
        self.assertLess(travel[.18], travel[1]/3)

    def test_all_authored_strokes_fit_shared_extents_during_gait_and_clicks(self):
        left, top, right, bottom = YOUNG_EXTENTS
        for motion in (1, .18):
            for reaction in (0, .3, .7, 1):
                for phase in (0, .5, 1.5, 2.5, 3.5, 4.5, 5.5):
                    pose = dict(self.pose, phase=phase, reaction=reaction, stride=1)
                    canvas = StrokeCanvas(240, 90)
                    _young_brachiosaurus(canvas, pose, self.nest, motion, self.palette)
                    self.assertTrue(canvas.points)
                    for x, y in canvas.points:
                        self.assertGreaterEqual(x-pose['x'], left)
                        self.assertLessEqual(x-pose['x'], right)
                        self.assertGreaterEqual(y-pose['foot_y'], top)
                        self.assertLessEqual(y-pose['foot_y'], bottom)

    def test_small_high_shouldered_long_necked_quadruped_has_an_actual_raster(self):
        canvas = self.frame()
        cells = self.owned(canvas)
        self.assertGreater(len(cells), 50)
        def span(world_y):
            row = round(canvas.project(self.pose['x'], world_y)[1])
            columns = [x for x, y in cells if y == row]
            return max(columns)-min(columns)+1 if columns else 0
        neck = span(self.pose['foot_y']-4)
        torso = span(self.pose['foot_y']-2)
        self.assertGreater(neck, 0)
        self.assertGreater(torso, neck*2)
        joints = _young_brachiosaurus_pose(self.pose, 1)
        feet = sorted(leg['foot'] for leg in joints['legs'])
        self.assertEqual(len(set(feet)), 4)
        for x, y in feet:
            px, py = canvas.project(x, y)
            self.assertTrue(any(abs(cx-px) <= 1 and abs(cy-py) <= 1 for cx, cy in cells))
        back = [leg['hip'][1] for leg in joints['legs'] if leg['hip'][0] < self.pose['x']]
        front = [leg['hip'][1] for leg in joints['legs'] if leg['hip'][0] > self.pose['x']]
        self.assertLess(max(front), min(back))
        self.assertGreater(self.pose['foot_y']-canvas.unproject(0, min(y for x, y in cells))[1], 5)
        self.assertLess(canvas.unproject(min(x for x, y in cells), 0)[0], self.pose['x']-3.5)

    def test_click_articulates_head_and_tail_but_never_inflates_torso(self):
        frames = [self.frame(dict(self.pose, reaction=value)) for value in (0, .5, 1)]
        crop = []
        for frame in frames:
            x0, y0 = map(round, frame.project(self.pose['x']-.7, self.pose['foot_y']-2.7))
            x1, y1 = map(round, frame.project(self.pose['x']+.4, self.pose['foot_y']-1.7))
            crop.append([(frame.chars[y][x], frame.colors[y][x], frame.owners[y][x])
                         for y in range(y0, y1+1) for x in range(x0, x1+1)])
        self.assertEqual(crop[0], crop[1])
        self.assertEqual(crop[0], crop[2])
        self.assertNotEqual(frames[0].chars, frames[-1].chars)

    def test_emergence_is_full_size_translation_clipped_at_the_nest_surface(self):
        counts = []
        for motion in (1, .18):
            motion_counts = []
            for emerge in (0, .2, .5, .8, 1):
                pose = dict(self.pose, state='hatching', emerge=emerge,
                            foot_y=self.nest.y+(1-emerge)*YOUNG_HEIGHT)
                joints = _young_brachiosaurus_pose(pose, motion)
                reference = _young_brachiosaurus_pose(self.pose, motion)
                for point in ((0, -2), (1, -4), (-3, -2)):
                    a, b = joints['body'](*point), reference['body'](*point)
                    self.assertAlmostEqual(a[0], b[0])
                    self.assertAlmostEqual(a[1]-b[1], (1-emerge)*YOUNG_HEIGHT)
                frame = self.frame(pose, motion=motion)
                cells = self.owned(frame)
                frame.depth = pose['depth']
                self.assertTrue(all(y <= math.floor(frame.project(self.nest.x, self.nest.y)[1])
                                    for x, y in cells))
                motion_counts.append(len(cells))
            self.assertEqual(motion_counts[0], 0)
            self.assertEqual(motion_counts, sorted(motion_counts))
            self.assertGreater(motion_counts[-1], motion_counts[2])
            counts.append(motion_counts)
        self.assertEqual(counts[0], counts[1])
        self.assertEqual(self.frame(dict(self.pose, state='hatching')).chars, self.frame().chars)

    def test_front_rim_reclaims_its_opaque_pixels_over_the_emerging_baby(self):
        pose = dict(self.pose, state='hatching', emerge=.8, x=self.pose['egg_x'],
                    foot_y=self.nest.y+.2*YOUNG_HEIGHT)
        canvas = self.nest_frame(pose)
        _young_brachiosaurus(canvas, pose, self.nest, 1, self.palette)
        before = self.owned(canvas)
        rim = Canvas(480, 180)
        _nest(rim, self.nest, self.palette, pose, rim_only=True)
        overlap = before & self.owned(rim, 'nest')
        self.assertTrue(overlap)
        _nest(canvas, self.nest, self.palette, pose, rim_only=True)
        self.assertFalse(overlap & self.owned(canvas))
        self.assertTrue(overlap <= self.owned(canvas, 'nest'))

    def test_young_and_egg_dimensions_scale_with_terminal_cells_not_fixed_glyphs(self):
        small = self.frame(width=240, height=90)
        large = self.frame(width=480, height=180)
        for index in (2, 3):
            self.assertAlmostEqual(large.bounds(self.pose['id'])[index],
                                   2*small.bounds(self.pose['id'])[index], delta=2)
        eggs = []
        for width, height in ((240, 90), (480, 180)):
            canvas = Canvas(width, height)
            canvas.default_owner = 'egg'
            _egg(canvas, 86, 53.2, self.palette)
            eggs.append(canvas.bounds('egg'))
        self.assertGreater(eggs[1][2], eggs[0][2])
        self.assertGreater(eggs[1][3], eggs[0][3])
        self.assertAlmostEqual(eggs[1][3], 2*eggs[0][3], delta=2)

    def test_selected_egg_zero_and_reset_endpoint_match_the_ordinary_clutch(self):
        for count in (3, 4):
            nest = Nest('nest', 86, 54, 2.5, count)
            normal = self.nest_frame(nest=nest)
            for index in range(count):
                first = dict(self.pose, state='wobbling', egg_index=index,
                             wobble=0, crack=0, emerge=0, reset=0)
                reset = dict(self.pose, state='scurrying', egg_index=index, reset=1)
                for pose in (first, reset):
                    frame = self.nest_frame(pose, nest)
                    self.assertEqual(frame.chars, normal.chars)
                    self.assertEqual(frame.colors, normal.colors)
                    self.assertFalse(self.owned(frame))

    def test_wobble_crack_open_and_reset_change_only_the_selected_egg(self):
        for count in (3, 4):
            nest = Nest('nest', 86, 54, 2.5, count)
            offsets = egg_offsets(nest)
            normal = self.nest_frame(nest=nest)
            for index in range(count):
                states = [dict(self.pose, egg_index=index, state='wobbling', emerge=0, crack=0, wobble=.3),
                          dict(self.pose, egg_index=index, state='cracking', emerge=0, crack=.6),
                          dict(self.pose, egg_index=index, state='hatching', emerge=.7),
                          dict(self.pose, egg_index=index, state='lingering', reset=.3),
                          dict(self.pose, egg_index=index, state='lingering', reset=.75)]
                for pose in states:
                    frame = self.nest_frame(pose, nest)
                    self.assertNotEqual(frame.chars, normal.chars)
                    self.assertFalse(self.owned(frame))
                    for other, dx in enumerate(offsets):
                        if other == index:
                            continue
                        egg = Canvas(480, 180)
                        egg.depth = .8
                        egg.default_owner = 'intact'
                        _egg(egg, nest.x+dx, nest.y-.8, self.palette)
                        for x, y in self.owned(egg, 'intact'):
                            self.assertEqual(frame.chars[y][x], normal.chars[y][x])
                            self.assertEqual(frame.colors[y][x], normal.colors[y][x])

    def test_reset_has_a_hidden_middle_and_continuous_boundary_rasters(self):
        def difference(a, b):
            return sum((a.chars[y][x], a.colors[y][x]) != (b.chars[y][x], b.colors[y][x])
                       for y in range(a.height) for x in range(a.width))
        for boundary in (0, .5, 1):
            a = self.nest_frame(dict(self.pose, state='lingering', reset=max(0, boundary-1e-6)))
            b = self.nest_frame(dict(self.pose, state='lingering', reset=min(1, boundary+1e-6)))
            self.assertLessEqual(difference(a, b), 2)
        cracked = self.nest_frame(dict(self.pose, state='cracking', emerge=0))
        opened = self.nest_frame(dict(self.pose, state='hatching', emerge=1e-6))
        self.assertLessEqual(difference(cracked, opened), 8)
        middle = self.nest_frame(dict(self.pose, state='lingering', reset=.5))
        whole = self.nest_frame()
        self.assertNotEqual(middle.chars, whole.chars)
        # Both fragments have actually gone below the rim, not faded to black.
        x = self.nest.x+egg_offsets(self.nest)[self.pose['egg_index']]
        middle.depth = .8
        px, py = map(round, middle.project(x, self.nest.y-.8))
        self.assertNotEqual(middle.colors[py][px], self.palette['egg'])

    def test_live_shell_reset_survives_baby_culling_but_requires_a_reserved_seat(self):
        nest = self.snapshot['layout'].nest
        index = nest.eggs - 1
        pose = dict(self.pose, egg_index=index, state='lingering', reset=.5,
                    x=500, foot_y=nest.y, depth=NEST_DEPTH)
        def scene(hatching, admitted, maximum=2):
            snapshot = dict(self.snapshot, hatching=hatching, admitted=admitted)
            config = copy.deepcopy(self.config)
            config['population']['maxVisible'] = maximum
            canvas = Canvas(480, 180)
            draw_scene(canvas, snapshot, config)
            canvas.depth = .8
            return [canvas.colors[round(y)][round(x)]
                    for dx in egg_offsets(nest)
                    for x, y in (canvas.project(nest.x+dx, nest.y-.8),)]
        resting = scene(None, ('brachiosaurus',))
        reserved = ('brachiosaurus', pose['id'])
        middle = scene(pose, reserved)
        self.assertNotEqual(middle[index], resting[index])
        for other in range(nest.eggs):
            if other != index:
                self.assertEqual(middle[other], resting[other])
        self.assertEqual(scene(dict(pose, reset=1), reserved), resting)
        self.assertEqual(scene(pose, ('brachiosaurus',)), resting)
        self.assertEqual(scene(pose, reserved, maximum=1), resting)

    def test_full_nest_rim_and_eggs_have_static_clearance_at_maximum_density(self):
        # Compare every opaque nest cell, not just a bounding-box intersection
        # or a few remaining egg-colored pixels. Include the early hatch pass,
        # the near-nest shell reset and the fully restored departing clutch.
        grids = ((80, 40, 3, None), (80, 40, 3, 0),
                 (120, 36, 2, 2), (240, 60, 1.2, 5),
                 (80, 40, 3, 29), (120, 36, 2, 32))
        maximum = {key: True if key == 'nestEnabled' else 2
                   for key in self.config['scenery']}
        for seed in (*range(12), 42, 2026, 2**53-1):
            layout = generate_layout(seed, maximum)
            event = NestHatching(layout.nest, layout.hatching_seed, layout.hatching_phase)
            event.advance(event.deadline, event.deadline)
            born = event.born
            for index, (width, height, aspect, age) in enumerate(grids):
                preset = ('morning', 'dusk')[(seed+index) % 2]
                reduced = bool((seed//2+index) % 2)
                motion = .18 if reduced else 1
                camera = ((-4, -2), (0, 0), (4, 2))[index % 3]
                if age is not None:
                    event.advance(event.elapsed_ns+age*SECOND, born+age*SECOND)
                young = None if age is None else event.current()
                config = settings({
                    'preset': preset, 'animals': self.config['animals'],
                    'population': {'maxVisible': 2, 'maxFamilies': 0},
                    'scenery': maximum, 'motion': {'reducedMotion': reduced}})
                snapshot = dict(self.snapshot, layout=layout, time=17.3*index,
                                brachiosaurus_reaction=(index % 3)/2, hatching=young,
                                admitted=('brachiosaurus', 'brachiosaurus:young'))
                palette = {name: tuple(min(255, round(v*1.45+8)) for v in rgb)
                           for name, rgb in _PALETTES[preset].items()}
                reference = StrokeCanvas(width, height, camera, aspect)
                _nest(reference, layout.nest, palette, young)
                if age is None:
                    reference.depth = .8
                    for point in reference.points:
                        x, y = map(round, reference.project(*point))
                        self.assertTrue(0 <= x < width and 0 <= y < height, point)
                footprint = {(x, y) for y, row in enumerate(reference.colors)
                             for x, color in enumerate(row) if color is not None}
                self.assertTrue(footprint)
                decorations = Canvas(width, height, camera, aspect)
                _focal_tree(decorations, snapshot['time'], motion, layout.wind_phase, palette)
                _brachiosaurus(decorations, snapshot, motion, palette)
                _foreground(decorations, snapshot['time'], motion,
                            replace(layout, nest=None), palette)
                scene = Canvas(width, height, camera, aspect)
                draw_scene(scene, snapshot, config)
                with self.subTest(seed=seed, grid=(width, height, aspect),
                                  preset=preset, reduced=reduced, age=age):
                    for x, y in footprint:
                        self.assertIsNone(decorations.colors[y][x], (x, y))
                        self.assertEqual((scene.chars[y][x], scene.colors[y][x]),
                                         (reference.chars[y][x], reference.colors[y][x]))
                        self.assertEqual(scene.owners[y][x], 'nest')

    def test_entire_browsing_group_translates_rigidly_with_shared_model_offset(self):
        for motion in (1, .18):
            for reaction in (0, .5, 1):
                snapshot = dict(self.snapshot, time=13.7, brachiosaurus_reaction=reaction)
                for paint in (
                    lambda c: _brachiosaurus(c, snapshot, motion, self.palette),
                    lambda c: _focal_tree(c, 13.7, motion, .4, self.palette),
                ):
                    shifted = StrokeCanvas(480, 180)
                    paint(shifted)
                    authored = StrokeCanvas(480, 180)
                    with patch('character_art.FOCAL_OFFSET_X', 0):
                        paint(authored)
                    self.assertEqual(len(shifted.points), len(authored.points))
                    for a, b in zip(shifted.points, authored.points):
                        self.assertAlmostEqual(a[0]-b[0], FOCAL_OFFSET_X)
                        self.assertAlmostEqual(a[1], b[1])

    def test_actual_hatch_path_remains_visible_through_linger_and_scurry(self):
        for seed in (0, 1, 17, 42, 2026, 2**53-1):
            layout = generate_layout(seed, {})
            event = NestHatching(layout.nest, layout.hatching_seed, layout.hatching_phase)
            self.assertTrue(event.start())
            previous_x = None
            for age in (11, 15, 17, 25, 29, 30, 31, 32):
                event.advance(age*SECOND, age*SECOND)
                young = event.current()
                self.assertIsNotNone(young)
                self.assertEqual(young['depth'], NEST_DEPTH)
                if previous_x is not None:
                    self.assertGreaterEqual(young['x'], previous_x)
                previous_x = young['x']
                for reduced in (False, True):
                    snapshot = dict(self.snapshot, layout=layout, time=age,
                                    hatching=young, brachiosaurus_reaction=.7,
                                    admitted=('brachiosaurus', young['id']))
                    config = copy.deepcopy(self.config)
                    config['motion']['reducedMotion'] = reduced
                    canvas = Canvas(480, 180)
                    draw_scene(canvas, snapshot, config)
                    self.assertTrue(self.owned(canvas), (seed, age, reduced))
                    self.assertAlmostEqual(young['foot_y'], layout.nest.y)

    def test_narrow_default_and_wide_frames_fit_stationary_focal_group_and_nest(self):
        for width, height, aspect in ((80, 40, 3), (120, 36, 2), (240, 60, 1.2)):
            for camera in ((-4, -2), (0, 0), (4, 2)):
                canvas = Canvas(width, height, camera, aspect)
                nest = self.snapshot['layout'].nest
                canvas.depth = .8
                for point in ((nest.x-nest.radius, nest.y-.5),
                              (nest.x+nest.radius, nest.y+.45)):
                    x, y = canvas.project(*point)
                    self.assertGreaterEqual(round(x), 0)
                    self.assertLess(round(x), width)
                    self.assertGreaterEqual(round(y), 0)
                    self.assertLess(round(y), height)
                for time in (0, 7, 19):
                    frame = StrokeCanvas(width, height, camera, aspect)
                    snapshot = dict(self.snapshot, time=time, brachiosaurus_reaction=.7)
                    _focal_tree(frame, time, 1, snapshot['layout'].wind_phase, self.palette)
                    _brachiosaurus(frame, snapshot, 1, self.palette)
                    for point in frame.points:
                        x, y = frame.project(*point)
                        self.assertGreaterEqual(round(x), 0)
                        self.assertLess(round(x), width)
                        self.assertGreaterEqual(round(y), 0)
                        self.assertLess(round(y), height)
                    self.assertEqual(_brachiosaurus_pose(snapshot, 1)['body'](69, 44),
                                     (69+FOCAL_OFFSET_X, 44))

    def test_lingering_and_scurrying_silhouettes_keep_rigid_geometry(self):
        for state in ('lingering', 'scurrying'):
            pose = dict(self.pose, state=state, x=105, stride=state == 'scurrying')
            canvas = self.frame(pose)
            self.assertTrue(self.owned(canvas))
            reference = _young_brachiosaurus_pose(self.pose, 1)
            joints = _young_brachiosaurus_pose(pose, 1)
            for part in ('body', 'head', 'tail'):
                for point in ((0, -2), (1, -4), (-3, -2)):
                    a, b = joints[part](*point), reference[part](*point)
                    self.assertAlmostEqual(a[0]-b[0], pose['x']-self.pose['x'])
                    self.assertAlmostEqual(a[1], b[1])

    def test_young_paints_in_front_of_focal_tree_and_parent_from_birth(self):
        for state in ('hatching', 'toddling', 'lingering', 'scurrying'):
            pose = dict(self.pose, state=state, x=82+FOCAL_OFFSET_X,
                        foot_y=51, emerge=1)
            snapshot = dict(self.snapshot, hatching=pose,
                            admitted=('brachiosaurus', pose['id']))
            isolated = self.frame(pose)
            focal = Canvas(480, 180)
            _focal_tree(focal, 0, 1, snapshot['layout'].wind_phase, self.palette)
            _brachiosaurus(focal, snapshot, 1, self.palette)
            overlap = {(x, y) for x, y in self.owned(isolated)
                       if focal.colors[y][x] is not None}
            self.assertTrue(overlap)
            frame = Canvas(480, 180)
            draw_scene(frame, snapshot, self.config)
            self.assertTrue(overlap <= self.owned(frame))

    def test_real_nearer_walker_occludes_young_in_the_normal_scene_pass(self):
        walker = dict(id='triceratops', x=86, scale=1, foot_y=54.5,
                      reaction=0, graze=0, nuzzle=0, juvenile=False,
                      calf_near=0, phase=0, stride=0, blink=False)
        snapshot = copy.deepcopy(self.snapshot)
        snapshot['hatching'] = dict(self.pose)
        snapshot['herbivores']['triceratops'] = walker
        snapshot['admitted'] = ('brachiosaurus', self.pose['id'], 'triceratops')
        config = copy.deepcopy(self.config)
        config['population']['maxVisible'] = 3
        baseline = Canvas(480, 180)
        draw_scene(baseline, snapshot, config)
        config['animals']['triceratopsEnabled'] = True
        frame = Canvas(480, 180)
        draw_scene(frame, snapshot, config)
        isolated = Canvas(480, 180)
        _triceratops(isolated, walker, 1, self.palette)
        overlap = self.owned(baseline) & self.owned(isolated, 'triceratops')
        self.assertTrue(overlap)
        self.assertEqual(self.owned(frame), self.owned(baseline)-self.owned(isolated, 'triceratops'))
        self.assertFalse(overlap & self.owned(frame))

    def test_scene_never_paints_unselected_or_over_cap_young(self):
        snapshot = copy.deepcopy(self.snapshot)
        snapshot['hatching'] = dict(self.pose)
        snapshot['admitted'] = ('brachiosaurus', self.pose['id'])
        canvas = Canvas(480, 180)
        self.assertIn(self.pose['id'], visible_cast_members(canvas, snapshot, self.config))
        draw_scene(canvas, snapshot, self.config)
        self.assertTrue(self.owned(canvas))
        for cap, admitted in ((1, snapshot['admitted']), (2, ('brachiosaurus',))):
            config = copy.deepcopy(self.config)
            config['population']['maxVisible'] = cap
            snapshot['admitted'] = admitted
            frame = Canvas(480, 180)
            draw_scene(frame, snapshot, config)
            self.assertFalse(self.owned(frame))
            self.assertLessEqual(len(visible_cast_members(frame, snapshot, config)), cap)
        for state in ('wobbling', 'cracking'):
            self.assertFalse(self.owned(self.frame(dict(self.pose, state=state))))

    def test_canvas_depth_clip_and_owner_are_restored_even_when_drawing_raises(self):
        for function, args in ((_young_brachiosaurus, (self.pose, self.nest, 1, self.palette)),
                               (_nest, (self.nest, self.palette, self.pose))):
            canvas = Canvas(240, 90)
            canvas.depth, canvas.clip_bottom, canvas.default_owner = .123, 80, 'sentinel'
            previous = canvas.depth, canvas.clip_bottom, canvas.default_owner
            function(canvas, *args)
            self.assertEqual((canvas.depth, canvas.clip_bottom, canvas.default_owner), previous)
            with patch.object(canvas, 'polygon', side_effect=RuntimeError('raster failure')):
                with self.assertRaises(RuntimeError):
                    function(canvas, *args)
            self.assertEqual((canvas.depth, canvas.clip_bottom, canvas.default_owner), previous)
        canvas = Canvas(240, 90)
        previous = canvas.depth, canvas.clip_bottom, canvas.default_owner
        _young_brachiosaurus(canvas, None, None, 1, self.palette)
        _nest(canvas, None, self.palette)
        self.assertEqual((canvas.depth, canvas.clip_bottom, canvas.default_owner), previous)


if __name__ == '__main__':
    unittest.main()
