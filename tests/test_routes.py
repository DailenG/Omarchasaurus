from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from configuration import settings
from canvas import Canvas
from engine import World
from character_art import draw_scene
from routes import Routes
from pteranodon import flight_radius, pteranodon_bounds


class ReturnRoutes(unittest.TestCase):
    def descriptor(self, span=134, start=20):
        return dict(key='animal', start_x=start, rear=-5, nose=5, depth=.5,
                    minimum_span=span)

    def test_wraps_only_after_the_whole_animal_has_cleared_the_view(self):
        for bounds in ((0, 100), (-200, 500)):
            route = Routes([self.descriptor()], {'animal': 0}, bounds)
            previous = route.position('animal')
            wrapped = False
            for distance in range(1, 1800):
                route.advance({'animal': distance})
                x = route.position('animal')
                if x < previous:
                    wrapped = True
                    self.assertGreater(previous - 5, bounds[1] + 3.5 * .5 - 1)
                    self.assertLess(x + 5, bounds[0] - 3.5 * .5 + 1)
                else:
                    self.assertAlmostEqual(x - previous, 1)
                previous = x
            self.assertTrue(wrapped)

    def test_resize_preserves_position_and_shrinking_does_not_backdate_reentry(self):
        route = Routes([self.descriptor(start=500)], {'animal': 0}, (0, 600))
        old = route.position('animal')
        route.set_viewport((0, 100), {'animal': 0})
        self.assertEqual(route.position('animal'), old)
        route.advance({'animal': .1})
        self.assertLess(route.position('animal') + 5, 0)
        before = route.position('animal')
        route.set_viewport((-100, 800), {'animal': .1})
        self.assertEqual(route.position('animal'), before)
        route.advance({'animal': .2})
        self.assertAlmostEqual(route.position('animal') - before, .1)

    def test_different_cohort_widths_keep_their_gap_over_many_wide_view_laps(self):
        a = dict(self.descriptor(span=600, start=50), key='family-a', rear=-80, nose=16, depth=.32, lane='ground')
        b = dict(self.descriptor(span=600, start=250), key='family-b', rear=-20, nose=16, depth=.32, lane='ground')
        route = Routes([a, b], {'family-a': 0, 'family-b': 0}, (0, 1000))
        route.advance({'family-a': 15000, 'family-b': 15000})
        bounds = sorted((route.position(item['key']) + item['rear'],
                         route.position(item['key']) + item['nose']) for item in (a, b))
        self.assertGreaterEqual(bounds[1][0] - bounds[0][1], 3)

    def test_shrinking_a_shared_route_does_not_collapse_two_offscreen_families(self):
        a = dict(self.descriptor(span=600, start=50), key='family-a', rear=-80, nose=16, depth=.32, lane='ground')
        b = dict(self.descriptor(span=600, start=250), key='family-b', rear=-20, nose=16, depth=.32, lane='ground')
        route = Routes([a, b], {'family-a': 0, 'family-b': 0}, (0, 1000))
        route.advance({'family-a': 500, 'family-b': 500})
        before = tuple(route.position(item['key']) for item in (a, b))
        route.set_viewport((0, 100), {'family-a': 500, 'family-b': 500})
        self.assertEqual(tuple(route.position(item['key']) for item in (a, b)), before)
        for distance in range(501, 1600):
            route.advance({'family-a': distance, 'family-b': distance})
            bounds = [(route.position(item['key']) + item['rear'],
                       route.position(item['key']) + item['nose']) for item in (a, b)]
            if all(left <= 100 and right >= 0 for left, right in bounds):
                bounds.sort()
                self.assertGreaterEqual(bounds[1][0] - bounds[0][1], 3)

    def test_constant_view_replay_matches_fine_and_coarse_advances(self):
        for distance in (0, 1234, 10000):
            direct = Routes([self.descriptor()], {'animal': distance}, (0, 100))
            stepped = Routes([self.descriptor()], {'animal': 0}, (0, 100))
            for value in range(0, distance + 1, 17):
                stepped.advance({'animal': value})
            stepped.advance({'animal': distance})
            self.assertEqual(stepped.position('animal'), direct.position('animal'))

    def test_previously_visible_pteranodon_wrap_now_remains_continuous_in_actual_raster(self):
        config = settings({'animals': {key: key == 'pteranodonEnabled' for key in settings()['animals']},
                           'population': {'maxVisible': 4}, 'motion': {'speed': 1, 'parallaxStrength': 0}})
        bird = World(config).layout.pteranodons[0]
        old_boundary = (124 - bird.start_x) / bird.speed
        frames = []
        positions = []
        for time in (old_boundary - .02, old_boundary + .02):
            world = World(config, elapsed_ns=round(time * 1e9))
            canvas = Canvas(320, 48)
            world.set_viewport(canvas.world_bounds)
            snapshot = world.snapshot()
            draw_scene(canvas, snapshot, config)
            frames.append(canvas.bounds(bird.id))
            positions.append(next(pose['x'] for pose in snapshot['pteranodons'] if pose['id'] == bird.id))
        self.assertGreater(positions[1], positions[0])
        self.assertLess(positions[1] - positions[0], .1)
        self.assertIsNotNone(frames[0])
        self.assertIsNotNone(frames[1])
        self.assertLess(abs(frames[1][0] - frames[0][0]), 2)

    def test_ordinary_flight_routes_use_full_rotation_radius_at_both_edges(self):
        world = World(settings({'population': {'maxVisible': 128},
                                'motion': {'speed': 1}}))
        world.set_viewport((-100, 0, 500, 60))
        for bird in world.layout.pteranodons:
            record = world._routes._records[bird.id]
            descriptor = record['descriptor']
            radius = flight_radius(bird.span)
            self.assertEqual(descriptor['rear'], -radius)
            self.assertEqual(descriptor['nose'], radius)
            x = record['entry'] + record['span'] - .01
            # Choose the route's accumulated distance just before its next wrap.
            distance = x - world._routes.origin(bird.id)
            distances = world._route_distances()
            distances[bird.id] = distance
            world._routes.advance(distances)
            before = world._routes.position(bird.id)
            distances[bird.id] += .02
            world._routes.advance(distances)
            after = world._routes.position(bird.id)
            pose = next(pose for pose in world.snapshot()['pteranodons']
                        if pose['id'] == bird.id)
            pose.update(x=before, bank=.28)
            self.assertGreater(pteranodon_bounds(pose)[0], 500 + 3.5 * bird.depth)
            pose.update(x=after, bank=-.28)
            self.assertLess(pteranodon_bounds(pose)[2], -100 - 3.5 * bird.depth)

    def test_very_wide_ground_routes_do_not_wrap_inside_the_viewport(self):
        config = settings({'population': {'maxVisible': 128}, 'motion': {'speed': 1, 'parallaxStrength': 0}})
        world = World(config)
        canvas = Canvas(500, 24, cell_aspect=1.2)
        world.set_viewport(canvas.world_bounds)
        left, right = world._visitor_bounds
        previous = world.snapshot()
        for _ in range(4000):
            world.advance(250_000_000)
            current = world.snapshot()
            for key, rear, nose in (('trex', -18, 23), ('triceratops', -35, 15)):
                before = previous['trex_x'] if key == 'trex' else previous['herbivores'][key]['x']
                after = current['trex_x'] if key == 'trex' else current['herbivores'][key]['x']
                if after < before - 100:
                    self.assertGreater(before + rear, right - 1)
                    self.assertLess(after + nose, left + 1)
            previous = current


if __name__ == '__main__':
    unittest.main()
