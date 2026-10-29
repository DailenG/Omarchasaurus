import copy
from dataclasses import replace
from pathlib import Path
import random
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from configuration import settings
from canvas import Canvas
from engine import World
import layout as layout_module
from layout import WATER_DEPTH, generate_layout
from character_art import visible_cast_members
from population import plesiosaurus_pose


class PlesiosaurusBehavior(unittest.TestCase):
    def advance(self, world, seconds):
        remaining = round(seconds * 1_000_000_000)
        while remaining:
            delta = min(250_000_000, remaining)
            world.advance(delta)
            remaining -= delta

    def descriptor(self):
        return replace(generate_layout(42, {}).plesiosaurus, phase=0)

    def pose(self, descriptor, walk_time, motion_time=None, reaction=0):
        return plesiosaurus_pose(descriptor, walk_time,
                                walk_time if motion_time is None else motion_time,
                                reaction, WATER_DEPTH)

    def world(self, *, elapsed=0, phase=4, limit=8, visitors=False):
        world = World(settings({'animals': {'diplodocusEnabled': False},
                                'population': {'maxVisible': limit,
                                               'randomVisitors': visitors}}),
                      elapsed_ns=round(elapsed * 1_000_000_000), visitor_seed=17)
        world.layout = replace(world.layout, plesiosaurus=replace(
            world.layout.plesiosaurus, phase=phase))
        return world

    def test_lifecycle_boundaries_translate_rigidly_without_surface_or_cycle_jumps(self):
        descriptor = self.descriptor()
        for boundary in (0, 4, 14, 18, 30, 34, 44, 48, 60):
            before = self.pose(descriptor, boundary - .0001)
            after = self.pose(descriptor, boundary + .0001)
            with self.subTest(boundary=boundary):
                for key in ('x', 'body_y', 'emergence', 'look'):
                    self.assertLess(abs(after[key] - before[key]), .001)
                # Smoothstep has zero vertical velocity at each state boundary.
                self.assertLess(abs(after['body_y'] - before['body_y']), .00001)
        for time, state, emergence in ((0, 'surfacing', 0), (2, 'surfacing', .5),
                                        (4, 'looking', 1), (13, 'looking', 1),
                                        (14, 'diving', 1), (16, 'diving', .5),
                                        (18, 'submerged', 0), (29, 'submerged', 0)):
            pose = self.pose(descriptor, time)
            self.assertEqual(pose['state'], state)
            self.assertAlmostEqual(pose['emergence'], emergence)

    def test_swimmer_stays_in_lake_and_continues_drifting_while_hidden(self):
        descriptor = self.descriptor()
        left, _, right, _ = generate_layout(42, {}).water_bounds
        previous = None
        for step in range(2401):
            time = step / 10
            pose = self.pose(descriptor, time)
            self.assertLessEqual(abs(pose['x'] - descriptor.x), 2)
            self.assertGreaterEqual(pose['x'] - 12, left)
            self.assertLessEqual(pose['x'] + 12, right)
            self.assertLessEqual(abs(pose['look']), .15)
            if previous is not None:
                self.assertLess(abs(pose['x'] - previous['x']), .04)
            previous = pose
        self.assertNotEqual(self.pose(descriptor, 19)['x'], self.pose(descriptor, 28)['x'])

    def test_admission_waits_for_head_to_clear_water_and_releases_slot_when_hidden(self):
        world = self.world(phase=0, limit=2)
        canvas = Canvas(500, 10)
        for time, expected in ((0, False), (1, False), (2, True), (4, True),
                               (14, True), (16, True), (17, False), (18, False),
                               (29, False), (30, False), (32, True)):
            snapshot = world.snapshot()
            snapshot['plesiosaurus'] = self.pose(world.layout.plesiosaurus, time)
            swimmer = snapshot['plesiosaurus']
            selected = visible_cast_members(canvas, snapshot, world.config)
            self.assertEqual('plesiosaurus' in selected, expected, time)
            self.assertEqual(swimmer['visible'], expected, time)
            self.assertLessEqual(len(selected), 2)
            if expected:
                self.assertLessEqual(swimmer['body_y'] - 14, swimmer['water_y'])
        self.assertGreater(self.pose(world.layout.plesiosaurus, 1)['emergence'], 0)
        offscreen = Canvas(320, 96, camera=(1_000_000, 0))
        self.advance(world, 4)
        self.assertNotIn('plesiosaurus', visible_cast_members(offscreen, world.snapshot(), world.config))


    def test_hide_show_resize_pause_and_live_settings_never_restart_the_dive(self):
        world = World(settings())
        start_ns = round((15 - world.layout.plesiosaurus.phase) * 1_000_000_000)
        self.advance(world, start_ns / 1_000_000_000)
        before = world.snapshot()['plesiosaurus']
        world.paused = True
        self.advance(world, 8)
        for size in ((80, 24), (500, 10), (320, 96)):
            world.set_viewport(Canvas(*size).world_bounds)
            self.assertEqual(world.snapshot()['plesiosaurus'], before)
        config = copy.deepcopy(world.config)
        config['animals']['plesiosaurusEnabled'] = False
        config['population']['maxVisible'] = 1
        config['scenery']['treeDensity'] = 0
        config['motion']['reducedMotion'] = True
        world.reconfigure(config)
        self.assertEqual(world.snapshot()['plesiosaurus'], before)
        self.assertNotIn('plesiosaurus', visible_cast_members(Canvas(500, 10), world.snapshot(), config))
        world.paused = False
        self.advance(world, 4)
        hidden = world.snapshot()['plesiosaurus']
        self.assertEqual(hidden, self.pose(world.layout.plesiosaurus,
                         (start_ns + 2_000_000_000) / 1_000_000_000,
                         (start_ns + 4_000_000_000) / 1_000_000_000))
        config['animals']['plesiosaurusEnabled'] = True
        config['population']['maxVisible'] = 8
        world.reconfigure(config)
        self.assertEqual(world.snapshot()['plesiosaurus'], hidden)
        self.assertNotIn('plesiosaurus', visible_cast_members(Canvas(500, 10), world.snapshot(), config))
        self.advance(world, 30)
        self.assertEqual(world.snapshot()['plesiosaurus'],
                         self.pose(world.layout.plesiosaurus,
                         (start_ns + 17_000_000_000) / 1_000_000_000,
                         (start_ns + 34_000_000_000) / 1_000_000_000))

    def test_click_in_random_ground_mode_uses_existing_envelope_without_retiming_or_effects(self):
        world = self.world(visitors=True)
        control = self.world(visitors=True)
        before = world.snapshot()['plesiosaurus']
        self.assertTrue(world.react('plesiosaurus'))
        self.assertFalse(world.react('plesiosaurus'))
        self.advance(world, 1)
        self.advance(control, 1)
        active = world.snapshot()['plesiosaurus']
        self.assertAlmostEqual(active['reaction'], 1)
        self.assertEqual(dict(active, reaction=0), control.snapshot()['plesiosaurus'])
        self.assertIsNone(world.water_jump)
        self.assertIsNone(world.meteor)
        self.assertEqual(world.snapshot()['visitor'], control.snapshot()['visitor'])
        self.advance(world, 1)
        self.assertEqual(world.snapshot()['plesiosaurus']['reaction'], 0)
        self.assertFalse(world.react('plesiosaurus'))
        self.advance(world, 1)
        self.assertTrue(world.react('plesiosaurus'))
        self.assertEqual(len(world.reactions), 1)
        self.assertEqual(world.layout.plesiosaurus.water_y, before['water_y'])

    def test_disabled_and_submerged_clicks_cannot_force_resurfacing(self):
        for elapsed, enabled in ((4, False), (1, True), (20, True), (29, True)):
            world = self.world(elapsed=elapsed, phase=0)
            config = copy.deepcopy(world.config)
            config['animals']['plesiosaurusEnabled'] = enabled
            world.reconfigure(config)
            before = world.snapshot()
            self.assertFalse(world.react('plesiosaurus'))
            self.assertEqual(world.snapshot(), before)
            self.assertEqual(world.reactions, {})
            self.assertIsNone(world.water_jump)
            self.assertNotIn('plesiosaurus', visible_cast_members(Canvas(500, 10), before, config))

    def test_frame_rate_and_live_reduced_motion_preserve_walk_clock_history(self):
        poses = []
        for fps in (15, 60, 144):
            world = self.world(phase=0)
            self.advance(world, 3)
            before = world.snapshot()['plesiosaurus']
            config = copy.deepcopy(world.config)
            config['motion'].update(speed=.75, reducedMotion=True)
            world.reconfigure(config)
            self.assertEqual(world.snapshot()['plesiosaurus'], before)
            for frame in range(fps * 4):
                world.advance((frame + 1) * 1_000_000_000 // fps
                              - frame * 1_000_000_000 // fps)
            poses.append(world.snapshot()['plesiosaurus'])
            self.assertEqual(poses[-1], self.pose(world.layout.plesiosaurus, 4.5, 6))
        self.assertEqual(poses[0], poses[1])
        self.assertEqual(poses[0], poses[2])

    def test_seed_namespaces_isolate_swimmer_from_scenery_ground_and_global_random(self):
        state = random.getstate()
        original_rng = layout_module._rng
        for seed in (0, 17, 42, 2**53 - 1):
            original = generate_layout(seed, {})
            changed_scenery = generate_layout(seed, {'treeDensity': 0, 'lilyPadDensity': 2})
            self.assertEqual(original.plesiosaurus, changed_scenery.plesiosaurus)
            def altered_rng(value, namespace):
                return original_rng(value + 1 if namespace.startswith('plesiosaurus') else value,
                                    namespace)
            with patch.object(layout_module, '_rng', side_effect=altered_rng):
                changed = generate_layout(seed, {})
            self.assertNotEqual(changed.plesiosaurus, original.plesiosaurus)
            self.assertEqual(replace(changed, plesiosaurus=original.plesiosaurus), original)
            swimmer = original.plesiosaurus
            left, top, right, bottom = original.water_bounds
            self.assertGreaterEqual(swimmer.x - 14, left)
            self.assertLessEqual(swimmer.x + 14, right)
            self.assertLess(top, swimmer.water_y)
            self.assertLess(swimmer.water_y, bottom)
            startup = self.pose(swimmer, 0)
            self.assertEqual(startup['state'], 'looking')
            self.assertTrue(startup['visible'])
            self.assertEqual(startup['emergence'], 1)
        self.assertEqual(random.getstate(), state)

    def test_enabling_and_diving_never_perturb_ground_encounter_sequence(self):
        enabled = self.world(visitors=True)
        disabled = self.world(visitors=True)
        config = copy.deepcopy(disabled.config)
        config['animals']['plesiosaurusEnabled'] = False
        disabled.reconfigure(config)
        for sample in range(12):
            self.assertEqual(enabled.snapshot()['visitor'], disabled.snapshot()['visitor'])
            self.assertEqual(enabled.layout, disabled.layout)
            if sample == 5:
                config['animals']['plesiosaurusEnabled'] = True
                disabled.reconfigure(config)
            self.advance(enabled, 60)
            self.advance(disabled, 60)
        self.assertGreater(enabled.snapshot()['visitor']['generation'], 0)

    def test_canvas_bottom_clip_is_inclusive_and_preserves_underlying_ownership(self):
        canvas = Canvas(20, 10)
        canvas.put(3, 5, '~', (1, 2, 3), owner='water')
        canvas.clip_bottom = 4
        canvas.put(3, 4, 'o', (4, 5, 6), owner='plesiosaurus')
        canvas.put(3, 5, ' ', (4, 5, 6), owner='plesiosaurus')
        self.assertEqual(canvas.chars[4][3], 'o')
        self.assertEqual(canvas.owners[4][3], 'plesiosaurus')
        self.assertEqual(canvas.chars[5][3], '~')
        self.assertEqual(canvas.colors[5][3], (1, 2, 3))
        self.assertEqual(canvas.owners[5][3], 'water')
        canvas.clip_bottom = None
        canvas.put(3, 5, ' ', (4, 5, 6), owner='plesiosaurus')
        self.assertEqual(canvas.owners[5][3], 'plesiosaurus')


if __name__ == '__main__':
    unittest.main()
