import copy
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from canvas import Canvas
from character_art import (_PALETTES, _pteranodon_strokes, _pteranodons,
                           draw_scene, visible_cast_members)
from configuration import settings
from engine import World
from pteranodon import pteranodon_bounds


class PteranodonArtwork(unittest.TestCase):
    def setUp(self):
        self.bird = dict(id='pteranodon:0', x=55, y=16, span=4.8,
                         tip_y=13.2, depth=.18, bank=0)
        self.config = settings({
            'animals': {name: name == 'pteranodonEnabled'
                        for name in settings()['animals']},
            'population': {'maxVisible': 8, 'maxFamilies': 0, 'randomVisitors': False},
            'motion': {'parallaxStrength': 0},
            'scenery': {name: False if name == 'nestEnabled' else 0
                        for name in settings()['scenery']},
        })

    @staticmethod
    def owned(canvas, identity):
        return {(x, y) for y, row in enumerate(canvas.owners)
                for x, owner in enumerate(row) if owner == identity}

    def frame(self, bird=None, width=480, height=120, aspect=2,
              camera=(0, 0), preset='morning'):
        bird = self.bird if bird is None else bird
        canvas = Canvas(width, height, camera, cell_aspect=aspect)
        _pteranodons(canvas, (bird,), (bird['id'],), _PALETTES[preset])
        return canvas

    def assert_owned_near(self, canvas, bird, point):
        old_depth = canvas.depth
        canvas.depth = bird['depth']
        px, py = canvas.project(*point)
        canvas.depth = old_depth
        self.assertTrue(any(abs(x-px) <= .75 and abs(y-py) <= .75
                            for x, y in self.owned(canvas, bird['id'])), point)

    def test_intermediate_banks_rigidly_rotate_every_vertex_about_one_root(self):
        for tip_offset in (-2.8, 0, 2.8):
            neutral = dict(self.bird, tip_y=self.bird['y'] + tip_offset)
            reference = [point for stroke in _pteranodon_strokes(neutral) for point in stroke]
            for bank in (-.28, -.193, -.071, .083, .217, .28):
                with self.subTest(tip_offset=tip_offset, bank=bank):
                    bird = dict(neutral, bank=bank)
                    rotated = [point for stroke in _pteranodon_strokes(bird) for point in stroke]
                    root = bird['x'], bird['y']
                    for original, actual in zip(reference, rotated):
                        dx, dy = original[0]-root[0], original[1]-root[1]
                        expected = (root[0] + dx*math.cos(bank) - dy*math.sin(bank),
                                    root[1] + dx*math.sin(bank) + dy*math.cos(bank))
                        self.assertAlmostEqual(actual[0], expected[0])
                        self.assertAlmostEqual(actual[1], expected[1])
                        self.assertAlmostEqual(math.dist(root, actual), math.dist(root, original))
                    # Cross-part distances also prohibit independently pivoted or inflated torsos.
                    for i, a in enumerate(reference):
                        for j, b in enumerate(reference):
                            self.assertAlmostEqual(math.dist(rotated[i], rotated[j]), math.dist(a, b))
                    canvas = self.frame(bird)
                    self.assertNotEqual(self.owned(canvas, bird['id']),
                                        self.owned(self.frame(neutral), bird['id']))
                    for point in rotated:
                        self.assert_owned_near(canvas, bird, point)

    def test_maximum_flap_and_bank_rasters_fit_live_root_centered_bounds(self):
        for aspect in (1.2, 2, 3):
            for size in ((96, 30), (240, 60), (480, 120)):
                for bank in (-.28, -.139, 0, .117, .28):
                    for tip_offset in (-2.8, 2.8):
                        bird = dict(self.bird, x=48, y=17, bank=bank,
                                    tip_y=17+tip_offset)
                        canvas = self.frame(bird, *size, aspect=aspect, camera=(7, -2))
                        points = self.owned(canvas, bird['id'])
                        self.assertTrue(points)
                        left, top, right, bottom, depth = pteranodon_bounds(bird)
                        radius = math.hypot(bird['span'], 2.8)
                        self.assertEqual((left, top, right, bottom, depth),
                                         (48-radius, 17-radius, 48+radius, 17+radius, bird['depth']))
                        dx = .501 / (canvas.aspect * canvas.scale)
                        dy = .501 / canvas.scale
                        for px, py in points:
                            x, y = canvas.unproject(px, py, bird['depth'])
                            self.assertGreaterEqual(x, left-dx)
                            self.assertLessEqual(x, right+dx)
                            self.assertGreaterEqual(y, top-dy)
                            self.assertLessEqual(y, bottom+dy)
                        for stroke in _pteranodon_strokes(bird):
                            for point in stroke:
                                self.assert_owned_near(canvas, bird, point)

    def test_terminal_size_and_cell_aspect_scale_strokes_not_the_bank_geometry(self):
        for preset in ('morning', 'dusk'):
            for aspect in (1.2, 2, 3):
                for bank in (-.21, .17):
                    bird = dict(self.bird, bank=bank, tip_y=18.8)
                    small = self.frame(bird, 240, 60, aspect, preset=preset)
                    large = self.frame(bird, 480, 120, aspect, preset=preset)
                    a, b = small.bounds(bird['id']), large.bounds(bird['id'])
                    self.assertIsNotNone(a)
                    self.assertIsNotNone(b)
                    for dimension in (2, 3):
                        self.assertAlmostEqual(b[dimension]-1, 2*(a[dimension]-1), delta=2)
                    for canvas in (small, large):
                        for stroke in _pteranodon_strokes(bird):
                            for point in stroke:
                                self.assert_owned_near(canvas, bird, point)

    def test_unselected_and_globally_clipped_strokes_preserve_following_canvas_state(self):
        bird = dict(self.bird, bank=.23, tip_y=18.8)
        canvas = Canvas(480, 120, camera=(9, -3))
        canvas.depth = .63
        canvas.default_owner = 'scenery'
        before = copy.deepcopy((canvas.chars, canvas.colors, canvas.owners))
        _pteranodons(canvas, (bird,), (), _PALETTES['morning'])
        self.assertEqual((canvas.chars, canvas.colors, canvas.owners), before)
        self.assertEqual(canvas.depth, .63)
        canvas.depth = bird['depth']
        plane = round(canvas.project(bird['x'], bird['y'])[1])
        canvas.depth = .63
        canvas.clip_bottom = plane
        _pteranodons(canvas, (bird,), (bird['id'],), _PALETTES['morning'])
        unclipped = self.frame(bird, camera=(9, -3))
        expected = {(x, y) for x, y in self.owned(unclipped, bird['id']) if y <= plane}
        self.assertTrue(expected)
        self.assertGreater(len(self.owned(unclipped, bird['id'])), len(expected))
        self.assertEqual(self.owned(canvas, bird['id']), expected)
        self.assertEqual((canvas.depth, canvas.clip_bottom, canvas.default_owner),
                         (.63, plane, 'scenery'))
        canvas.put(10, plane, '#', (1, 2, 3))
        canvas.put(10, plane+1, '#', (1, 2, 3))
        self.assertEqual(canvas.owners[plane][10], 'scenery')
        self.assertNotEqual(canvas.chars[plane+1][10], '#')
        with patch.object(canvas, 'path', side_effect=RuntimeError('paint interrupted')):
            with self.assertRaises(RuntimeError):
                _pteranodons(canvas, (bird,), (bird['id'],), _PALETTES['morning'])
        self.assertEqual((canvas.depth, canvas.clip_bottom, canvas.default_owner),
                         (.63, plane, 'scenery'))

    def flock_snapshot(self, count):
        snapshot = World(self.config).snapshot()
        offsets = ((0, 0), (-11, -4.5), (-11, 4.5), (-22, -9), (-22, 9))
        members = tuple(dict(self.bird, id=f'pteranodon:{i+3}', x=58+dx,
                             y=16+dy, tip_y=14+dy, bank=.08*(i-2))
                        for i, (dx, dy) in enumerate(offsets))
        snapshot.update(pteranodons=(), camera=(0, 0),
                        pteranodon_flock=dict(generation=17, members=members),
                        admitted=('brachiosaurus',) + tuple(bird['id'] for bird in members[:count]))
        return snapshot

    def test_real_scene_draws_only_admitted_flock_prefix_and_ordinary_individuals(self):
        for count in (2, 3, 4, 5):
            snapshot = self.flock_snapshot(count)
            ordinary = tuple(dict(self.bird, id=f'pteranodon:{i}', x=15+i*15, y=5,
                                  tip_y=3, bank=.15) for i in range(2))
            snapshot['pteranodons'] = ordinary
            snapshot['admitted'] += tuple(bird['id'] for bird in ordinary)
            before = copy.deepcopy(snapshot)
            canvas = Canvas(480, 120, snapshot['camera'])
            expected = set(snapshot['admitted'])
            self.assertEqual(set(visible_cast_members(canvas, snapshot, self.config)), expected)
            draw_scene(canvas, snapshot, self.config)
            flyers = {owner for row in canvas.owners for owner in row
                      if owner and owner.startswith('pteranodon:')}
            self.assertEqual(flyers, expected - {'brachiosaurus'})
            self.assertEqual(snapshot, before)

    def test_disabled_or_tight_global_budget_emits_no_flock_and_never_promotes_one_member(self):
        snapshot = self.flock_snapshot(5)
        for enabled, cap, expected_count in ((False, 8, 0), (True, 1, 0),
                                              (True, 2, 0), (True, 3, 2), (True, 5, 4)):
            config = copy.deepcopy(self.config)
            config['animals']['pteranodonEnabled'] = enabled
            config['population']['maxVisible'] = cap
            canvas = Canvas(480, 120, snapshot['camera'])
            selected = visible_cast_members(canvas, snapshot, config)
            expected = {bird['id'] for bird in snapshot['pteranodon_flock']['members'][:expected_count]}
            self.assertEqual(set(selected) - {'brachiosaurus'}, expected)
            draw_scene(canvas, snapshot, config)
            actual = {owner for row in canvas.owners for owner in row
                      if owner and owner.startswith('pteranodon:')}
            self.assertEqual(actual, expected)
            self.assertLessEqual(len(selected), cap)

    def test_flock_and_ordinary_wings_remain_behind_real_foreground_tree(self):
        for flocked in (False, True):
            snapshot = self.flock_snapshot(2)
            birds = tuple(dict(self.bird, id=f'pteranodon:{i+3 if flocked else i}',
                               x=94-i*11, y=18-i*4.5, tip_y=20-i*4.5, bank=.21)
                          for i in range(2))
            snapshot['pteranodons'] = () if flocked else birds
            snapshot['pteranodon_flock'] = dict(generation=18, members=birds) if flocked else None
            snapshot['admitted'] = ('brachiosaurus',) + tuple(bird['id'] for bird in birds)
            bare = Canvas(480, 120)
            _pteranodons(bare, birds, snapshot['admitted'], _PALETTES['morning'])
            scene = Canvas(480, 120)
            draw_scene(scene, snapshot, self.config)
            baseline_snapshot = copy.deepcopy(snapshot)
            baseline_snapshot.update(pteranodons=(), pteranodon_flock=None,
                                     admitted=('brachiosaurus',))
            baseline = Canvas(480, 120)
            draw_scene(baseline, baseline_snapshot, self.config)
            covered = self.owned(bare, birds[0]['id']) - self.owned(scene, birds[0]['id'])
            self.assertTrue(covered)
            self.assertTrue(self.owned(scene, birds[0]['id']))
            for x, y in covered:
                self.assertEqual((scene.chars[y][x], scene.colors[y][x], scene.owners[y][x]),
                                 (baseline.chars[y][x], baseline.colors[y][x], baseline.owners[y][x]))


if __name__ == '__main__':
    unittest.main()
