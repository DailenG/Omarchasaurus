import copy
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from configuration import settings
from engine import World
from tyrannosaurus import tyrannosaurus_pose


class TyrannosaurusBehavior(unittest.TestCase):
    def pose(self, time, reduced=False):
        return tyrannosaurus_pose(time, time, 0, 30, 0, .7, reduced)

    def test_stops_alternate_look_silent_roar_and_sit_without_moving_the_feet_lane(self):
        for begin, state, field in ((18, 'looking', 'trex_look'),
                                    (42, 'roaring', 'trex_roar'),
                                    (66, 'sitting', 'trex_sit')):
            samples = [self.pose(begin + age) for age in (0, 1.5, 3, 4.5, 6)]
            for pose in samples[:-1]:
                self.assertEqual(pose['trex_state'], state)
                self.assertEqual(pose['trex_stride'], 0)
                self.assertEqual(pose['trex_x'], samples[0]['trex_x'])
            self.assertEqual(samples[-1]['trex_state'], 'walking')
            self.assertTrue(any(abs(pose[field]) > .01 for pose in samples[1:-1]))
            self.assertEqual(samples[0][field], 0)
            self.assertAlmostEqual(samples[-1][field], 0)
            self.assertGreater(self.pose(begin + 7)['trex_x'], samples[-1]['trex_x'])

    def test_transition_overshoot_and_walk_action_boundaries_are_continuous(self):
        for boundary in (0, 1, 17, 18, 19, 22, 23, 24, 42, 43, 46, 48, 66, 67.5, 70.5, 72):
            before, after = self.pose(boundary - .0001), self.pose(boundary + .0001)
            for field in ('trex_x', 'trex_stride', 'trex_look', 'trex_roar', 'trex_sit'):
                self.assertLess(abs(after[field] - before[field]), .001, (boundary, field))
        self.assertTrue(0 < self.pose(66.75)['trex_sit'] < 1)
        self.assertAlmostEqual(self.pose(66.75)['trex_sit'], self.pose(71.25)['trex_sit'])
        self.assertEqual(self.pose(69)['trex_sit'], 1)
        self.assertEqual(self.pose(45)['trex_roar'], 1)

    def test_reduced_motion_substitutes_a_calm_look_but_retains_functional_sitting(self):
        ordinary, calm = self.pose(45), self.pose(45, reduced=True)
        self.assertGreater(ordinary['trex_roar'], .9)
        self.assertEqual(calm['trex_roar'], 0)
        self.assertNotEqual(calm['trex_look'], 0)
        self.assertEqual(calm['trex_state'], 'looking')
        for time in (45, 69):
            ordinary, calm = self.pose(time), self.pose(time, reduced=True)
            self.assertEqual(calm['trex_x'], ordinary['trex_x'])
            self.assertEqual(calm['phase'], ordinary['phase'])
            self.assertEqual(calm['trex_sit'], ordinary['trex_sit'])

    def test_live_world_frame_rates_pause_and_speed_reload_preserve_action_history(self):
        config = settings({'animals': {key: key == 'trexEnabled' for key in settings()['animals']},
                           'population': {'maxVisible': 2},
                           'motion': {'speed': 1, 'reducedMotion': False}})
        phase = World(config).layout.trex_phase
        target = round((69 - phase * 24 / math.tau) * 1e9)
        results = []
        fields = ('trex_x', 'phase', 'trex_blink', 'trex_reaction', 'trex_stride',
                  'trex_look', 'trex_roar', 'trex_sit', 'trex_state')
        for fps in (4, 15, 60):
            world = World(config)
            elapsed = 0
            while elapsed < target:
                delta = min(1_000_000_000 // fps, target - elapsed)
                world.advance(delta)
                elapsed += delta
            results.append({field: world.snapshot()[field] for field in fields})
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0], results[2])
        self.assertEqual(results[-1]['trex_state'], 'sitting')
        world.paused = True
        for _ in range(20):
            world.advance(250_000_000)
        changed = copy.deepcopy(world.config)
        changed['motion'].update(speed=.5, reducedMotion=True)
        world.reconfigure(changed)
        self.assertEqual({field: world.snapshot()[field] for field in fields}, results[-1])
        world.paused = False
        for _ in range(4):
            world.advance(250_000_000)
        self.assertEqual(world.snapshot()['trex_x'], results[-1]['trex_x'])
        self.assertEqual(world.snapshot()['trex_sit'], 1)


if __name__ == '__main__':
    unittest.main()
