import copy
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from canvas import Canvas
from character_art import (_PALETTES, _brachiosaurus, _egg,
                           _nest, _triceratops, _young_brachiosaurus, _young_brachiosaurus_pose,
                           draw_scene, visible_cast_members)
from configuration import settings
from engine import World
from hatching import YOUNG_EXTENTS, YOUNG_HEIGHT, egg_offsets
from layout import Nest


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
                reset = dict(self.pose, state='settling', egg_index=index, reset=1)
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
                          dict(self.pose, egg_index=index, state='settling', reset=.3),
                          dict(self.pose, egg_index=index, state='settling', reset=.75)]
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
            a = self.nest_frame(dict(self.pose, state='settling', reset=max(0, boundary-1e-6)))
            b = self.nest_frame(dict(self.pose, state='settling', reset=min(1, boundary+1e-6)))
            self.assertLessEqual(difference(a, b), 2)
        cracked = self.nest_frame(dict(self.pose, state='cracking', emerge=0))
        opened = self.nest_frame(dict(self.pose, state='hatching', emerge=1e-6))
        self.assertLessEqual(difference(cracked, opened), 8)
        middle = self.nest_frame(dict(self.pose, state='settling', reset=.5))
        whole = self.nest_frame()
        self.assertNotEqual(middle.chars, whole.chars)
        # Both fragments have actually gone below the rim, not faded to black.
        x = self.nest.x+egg_offsets(self.nest)[self.pose['egg_index']]
        middle.depth = .8
        px, py = map(round, middle.project(x, self.nest.y-.8))
        self.assertNotEqual(middle.colors[py][px], self.palette['egg'])

    def test_live_nest_reset_preserves_neighbours_and_requires_a_reserved_seat(self):
        nest = self.snapshot['layout'].nest
        index = nest.eggs - 1
        pose = dict(self.pose, egg_index=index, state='settling', reset=.5,
                    x=69, foot_y=48.6, depth=.39)
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

    def test_every_young_pixel_is_covered_by_actual_parent_raster_at_path_end(self):
        grids = ((100, 40, 1.2), (160, 60, 2), (240, 80, 3),
                 (320, 100, 1.6), (400, 150, 2), (500, 200, 3))
        for width, height, aspect in grids:
            for camera in ((-4, -2), (0, 0), (4, 2)):
                for reaction in (0, .5, 1):
                    with self.subTest(grid=(width, height, aspect), camera=camera, reaction=reaction):
                        pose = dict(self.pose, state='settling', x=69, foot_y=48.6,
                                    depth=.39, reaction=reaction, phase=1.3)
                        canvas = self.frame(pose, width, height, aspect, camera)
                        young = self.owned(canvas)
                        self.assertTrue(young)
                        snapshot = dict(self.snapshot, brachiosaurus_reaction=reaction, time=17)
                        _brachiosaurus(canvas, snapshot, 1, self.palette)
                        self.assertFalse(self.owned(canvas))
                        self.assertTrue(young <= self.owned(canvas, 'brachiosaurus'))

    def test_parent_progressively_occludes_child_without_altering_ordinary_layers(self):
        before = self.frame(dict(self.pose, x=82, foot_y=51, depth=.65))
        original = self.owned(before)
        _brachiosaurus(before, self.snapshot, 1, self.palette)
        remaining = self.owned(before)
        self.assertTrue(remaining)
        self.assertLess(len(remaining), len(original))

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
