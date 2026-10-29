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
from character_art import _ankylosaurus_pose, draw_scene
from population import ANKYLOSAURUS_DEPTH, ankylosaurus_pose


class AnkylosaurusBehavior(unittest.TestCase):
    def advance(self, world, seconds):
        remaining = round(seconds * 1_000_000_000)
        while remaining:
            delta = min(250_000_000, remaining)
            world.advance(delta)
            remaining -= delta

    def napping_world(self, calm=False):
        config = settings({'motion': {'reducedMotion': calm}})
        phase = World(config).layout.ankylosaurus_phase
        walk_time = 44 - phase * 24 / math.tau
        rate = config['motion']['speed'] * (.5 if calm else 1)
        return World(config, elapsed_ns=round(walk_time / rate * 1_000_000_000))

    def frame(self, world, pose=None, width=400, height=96):
        pose = world.snapshot() if pose is None else pose
        canvas = Canvas(width, height, pose['camera'])
        draw_scene(canvas, pose, world.config)
        return canvas

    def test_natural_nap_transitions_are_continuous_and_travel_stops_until_waking(self):
        for timestamp, state in ((17, 'waddling'), (18.5, 'settling'), (20, 'napping'),
                                 (23.5, 'waking'), (24.5, 'waddling')):
            self.assertEqual(ankylosaurus_pose(timestamp, 0, 32, 0, False)['state'], state)
        for boundary in (18, 19, 23, 24):
            before = ankylosaurus_pose(boundary - .001, 0, 32, 0, False)
            after = ankylosaurus_pose(boundary + .001, 0, 32, 0, False)
            self.assertLess(abs(after['sleep'] - before['sleep']), .004)
            self.assertGreaterEqual(after['x'], before['x'])
            self.assertLess(after['x'] - before['x'], .003)
        settled = [ankylosaurus_pose(t, 0, 32, 0, False) for t in (19, 21, 23)]
        self.assertEqual(settled[0]['x'], settled[2]['x'])
        self.assertEqual(settled[0]['phase'], settled[2]['phase'])
        self.assertEqual(settled[1]['sleep'], 1)
        moving = ankylosaurus_pose(25, 0, 32, 0, False)
        self.assertGreater(moving['x'], settled[2]['x'])
        self.assertEqual(moving['sleep'], 0)

    def test_click_wakes_smoothly_without_teleporting_and_next_nap_is_not_suppressed(self):
        for calm, duration in ((False, .9), (True, 1.5)):
            with self.subTest(reducedMotion=calm):
                world = self.napping_world(calm)
                before = world.snapshot()['ankylosaurus']
                self.assertEqual(before['state'], 'napping')
                self.assertTrue(world.react('ankylosaurus'))
                started = world.snapshot()['ankylosaurus']
                self.assertEqual(started['sleep'], before['sleep'])
                self.assertEqual(started['x'], before['x'])
                self.assertFalse(world.react('ankylosaurus'))
                self.advance(world, duration / 2)
                middle = world.snapshot()['ankylosaurus']
                self.assertEqual(middle['state'], 'waking')
                self.assertAlmostEqual(middle['sleep'], .5)
                self.assertEqual(middle['x'], before['x'])
                self.advance(world, duration / 2)
                alert = world.snapshot()['ankylosaurus']
                self.assertEqual(alert['state'], 'awake')
                self.assertEqual(alert['sleep'], 0)
                self.assertEqual(alert['x'], before['x'])
                self.advance(world, 1)
                self.assertEqual(world.snapshot()['ankylosaurus']['state'], 'awake')
                walk_rate = world.config['motion']['speed'] * (.5 if calm else 1)
                self.advance(world, 24 / walk_rate - duration - 1)
                next_nap = world.snapshot()['ankylosaurus']
                self.assertEqual(next_nap['state'], 'napping')
                self.assertEqual(next_nap['sleep'], 1)
                self.assertGreater(next_nap['x'], before['x'])

    def test_pause_selection_and_motion_reload_preserve_active_wake_progress(self):
        world = self.napping_world()
        world.react('ankylosaurus')
        self.advance(world, .3)
        world.paused = True
        before = world.snapshot()['ankylosaurus']
        self.advance(world, 2)
        self.assertEqual(world.snapshot()['ankylosaurus'], before)
        world.reconfigure(settings({'animals': {'ankylosaurusEnabled': False},
                                    'population': {'maxVisible': 1}}))
        self.assertFalse(world.react('ankylosaurus'))
        self.assertEqual(world.snapshot()['ankylosaurus'], before)
        frame = self.frame(world)
        self.assertFalse(any(owner == 'ankylosaurus' for row in frame.owners for owner in row))
        world.reconfigure(settings({'motion': {'reducedMotion': True}}))
        self.assertEqual(world.snapshot()['ankylosaurus'], before)
        world.paused = False
        self.advance(world, .6)
        # The ongoing wake keeps its captured normal duration on a calm reload.
        self.assertEqual(world.snapshot()['ankylosaurus']['state'], 'awake')

    def test_changing_seed_does_not_transfer_alertness_to_a_new_sleeping_animal(self):
        world = self.napping_world()
        phase = world.layout.ankylosaurus_phase
        # Construct overlapping nap windows, independent of particular seed poses.
        seed = next(seed for seed in range(256)
                    if seed != world.config['seed'] and
                    abs(World(settings({'seed': seed})).layout.ankylosaurus_phase - phase) < math.tau / 48)
        world.react('ankylosaurus')
        self.advance(world, 2.1)
        self.assertEqual(world.snapshot()['ankylosaurus']['state'], 'awake')
        config = settings({'seed': seed})
        fresh = World(config, elapsed_ns=world.elapsed_ns).snapshot()['ankylosaurus']
        self.assertEqual(fresh['state'], 'napping')
        world.reconfigure(config)
        self.assertEqual(world.snapshot()['ankylosaurus'], fresh)

    def test_front_bank_art_scales_and_keeps_feet_below_the_other_walking_lane(self):
        world = World(settings({'animals': {'triceratopsEnabled': False, 'stegosaurusEnabled': False,
                                           'pteranodonEnabled': False},
                                'scenery': {key: False if key == 'nestEnabled' else 0
                                            for key in settings()['scenery']}}))
        pose = world.snapshot()
        pose['ankylosaurus']['x'] = 95
        bounds = []
        for width, height in ((200, 48), (400, 96)):
            frame = self.frame(world, pose, width, height)
            bounds.append(frame.bounds('ankylosaurus'))
            feet = {}
            for actor, depth in (('trex', .55), ('ankylosaurus', ANKYLOSAURUS_DEPTH)):
                feet[actor] = max(frame.unproject(x, y, depth)[1]
                                  for y, row in enumerate(frame.owners) for x, owner in enumerate(row)
                                  if owner == actor)
            self.assertGreater(feet['ankylosaurus'] - feet['trex'], 2)
        self.assertAlmostEqual(bounds[1][2] / bounds[0][2], 2, delta=.15)
        self.assertAlmostEqual(bounds[1][3] / bounds[0][3], 2, delta=.2)

    def test_club_stays_rigid_and_reaction_does_not_inflate_rendered_torso(self):
        world = World(settings({'animals': {'trexEnabled': False, 'triceratopsEnabled': False,
                                           'stegosaurusEnabled': False, 'pteranodonEnabled': False}}))
        baseline = world.snapshot()
        baseline['ankylosaurus'].update(x=32, sleep=0, reaction=0, blink=False)
        active = copy.deepcopy(baseline)
        active['ankylosaurus']['reaction'] = 1
        frames = [self.frame(world, pose) for pose in (baseline, active)]
        columns = []
        for frame in frames:
            frame.depth = ANKYLOSAURUS_DEPTH
            left, _ = map(round, frame.project(28, 54))
            right, _ = map(round, frame.project(33, 54))
            columns.append([sum(row[x] == 'ankylosaurus' for row in frame.owners)
                            for x in range(left, right + 1)])
        self.assertEqual(columns[0], columns[1])
        travel = {}
        for motion in (1, .18):
            _, _, resting_tail = _ankylosaurus_pose(baseline['ankylosaurus'], motion)
            _, _, moving_tail = _ankylosaurus_pose(active['ankylosaurus'], motion)
            for tail in (resting_tail, moving_tail):
                a, b = tail(-16.3, 54.6), tail(-12.7, 54.6)
                self.assertAlmostEqual(math.dist(a, b), 3.6, places=6)
            travel[motion] = math.dist(resting_tail(-14.5, 54.6), moving_tail(-14.5, 54.6))
        self.assertGreater(travel[1], 1.5)
        self.assertLess(travel[.18], travel[1] / 2)


if __name__ == '__main__':
    unittest.main()
