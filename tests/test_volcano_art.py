import copy
import math
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from canvas import Canvas
from character_art import (_PALETTES, _brachiosaurus, _volcano_smoke,
                           draw_scene, visible_cast_members)
from configuration import settings
from engine import World


class VolcanoArtwork(unittest.TestCase):
    def setUp(self):
        self.palette = _PALETTES['morning']
        self.snapshot = dict(time=7.3, layout=SimpleNamespace(smoke_phase=2.3),
                             volcano_puff=None, smoke_lift=.7)

    @staticmethod
    def pose(progress, calm=False):
        return dict(generation=3, progress=progress,
                    strength=math.sin(math.pi*progress)**2, calm=calm)

    @staticmethod
    def added_rise(progress, calm=False):
        total = .8 if calm else 2.4
        return total*(progress-math.sin(2*math.pi*progress)/(2*math.pi))

    def frame(self, pose=None, *, lift=.7, width=480, height=180, aspect=2,
              camera=(0, 0), preset='morning'):
        snapshot = dict(self.snapshot, volcano_puff=pose, smoke_lift=lift)
        canvas = Canvas(width, height, camera, cell_aspect=aspect)
        _volcano_smoke(canvas, snapshot, _PALETTES[preset])
        return canvas

    @staticmethod
    def colored(canvas, color):
        return {(x, y) for y, row in enumerate(canvas.colors)
                for x, value in enumerate(row) if value == color}

    @staticmethod
    def owned(canvas, owner):
        return {(x, y) for y, row in enumerate(canvas.owners)
                for x, value in enumerate(row) if value == owner}

    def smoke(self, canvas, preset='morning'):
        return self.colored(canvas, _PALETTES[preset]['smoke'])

    @staticmethod
    def raster(canvas):
        return canvas.chars, canvas.colors, canvas.owners

    @staticmethod
    def difference(a, b):
        return sum((a.chars[y][x], a.colors[y][x], a.owners[y][x]) !=
                   (b.chars[y][x], b.colors[y][x], b.owners[y][x])
                   for y in range(a.height) for x in range(a.width))

    def bands(self, canvas):
        """Measure separate visible curls, without duplicating their geometry."""
        cells = self.smoke(canvas)
        rows = sorted({y for x, y in cells})
        groups = []
        for y in rows:
            if not groups or y > groups[-1][-1]+1:
                groups.append([])
            groups[-1].append(y)
        return [(min(x for x, y in cells if y in rows), rows[0],
                 max(x for x, y in cells if y in rows), rows[-1])
                for rows in groups]

    def test_zero_strength_and_smooth_birth_end_rasters_match_ambient_smoke(self):
        for calm in (False, True):
            for boundary in (0, 1):
                lift = .7+self.added_rise(boundary, calm)
                baseline = self.frame(lift=lift)
                endpoint = self.frame(self.pose(boundary, calm), lift=lift)
                self.assertEqual(self.raster(endpoint), self.raster(baseline))
                progress = 1e-6 if boundary == 0 else 1-1e-6
                near = self.frame(self.pose(progress, calm),
                                  lift=.7+self.added_rise(progress, calm))
                self.assertLessEqual(self.difference(near, baseline), 2)
            middle = self.frame(self.pose(.5, calm))
            self.assertGreater(self.difference(middle, self.frame()), 10)

    def test_normal_swell_is_visible_and_captured_calm_profile_is_gentler(self):
        for preset in ('morning', 'dusk'):
            baseline = self.frame(preset=preset)
            normal = self.frame(self.pose(.5), preset=preset)
            calm = self.frame(self.pose(.5, True), preset=preset)
            # The same smoke ink remains open stroke artwork, not an opaque fill
            # or a flash. Expanded volume comes from horizontal spread alone.
            for canvas in (baseline, normal, calm):
                cells = self.smoke(canvas, preset)
                self.assertEqual({color for row in canvas.colors for color in row
                                  if color is not None}, {_PALETTES[preset]['smoke']})
                self.assertTrue(all(canvas.chars[y][x] != ' ' for x, y in cells))
                self.assertEqual({y for x, y in cells},
                                 {y for x, y in self.smoke(baseline, preset)})
            if preset == 'morning':
                base_bands, normal_bands, calm_bands = map(self.bands,
                                                          (baseline, normal, calm))
                self.assertEqual(len(base_bands), len(normal_bands))
                self.assertEqual(len(base_bands), len(calm_bands))
                for base, wide, gentle in zip(base_bands, normal_bands, calm_bands):
                    base_width = base[2]-base[0]
                    normal_width = wide[2]-wide[0]
                    calm_width = gentle[2]-gentle[0]
                    self.assertAlmostEqual(normal_width/base_width, 1.9, delta=.2)
                    self.assertAlmostEqual(calm_width/base_width, 1.22, delta=.2)
                    self.assertGreater(normal_width-base_width,
                                       2*(calm_width-base_width))
                    self.assertGreater(calm_width, base_width)
                    self.assertEqual(base[1::2], wide[1::2])
                    self.assertEqual(base[1::2], gentle[1::2])
            self.assertGreater(len(self.smoke(normal, preset)),
                               len(self.smoke(calm, preset)))

    def test_volume_grows_then_returns_without_vertical_shrink(self):
        for calm in (False, True):
            frames = [self.frame(self.pose(progress, calm))
                      for progress in (0, .2, .35, .5, .65, .8, 1)]
            widths = [sum(right-left for left, top, right, bottom in self.bands(frame))
                      for frame in frames]
            self.assertEqual(widths[:4], sorted(widths[:4]))
            self.assertEqual(widths[3:], sorted(widths[3:], reverse=True))
            self.assertGreater(widths[3], widths[0])
            self.assertEqual(self.raster(frames[0]), self.raster(frames[-1]))
            self.assertTrue(all({y for x, y in self.smoke(frame)} ==
                                {y for x, y in self.smoke(frames[0])}
                                for frame in frames))

    def test_completed_buoyancy_keeps_curls_upward_instead_of_rewinding(self):
        for calm in (False, True):
            progress_values = (.9, .95, .99, 1-1e-6, 1)
            frames = [self.frame(self.pose(progress, calm),
                                 lift=.7+self.added_rise(progress, calm))
                      for progress in progress_values]
            tops = [[top for left, top, right, bottom in self.bands(frame)]
                    for frame in frames]
            for before, after in zip(tops, tops[1:]):
                self.assertEqual(len(before), len(after))
                self.assertTrue(all(b <= a for a, b in zip(before, after)))
            completed_lift = .7+self.added_rise(1, calm)
            after = self.frame(lift=completed_lift)
            self.assertEqual(self.raster(frames[-1]), self.raster(after))
            self.assertLessEqual(self.difference(frames[-2], after), 2)
            rewound = self.frame(lift=.7)
            self.assertGreater(self.difference(after, rewound), 10)
            self.assertEqual(self.raster(after),
                             self.raster(self.frame(lift=completed_lift+11)))

    def test_terminal_grid_and_cell_aspect_scale_the_visible_curls_proportionally(self):
        for calm in (False, True):
            for aspect in (1.2, 2, 3):
                small = self.frame(self.pose(.5, calm), width=240, height=60, aspect=aspect)
                large = self.frame(self.pose(.5, calm), width=480, height=120, aspect=aspect)
                a, b = self.smoke(small), self.smoke(large)
                for coordinate in (0, 1):
                    extent_a = max(p[coordinate] for p in a)-min(p[coordinate] for p in a)
                    extent_b = max(p[coordinate] for p in b)-min(p[coordinate] for p in b)
                    self.assertAlmostEqual(extent_b, 2*extent_a, delta=2)
                # Recover world-space proportions across cell shapes, rather
                # than comparing unrelated fixed pixel sizes.
                reference = self.frame(self.pose(.5, calm), width=480, height=120)
                reference_cells = self.smoke(reference)
                width = (max(x for x, y in b)-min(x for x, y in b))/(large.aspect*large.scale)
                reference_width = (max(x for x, y in reference_cells)-
                                   min(x for x, y in reference_cells))/(reference.aspect*reference.scale)
                self.assertAlmostEqual(width, reference_width,
                                       delta=1/(large.aspect*large.scale)+
                                       1/(reference.aspect*reference.scale))

    def test_smoke_preserves_scenery_click_ownership_clip_and_state_even_on_error(self):
        canvas = Canvas(480, 180, camera=(9, -3))
        canvas.depth, canvas.default_owner = .63, 'following-scenery'
        baseline = self.frame(self.pose(.5), camera=canvas.camera)
        cells = self.smoke(baseline)
        plane = (min(y for x, y in cells)+max(y for x, y in cells))//2
        canvas.clip_bottom = plane
        previous = canvas.depth, canvas.clip_bottom, canvas.default_owner
        snapshot = dict(self.snapshot, volcano_puff=self.pose(.5))
        before = copy.deepcopy(snapshot)
        _volcano_smoke(canvas, snapshot, self.palette)
        self.assertEqual(snapshot, before)
        expected = {(x, y) for x, y in cells if y <= plane}
        self.assertGreater(len(cells), len(expected))
        self.assertEqual(self.smoke(canvas), expected)
        self.assertTrue(all(canvas.owners[y][x] is None for x, y in expected))
        self.assertEqual((canvas.depth, canvas.clip_bottom, canvas.default_owner), previous)
        canvas.put(0, plane, '#', (1, 2, 3))
        canvas.put(0, plane+1, '#', (1, 2, 3))
        self.assertEqual(canvas.owners[plane][0], 'following-scenery')
        self.assertNotEqual(canvas.chars[plane+1][0], '#')
        with patch.object(canvas, 'bezier', side_effect=RuntimeError('paint interrupted')):
            with self.assertRaises(RuntimeError):
                _volcano_smoke(canvas, snapshot, self.palette)
        self.assertEqual((canvas.depth, canvas.clip_bottom, canvas.default_owner), previous)

    def test_smoke_keeps_its_existing_parallax_plane(self):
        camera = (9, -3)
        base = self.frame(self.pose(.5))
        shifted = self.frame(self.pose(.5), camera=camera)
        for coordinate, scale in ((0, base.aspect*base.scale), (1, base.scale)):
            a = sum(p[coordinate] for p in self.smoke(base))/len(self.smoke(base))
            b = sum(p[coordinate] for p in self.smoke(shifted))/len(self.smoke(shifted))
            self.assertAlmostEqual(b-a, -camera[coordinate]*.11*scale, delta=1)

    def test_live_reduced_motion_toggle_does_not_replace_the_captured_swell_profile(self):
        config = settings({
            'animals': {name: False for name in settings()['animals']},
            'population': {'maxVisible': 1, 'maxFamilies': 0, 'randomVisitors': False},
            'scenery': {name: False if name == 'nestEnabled' else 0
                        for name in settings()['scenery']},
        })
        snapshot = World(config).snapshot()
        snapshot.update(time=9.6-snapshot['layout'].smoke_phase, smoke_lift=.7)
        color = tuple(min(255, round(v*1.45+8)) for v in self.palette['smoke'])
        profiles = []
        for calm in (False, True):
            snapshot['volcano_puff'] = self.pose(.5, calm)
            cells = []
            for reduced in (False, True):
                current = copy.deepcopy(config)
                current['motion']['reducedMotion'] = reduced
                canvas = Canvas(480, 120)
                draw_scene(canvas, snapshot, current)
                cells.append(self.colored(canvas, color))
            self.assertEqual(cells[0], cells[1])
            profiles.append(cells[0])
        self.assertGreater(len(profiles[0] - profiles[1]), 5)

    def test_real_scene_silhouette_occludes_smoke_without_changing_animal_coverage(self):
        config = settings({
            'animals': {name: False for name in settings()['animals']},
            'population': {'maxVisible': 1, 'maxFamilies': 0, 'randomVisitors': False},
            'scenery': {name: False if name == 'nestEnabled' else 0
                        for name in settings()['scenery']},
        })
        snapshot = World(config).snapshot()
        snapshot.update(time=9.6-snapshot['layout'].smoke_phase,
                        volcano_puff=self.pose(.5), smoke_lift=.7)
        smoke = Canvas(480, 120)
        _volcano_smoke(smoke, snapshot, self.palette)
        animal = Canvas(480, 120)
        _brachiosaurus(animal, snapshot, 1, self.palette)
        # Align a real opaque blank inside the authored head/neck with a smoke
        # curl using camera parallax; no replacement polygon or fake blocker.
        smoke_cells = self.smoke(smoke)
        blank_animal = {(x, y) for x, y in self.owned(animal, 'brachiosaurus')
                        if animal.chars[y][x] == ' '}
        common_rows = {y for x, y in smoke_cells} & {y for x, y in blank_animal}
        self.assertTrue(common_rows)
        row = max(common_rows, key=lambda y: sum(cy == y for x, cy in blank_animal))
        sx = sorted(x for x, y in smoke_cells if y == row)[len([x for x, y in smoke_cells if y == row])//2]
        columns = sorted(x for x, y in blank_animal if y == row)
        ax = columns[len(columns)//2]
        camera = ((ax-sx)/(animal.aspect*animal.scale*(.4-.11)), 0)
        bare_smoke = Canvas(480, 120, camera)
        _volcano_smoke(bare_smoke, snapshot, self.palette)
        animal_only = Canvas(480, 120, camera)
        _brachiosaurus(animal_only, snapshot, 1, self.palette)
        covered = self.smoke(bare_smoke) & self.owned(animal_only, 'brachiosaurus')
        self.assertTrue(covered)
        self.assertTrue(any(animal_only.chars[y][x] == ' ' for x, y in covered))
        before = copy.deepcopy(snapshot)
        frames = []
        selected = []
        for pose in (None, self.pose(.5), self.pose(.5, True)):
            current = dict(snapshot, volcano_puff=pose)
            canvas = Canvas(480, 120, camera)
            selected.append(visible_cast_members(canvas, current, config))
            draw_scene(canvas, current, config)
            frames.append(canvas)
        self.assertEqual(snapshot, before)
        self.assertTrue(all(members == selected[0] for members in selected))
        owned = self.owned(frames[0], 'brachiosaurus')
        self.assertTrue(covered <= owned)
        for frame in frames[1:]:
            self.assertEqual(self.owned(frame, 'brachiosaurus'), owned)
            for x, y in owned:
                self.assertEqual((frame.chars[y][x], frame.colors[y][x], frame.owners[y][x]),
                                 (frames[0].chars[y][x], frames[0].colors[y][x],
                                  frames[0].owners[y][x]))
        scene_smoke = tuple(min(255, round(v*1.45+8)) for v in self.palette['smoke'])
        self.assertGreater(len(self.colored(frames[1], scene_smoke) -
                               self.colored(frames[0], scene_smoke)), 5)


if __name__ == '__main__':
    unittest.main()
