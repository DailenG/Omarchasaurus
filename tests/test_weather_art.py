import copy
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from canvas import Canvas
from character_art import _PALETTES, _weather, draw_scene, visible_cast_members
from configuration import settings
from engine import World
from layout import HORIZON_Y, WATER_DEPTH, WEATHER_DEPTH, generate_layout
from weather import ValleyWeather

SECOND = 1_000_000_000
BANDS = ('red', 'orange', 'yellow', 'green', 'blue', 'indigo', 'violet')


class WeatherArtwork(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = settings({
            'seed': 8317,
            'animals': {name: False for name in settings()['animals']},
            'population': {'maxVisible': 1, 'maxFamilies': 0, 'randomVisitors': False},
            'scenery': {name: False if name == 'nestEnabled' else 0
                        for name in settings()['scenery']},
        })
        cls.layout = generate_layout(cls.config['seed'], cls.config['scenery'])

    def pose(self, age, calm=False):
        weather = ValleyWeather(self.layout.rain_drops, self.layout.weather_seed)
        birth = weather.deadline
        weather.advance(birth, birth, calm=calm)
        weather.advance(birth + round(age*SECOND), birth + round(age*SECOND), calm=calm)
        return weather.current()

    @staticmethod
    def colored(canvas, colors):
        if isinstance(colors, tuple) and len(colors) == 3 and isinstance(colors[0], int):
            colors = {colors}
        return {(x, y) for y, row in enumerate(canvas.colors)
                for x, color in enumerate(row) if color in colors}

    @staticmethod
    def owned(canvas, owner):
        return {(x, y) for y, row in enumerate(canvas.owners)
                for x, value in enumerate(row) if value == owner}

    @staticmethod
    def extent(cells, coordinate):
        return max(p[coordinate] for p in cells)-min(p[coordinate] for p in cells) if cells else 0

    @staticmethod
    def raster(canvas):
        return canvas.chars, canvas.colors, canvas.owners

    def frame(self, pose, width=480, height=180, aspect=2, camera=(0, 0), preset='morning'):
        canvas = Canvas(width, height, camera, cell_aspect=aspect)
        _weather(canvas, pose, _PALETTES[preset])
        return canvas

    def scene(self, snapshot, width=480, height=120, aspect=2, camera=(0, 0), config=None):
        canvas = Canvas(width, height, camera, cell_aspect=aspect)
        draw_scene(canvas, snapshot, self.config if config is None else config)
        return canvas

    def test_shower_is_a_low_open_cloud_and_many_sparse_short_rain_strokes(self):
        for preset in ('morning', 'dusk'):
            palette = _PALETTES[preset]
            for calm, age in ((False, 14), (True, 20)):
                canvas = self.frame(self.pose(age, calm), preset=preset)
                cloud = self.colored(canvas, {palette['cloud'], palette['cloud_light']})
                rain = self.colored(canvas, palette['rain'])
                self.assertGreater(len(cloud), 40)
                self.assertGreater(len(rain), 15)
                self.assertLess(len(rain), (16 if calm else 48)*7)
                world_width = self.extent(cloud, 0)/(canvas.aspect*canvas.scale)
                world_height = self.extent(cloud, 1)/canvas.scale
                self.assertGreater(world_width/world_height, 4)
                # Visible cloud ink is an outline, not a rectangular storm fill.
                area = (self.extent(cloud, 0)+1)*(self.extent(cloud, 1)+1)
                self.assertLess(len(cloud), area*.55)
                self.assertTrue(all(canvas.chars[y][x] in '_|/\\' for x, y in cloud | rain))
                self.assertGreater(max(y for x, y in rain), max(y for x, y in cloud)+10)
                self.assertTrue(all(canvas.owners[y][x] == 'sky' for x, y in cloud | rain))
                self.assertFalse(self.colored(canvas, {palette['rainbow_'+name] for name in BANDS}))

    def test_rainbow_resolves_seven_ordered_arched_colour_bands_in_both_palettes(self):
        for preset in ('morning', 'dusk'):
            canvas = self.frame(self.pose(44), preset=preset)
            palette = _PALETTES[preset]
            bands = [self.colored(canvas, palette['rainbow_'+name]) for name in BANDS]
            self.assertTrue(all(len(cells) > 50 for cells in bands))
            apex_rows = [min(y for x, y in cells) for cells in bands]
            self.assertTrue(all(a < b for a, b in zip(apex_rows, apex_rows[1:])))
            for cells in bands:
                left, right = min(x for x, y in cells), max(x for x, y in cells)
                middle = (left+right)/2
                edges = [y for x, y in cells if x < left+(right-left)*.15 or x > right-(right-left)*.15]
                apex = [y for x, y in cells if abs(x-middle) < (right-left)*.1]
                self.assertGreater(min(edges), min(apex)+15)
            ink = set().union(*bands)
            self.assertLess(len(ink), canvas.width*canvas.height*.08)
            self.assertTrue(all(canvas.chars[y][x] in '_|/\\' for x, y in ink))
            self.assertFalse(self.colored(canvas, palette['rain']))

    def test_cloud_and_rainbow_join_empty_frames_and_reveal_without_full_overlay_flash(self):
        for calm in (False, True):
            arrival, clear, end, reveal, retract = (6, 42, 90, 8, 12) if calm else (4, 30, 66, 4, 8)
            empty = self.frame(None)
            for age in (0, 1e-6, clear, clear+1e-6, end-1e-6, end):
                self.assertEqual(self.raster(self.frame(self.pose(age, calm))), self.raster(empty))
            clouds = [self.frame(self.pose(arrival*fraction, calm)) for fraction in (.1, .4, .7, 1)]
            cloud_colors = {_PALETTES['morning']['cloud'], _PALETTES['morning']['cloud_light']}
            widths = [self.extent(self.colored(frame, cloud_colors), 0) for frame in clouds]
            self.assertEqual(widths, sorted(widths))
            self.assertGreater(widths[-1], widths[0]+20)
            red = _PALETTES['morning']['rainbow_red']
            opening = [self.frame(self.pose(clear+reveal*fraction, calm)) for fraction in (.05, .25, .5, 1)]
            closing = [self.frame(self.pose(end-retract*fraction, calm)) for fraction in (1, .5, .25, .05)]
            for frames, reverse in ((opening, False), (closing, True)):
                spans = [self.extent(self.colored(frame, red), 0) for frame in frames]
                self.assertEqual(spans, sorted(spans, reverse=reverse))
                self.assertGreater(max(spans), 5*min(spans))
                # Reveal changes angular coverage, never translates the apex.
                tops = [min(y for x, y in self.colored(frame, red)) for frame in frames]
                self.assertLessEqual(max(tops)-min(tops), 1)
            self.assertEqual(self.raster(opening[-1]), self.raster(closing[0]))

    def test_projection_is_proportional_and_cell_aspect_aware(self):
        pose = self.pose(44)
        color = _PALETTES['morning']['rainbow_red']
        world_sizes = []
        for aspect in (1.2, 2, 3):
            small = self.frame(pose, width=240, height=40, aspect=aspect)
            large = self.frame(pose, width=480, height=80, aspect=aspect)
            a, b = self.colored(small, color), self.colored(large, color)
            for coordinate in (0, 1):
                self.assertAlmostEqual(self.extent(b, coordinate), 2*self.extent(a, coordinate), delta=2)
            world_sizes.append((self.extent(b, 0)/(large.aspect*large.scale),
                                self.extent(b, 1)/large.scale))
        for width, height in world_sizes[1:]:
            self.assertAlmostEqual(width, world_sizes[0][0], delta=1.5)
            self.assertAlmostEqual(height, world_sizes[0][1], delta=1.5)
        base = self.frame(pose)
        camera = (17, -9)
        shifted = self.frame(pose, camera=camera)
        a, b = self.colored(base, color), self.colored(shifted, color)
        self.assertGreater(self.extent(a, 0), base.width/2)
        dx = -camera[0]*WEATHER_DEPTH*base.aspect*base.scale
        dy = -camera[1]*WEATHER_DEPTH*base.scale
        def sky_limit(canvas):
            previous = canvas.depth
            canvas.depth = 0
            original = canvas.project(0, HORIZON_Y)[1]
            canvas.depth = WATER_DEPTH
            foreground = canvas.project(0, HORIZON_Y)[1]
            canvas.depth = previous
            return math.ceil(min(original, foreground))-1
        # The left edge is clipped in both views, so its pixel centroid cannot
        # translate rigidly. Corresponding visible strokes still must.
        for source, target, frame, shift in ((a, b, shifted, (dx, dy)),
                                              (b, a, base, (-dx, -dy))):
            bottom = sky_limit(frame)
            for x, y in source:
                px, py = x+shift[0], y+shift[1]
                if 1.5 <= px < frame.width-1.5 and 1.5 <= py < bottom-1.5:
                    self.assertLessEqual(min((tx-px)**2+(ty-py)**2 for tx, ty in target),
                                         1.5**2)

    def test_arc_sampling_is_bounded_while_actual_large_raster_keeps_all_colours(self):
        canvas = Canvas(500, 200)
        counts = []
        original = canvas.path

        def path(points, color, *args, **kwargs):
            points = tuple(points)
            counts.append(len(points))
            return original(points, color, *args, **kwargs)

        with patch.object(canvas, 'path', side_effect=path):
            _weather(canvas, self.pose(44), _PALETTES['morning'])
        self.assertEqual(len(counts), len(BANDS))
        self.assertTrue(all(3 <= count <= 96 for count in counts))
        self.assertTrue(all(len(self.colored(canvas, _PALETTES['morning']['rainbow_'+name])) > 30
                            for name in BANDS))

    def test_exact_full_frame_click_ownership_at_edge_grids_and_parallax(self):
        snapshot = World(self.config).snapshot()
        cases = ((1, 1, 1.2, (0, 0)), (2, 3, 3, (12, -8)),
                 (31, 18, 2, (-35, 40)), (80, 24, 3, (9, -40)),
                 (123, 47, 1.2, (-21, 17)), (160, 55, 2, (0, 250)),
                 (241, 80, 3, (0, -250)), (499, 199, 2, (12, 12)))
        for width, height, aspect, camera in cases:
            baseline = self.scene(dict(snapshot, weather=None), width, height, aspect, camera)
            for age, calm in ((14, False), (25, False), (44, False), (20, True), (60, True)):
                with self.subTest(grid=(width, height), aspect=aspect, camera=camera, age=age):
                    current = dict(snapshot, weather=self.pose(age, calm))
                    frame = self.scene(current, width, height, aspect, camera)
                    self.assertEqual(frame.owners, baseline.owners)
                    self.assertEqual(visible_cast_members(frame, current, self.config),
                                     visible_cast_members(baseline, dict(snapshot, weather=None), self.config))

    def test_real_mountains_water_and_opaque_animal_interiors_remain_foreground(self):
        snapshot = World(self.config).snapshot()
        palette = {name: tuple(min(255, round(v*1.45+8)) for v in rgb)
                   for name, rgb in _PALETTES['morning'].items()}
        rainbow_colors = {palette['rainbow_'+name] for name in BANDS}
        for camera in ((0, 0), (0, 40)):
            bare = Canvas(480, 120, camera)
            _weather(bare, self.pose(44), palette)
            baseline = self.scene(dict(snapshot, weather=None), camera=camera)
            frame = self.scene(dict(snapshot, weather=self.pose(44)), camera=camera)
            ink = self.colored(bare, rainbow_colors)
            terrain = self.colored(baseline, {palette['mountain'], palette['snow'], palette['volcano']})
            self.assertTrue(ink & terrain)
            animal = self.owned(baseline, 'brachiosaurus')
            water = self.owned(baseline, 'water')
            self.assertTrue(animal)
            self.assertTrue(water)
            if camera == (0, 0):
                self.assertTrue(ink & animal)
                self.assertTrue(any(baseline.chars[y][x] == ' ' for x, y in ink & animal))
            else:
                semantic_horizon = (HORIZON_Y-frame.origin_y)*frame.scale
                self.assertTrue(any(y < semantic_horizon for x, y in water))
                self.assertFalse(ink & water)
            for x, y in terrain | animal | water:
                self.assertEqual((frame.chars[y][x], frame.colors[y][x], frame.owners[y][x]),
                                 (baseline.chars[y][x], baseline.colors[y][x], baseline.owners[y][x]))
            self.assertTrue(self.colored(frame, rainbow_colors))

    def test_captured_calm_cloud_is_smaller_and_live_motion_setting_does_not_restyle_it(self):
        snapshot = World(self.config).snapshot()
        colors = {tuple(min(255, round(v*1.45+8)) for v in _PALETTES['morning'][name])
                  for name in ('cloud', 'cloud_light', 'rain')}
        clouds = []
        for calm, age in ((False, 14), (True, 20)):
            pose = self.pose(age, calm)
            current = dict(snapshot, weather=pose)
            frames = []
            for reduced in (False, True):
                config = copy.deepcopy(self.config)
                config['motion']['reducedMotion'] = reduced
                frames.append(self.scene(current, config=config))
            self.assertEqual(self.colored(frames[0], colors), self.colored(frames[1], colors))
            cloud = self.colored(self.frame(pose), {_PALETTES['morning']['cloud'],
                                                  _PALETTES['morning']['cloud_light']})
            clouds.append(cloud)
        self.assertGreater(self.extent(clouds[0], 0), self.extent(clouds[1], 0))
        self.assertGreater(self.extent(clouds[0], 1), self.extent(clouds[1], 1))

    def test_clip_depth_and_owner_are_restored_even_when_painting_raises(self):
        for age, failing_method in ((14, 'bezier'), (44, 'path')):
            pose = self.pose(age)
            original_pose = copy.deepcopy(pose)
            reference = self.frame(pose)
            ink = {(x, y) for y, row in enumerate(reference.colors)
                   for x, color in enumerate(row) if color is not None}
            cut = (min(y for x, y in ink)+max(y for x, y in ink))//2
            canvas = Canvas(480, 180)
            canvas.depth, canvas.clip_bottom, canvas.default_owner = .73, cut, 'next-layer'
            previous = canvas.depth, canvas.clip_bottom, canvas.default_owner
            original_owners = copy.deepcopy(canvas.owners)
            _weather(canvas, pose, _PALETTES['morning'])
            clipped = {(x, y) for y, row in enumerate(canvas.colors)
                       for x, color in enumerate(row) if color is not None}
            self.assertEqual(clipped, {(x, y) for x, y in ink if y <= cut})
            self.assertLess(len(clipped), len(ink))
            self.assertEqual(canvas.owners, original_owners)
            self.assertEqual((canvas.depth, canvas.clip_bottom, canvas.default_owner), previous)
            self.assertEqual(pose, original_pose)
            with patch.object(canvas, failing_method, side_effect=RuntimeError('paint interrupted')):
                with self.assertRaisesRegex(RuntimeError, 'paint interrupted'):
                    _weather(canvas, pose, _PALETTES['morning'])
            self.assertEqual((canvas.depth, canvas.clip_bottom, canvas.default_owner), previous)
            # Following artwork still inherits the caller's owner and clipping.
            canvas.put(0, cut, '#', (1, 2, 3))
            canvas.put(0, cut+1, '#', (1, 2, 3))
            self.assertEqual(canvas.owners[cut][0], 'next-layer')
            self.assertNotEqual(canvas.chars[cut+1][0], '#')


if __name__ == '__main__':
    unittest.main()
