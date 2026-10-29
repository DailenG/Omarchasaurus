import fcntl
import json
import math
import os
import re
import select
import signal
import struct
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest
import termios
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from canvas import Canvas
from engine import World
from configuration import load_settings, settings
from dinosaurs import Input, session_alive
from character_art import _brachiosaurus_pose, _trex_pose, draw_scene
from layout import FOCAL_OFFSET_X, METEOR_DEPTH, WATER_DEPTH


class TerminalBehavior(unittest.TestCase):
    def test_fragmented_mouse_report_and_reply_are_classified(self):
        d = Input()
        self.assertEqual(d.feed(b'\x1b[<0;12', 1), [])
        self.assertEqual(d.feed(b';8M', 1.01), [('click', (11, 7))])
        self.assertEqual(d.feed(b'\x1b[?1;2c', 2), [])
        self.assertEqual(d.feed(b'q', 3), [('key', b'q')])

    def test_escape_timeout_and_buffer_limit(self):
        d = Input()
        self.assertEqual(d.feed(b'\x1b', 1), [])
        self.assertEqual(d.feed(b'', 1.1), [('key', b'\x1b')])
        self.assertEqual(d.feed(b'x'*4097, 2), [('key', b'overflow')])
        self.assertFalse(d.data)

    def test_exact_elapsed_time_determines_simulation_not_fps(self):
        for speed in (.25, .75, 1.2, 2):
            outcomes = []
            for fps in (15, 24, 60, 144):
                w = World(settings({'motion': {'speed': speed}}))
                for frame in range(fps*5):
                    start = frame*5_000_000_000//(fps*5)
                    end = (frame+1)*5_000_000_000//(fps*5)
                    w.advance(end-start)
                outcomes.append((w.tick, w.snapshot()['trex_x'], w.snapshot()['time']))
            self.assertTrue(all(value == outcomes[0] for value in outcomes))
            self.assertEqual(outcomes[0][0], 300)
            self.assertEqual(outcomes[0][2], 5*speed)


    def test_pause_stall_reduced_motion_and_individual_cooldowns(self):
        w = World(settings())
        w.advance(90_000_000_000)
        self.assertEqual(w.tick, 15)
        w.paused = True
        w.advance(90_000_000)
        self.assertEqual(w.tick, 15)
        self.assertTrue(w.react('trex'))
        self.assertFalse(w.react('trex'))
        self.assertTrue(w.react('brachiosaurus'))
        calm = World(settings({'motion': {'reducedMotion': True}}), elapsed_ns=17_000_000_000)
        self.assertEqual(calm.snapshot()['camera'], (0, 0))

    def test_sparse_settings_and_invalid_reload_do_not_mutate_scene(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'settings.json'
            path.write_text(json.dumps({'preset':'dusk','motion':{'speed':.5}}))
            previous = load_settings(path)
            self.assertEqual(previous['preset'], 'dusk')
            self.assertEqual(previous['motion']['speed'], .5)
            path.write_text('{"motion":{"speed":9}}')
            with self.assertRaises(ValueError):
                load_settings(path)
            self.assertEqual(previous['motion']['speed'], .5)
            self.assertEqual(json.loads(path.read_text()), {'motion':{'speed':9}})

    def test_actor_glyph_bounds_grow_with_terminal_not_just_population(self):
        w = World(settings(), elapsed_ns=12_000_000_000)
        p = w.snapshot()
        bounds = []
        for width, height in ((160,48),(320,96)):
            c = Canvas(width,height,p['camera'])
            draw_scene(c,p,w.config)
            bounds.append(c.bounds('brachiosaurus'))
        a,b=bounds
        self.assertIsNotNone(a)
        self.assertIsNotNone(b)
        self.assertAlmostEqual(b[2]/a[2], 2, delta=.15)
        self.assertAlmostEqual(b[3]/a[3], 2, delta=.15)

    def test_occluding_scenery_removes_click_ownership(self):
        c = Canvas(160,60)
        c.polygon([(50,40),(60,40),(60,50),(50,50)],(200,150,50),owner='trex',fill=' ')
        x,y=map(round,c.project(55,45))
        self.assertEqual(c.chars[y][x], ' ')
        self.assertEqual(c.owners[y][x], 'trex')
        c.polygon([(52,42),(58,42),(58,48),(52,48)],(80,100,80),fill='.')
        self.assertIsNone(c.owners[y][x])

    def test_session_ends_when_coordinator_releases_ownership_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = root/'preview-session'
            session.mkdir(mode=0o700)
            lock = root/'preview.lock'
            lock.touch(mode=0o600)
            with lock.open('r+') as coordinator:
                fcntl.flock(coordinator, fcntl.LOCK_EX)
                self.assertTrue(session_alive(session, True))
                fcntl.flock(coordinator, fcntl.LOCK_UN)
                self.assertFalse(session_alive(session, True))

    def test_paused_runner_stops_painting_but_invalidates_on_palette_and_terminal_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            master, slave = os.openpty()
            saved = termios.tcgetattr(slave)
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 80, 640, 384))
            process = subprocess.Popen(
                [sys.executable, str(ROOT/'scripts/dinosaurs.py'), '--preview',
                 '--config', str(Path(temporary)/'settings.json'), '--duration', '15'],
                stdin=slave, stdout=slave, stderr=subprocess.PIPE,
                start_new_session=True,
                env={key: value for key, value in os.environ.items()
                     if key not in ('COLUMNS', 'LINES')})

            def frame():
                data = b''
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    if select.select([master], [], [], max(0, deadline-time.monotonic()))[0]:
                        data += os.read(master, 65536)
                        if b'\x1b[0m' in data:
                            return data
                self.fail('scene did not repaint after invalidation')

            def idle():
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    if not select.select([master], [], [], .25)[0]:
                        self.assertIsNone(process.poll())
                        return
                    os.read(master, 65536)
                self.fail('paused scene kept writing terminal frames')

            try:
                initial = frame()
                os.write(master, b' ')
                idle()
                invalid_path = Path(temporary) / 'settings.json'
                invalid_path.write_text('{"motion":')
                os.write(master, b'r')
                # Cross the real reload poll while paused: rejection must keep
                # the last valid scene alive, not unwind the animation loop.
                deadline = time.monotonic() + 1.5
                while time.monotonic() < deadline:
                    if select.select([master], [], [], .05)[0]:
                        os.read(master, 65536)
                    self.assertIsNone(process.poll(), 'invalid live settings closed the preview')
                invalid_path.unlink()
                os.write(master, b'p')
                palette = frame()
                colors = lambda data: set(re.findall(rb'\x1b\[(?:38|48);2;(\d+;\d+;\d+)m', data))
                self.assertNotEqual(colors(initial), colors(palette))
                idle()
                fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 30, 100, 800, 480))
                resized = frame()
                self.assertIn(b'\x1b[29;1H', resized)
                idle()
                fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 30, 100, 1600, 480))
                changed_aspect = frame()
                glyphs = lambda data: re.sub(rb'\x1b\[[0-9;?]*[A-Za-z]', b'', data)
                self.assertNotEqual(glyphs(resized), glyphs(changed_aspect))
                idle()
                os.kill(process.pid, signal.SIGTSTP)
                deadline = time.monotonic() + 3
                stopped = None
                while stopped is None and time.monotonic() < deadline:
                    stopped = os.waitid(os.P_PID, process.pid, os.WSTOPPED | os.WNOHANG)
                    time.sleep(.01)
                self.assertIsNotNone(stopped, 'runner did not suspend')
                self.assertEqual(stopped.si_code, os.CLD_STOPPED)
                idle()
                os.kill(process.pid, signal.SIGCONT)
                self.assertIn(b'\x1b[29;1H', frame())
                idle()
                os.write(master, b' ')
                self.assertIn(b'\x1b[29;1H', frame())
                self.assertIn(b'\x1b[29;1H', frame())
                os.write(master, b'q')
                _, errors = process.communicate(timeout=3)
                self.assertEqual(process.returncode, 0, errors.decode())
                self.assertEqual(termios.tcgetattr(slave), saved)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
                os.close(master)
                os.close(slave)


class PreviewInteractions(unittest.TestCase):
    def scene(self, world, pose=None):
        pose = world.snapshot() if pose is None else pose
        canvas = Canvas(400, 96, pose['camera'])
        draw_scene(canvas, pose, world.config)
        return canvas

    def test_head_reactions_are_large_but_reduced_motion_stays_gentle(self):
        travel = {}
        for calm in (False, True):
            world = World(settings({'motion': {'reducedMotion': calm}}))
            world.react('brachiosaurus')
            world.react('trex')
            for _ in range(4):
                world.advance(250_000_000)
            pose = world.snapshot()
            pose.update(brachiosaurus_blink=False, trex_blink=False)
            resting = dict(pose, brachiosaurus_reaction=0, trex_reaction=0)
            frames = [self.scene(world, p) for p in (resting, pose)]
            for actor in ('brachiosaurus', 'trex'):
                eyes = []
                for frame in frames:
                    eyes.append(next((x, y) for y, row in enumerate(frame.chars)
                                     for x, ch in enumerate(row)
                                     if ch == 'o' and frame.owners[y][x] == actor))
                distance = math.hypot((eyes[1][0]-eyes[0][0])/(frames[0].aspect*frames[0].scale),
                                      (eyes[1][1]-eyes[0][1])/frames[0].scale)
                travel[actor, calm] = distance
        for actor in ('brachiosaurus', 'trex'):
            self.assertGreater(travel[actor, False], 5)
            self.assertGreater(travel[actor, True], .1)
            self.assertLess(travel[actor, True], travel[actor, False]/2)

    def test_reactions_articulate_head_jaw_and_tail_without_deforming_torso_or_neck_length(self):
        world = World(settings({'scenery': dict.fromkeys(
            ('treeDensity', 'fernDensity', 'rockDensity', 'cloudDensity'), 0)}),
            elapsed_ns=12_000_000_000)
        resting = dict(world.snapshot(), brachiosaurus_blink=False, trex_blink=False,
                       brachiosaurus_reaction=0, trex_reaction=0)

        def column_counts(canvas, actor, x_min, x_max):
            canvas.depth = .40 if actor == 'brachiosaurus' else .55
            start, _ = map(round, canvas.project(x_min, 44))
            end, _ = map(round, canvas.project(x_max, 44))
            return [sum(1 for y in range(canvas.height) if canvas.owners[y][x] == actor)
                    for x in range(start, end + 1)]

        def neck_lengths(pose):
            return [math.hypot(b[0] - a[0], b[1] - a[1])
                    for a, b in zip(pose['neck'], pose['neck'][1:])]

        base_brachio = _brachiosaurus_pose(resting, 1.0)
        base_trex = _trex_pose(resting, 1.0)
        base_b_links = neck_lengths(base_brachio)
        base_b_jaw = math.hypot(*(base_brachio['jaw'](88.7, 16.3)[i] - base_brachio['head'](89.1, 15.2)[i] for i in (0, 1)))
        base_t_jaw = math.hypot(*(base_trex['jaw'](18.0, 37.3)[i] - base_trex['head'](17.2, 36.8)[i] for i in (0, 1)))
        base_b_tail = base_brachio['tail'](44, 49)
        base_t_tail = base_trex['tail'](-16, 47)

        rest_brachio_canvas = Canvas(240, 72, resting['camera'])
        draw_scene(rest_brachio_canvas, dict(resting, trex_x=-100), world.config)
        rest_trex_canvas = Canvas(240, 72, resting['camera'])
        draw_scene(rest_trex_canvas, resting, world.config)
        tx = resting['trex_x']
        torso_left = base_brachio['body'](58, 44)[0]
        torso_right = base_brachio['body'](74, 44)[0]
        base_b_torso = column_counts(rest_brachio_canvas, 'brachiosaurus', torso_left, torso_right)
        base_t_torso = column_counts(rest_trex_canvas, 'trex', tx - 3.5, tx + 3.0)

        for reaction in (.5, 1.0):
            active = dict(resting, brachiosaurus_reaction=reaction, trex_reaction=reaction)
            b_pose = _brachiosaurus_pose(active, 1.0)
            t_pose = _trex_pose(active, 1.0)
            for a, b in zip(base_b_links, neck_lengths(b_pose)):
                self.assertAlmostEqual(a, b, places=6)
            self.assertGreater(math.hypot(*(b_pose['jaw'](88.7, 16.3)[i] - b_pose['head'](89.1, 15.2)[i] for i in (0, 1))),
                               base_b_jaw + .5)
            self.assertGreater(math.hypot(*(t_pose['jaw'](18.0, 37.3)[i] - t_pose['head'](17.2, 36.8)[i] for i in (0, 1))),
                               base_t_jaw + .5)
            self.assertGreater(math.hypot(*(b_pose['tail'](44, 49)[i] - base_b_tail[i] for i in (0, 1))), 1.0)
            self.assertGreater(math.hypot(*(t_pose['tail'](-16, 47)[i] - base_t_tail[i] for i in (0, 1))), 1.0)

            b_canvas = Canvas(240, 72, active['camera'])
            draw_scene(b_canvas, dict(active, trex_x=-100), world.config)
            t_canvas = Canvas(240, 72, active['camera'])
            draw_scene(t_canvas, active, world.config)
            self.assertEqual(column_counts(b_canvas, 'brachiosaurus', torso_left, torso_right), base_b_torso)
            self.assertEqual(column_counts(t_canvas, 'trex', tx - 3.5, tx + 3.0), base_t_torso)

    def test_meteor_is_single_bounded_and_frozen_by_pause(self):
        for calm, steps in ((False, 14), (True, 24)):
            world = World(settings({'motion': {'reducedMotion': calm}}))
            self.assertTrue(world.spawn_meteor(8, 4))
            original = world.snapshot()['meteor']
            for _ in range(100):
                self.assertFalse(world.spawn_meteor(30, 10))
            self.assertEqual(world.snapshot()['meteor'], original)
            world.paused = True
            world.advance(250_000_000)
            self.assertEqual(world.snapshot()['meteor'], original)
            world.paused = False
            for _ in range(steps-1):
                world.advance(250_000_000)
            self.assertIsNotNone(world.snapshot()['meteor'])
            world.advance(250_000_000)
            self.assertIsNone(world.snapshot()['meteor'])
            self.assertTrue(world.spawn_meteor(12, 3))

    def test_meteor_position_depends_on_elapsed_time_not_frame_count(self):
        positions = []
        for fps in (15, 60, 144):
            world = World(settings())
            world.spawn_meteor(8, 4)
            for frame in range(fps*2):
                start = frame*2_000_000_000//(fps*2)
                end = (frame+1)*2_000_000_000//(fps*2)
                world.advance(end-start)
            positions.append(world.snapshot()['meteor'])
        self.assertEqual(positions[0], positions[1])
        self.assertEqual(positions[0], positions[2])

    def test_sky_click_targets_exclude_mountain_water_tree_and_dinosaur(self):
        canvas = self.scene(World(settings()))
        for point, expected in (((5, 4), 'sky'), ((21, 25), None),
                                ((20, 42), 'water'), ((94+FOCAL_OFFSET_X, 22), None),
                                ((69+FOCAL_OFFSET_X, 44), 'brachiosaurus')):
            x, y = map(round, canvas.project(*point))
            self.assertEqual(canvas.owners[y][x], expected, point)

    def test_falling_meteor_disappears_behind_opaque_mountain_interiors(self):
        world = World(settings({'motion': {'parallaxStrength': 0}}))
        world.spawn_meteor(0, 0)
        for target in (1_050_000_000, 2_275_000_000):
            while world.elapsed_ns < target:
                world.advance(min(250_000_000, target-world.elapsed_ns))
            pose = world.snapshot()
            visible = self.scene(world, pose)
            baseline = self.scene(world, dict(pose, meteor=None))
            visible.depth = METEOR_DEPTH
            x, y = map(round, visible.project(*pose['meteor']['head']))
            sample = lambda c: (c.chars[y][x], c.colors[y][x])
            if target == 1_050_000_000:
                self.assertEqual(visible.owners[y][x], 'sky')
                self.assertNotEqual(sample(visible), sample(baseline))
            else:
                self.assertIsNone(visible.owners[y][x])
                self.assertEqual(sample(visible), sample(baseline))

    def test_water_leap_arc_pause_reduced_motion_and_independent_effect_slots(self):
        lifts = {}
        for calm, duration in ((False, 2_200_000_000), (True, 3_600_000_000)):
            world = World(settings({'motion': {'reducedMotion': calm},
                                    'population': {'maxVisible': 128}}))
            self.assertTrue(world.spawn_water_jump(20, 43))
            self.assertTrue(world.spawn_meteor(5, 4))
            for _ in range(100):
                self.assertFalse(world.spawn_water_jump(80, 44))
                self.assertFalse(world.spawn_meteor(10, 3))
            start = world.snapshot()['water_jump']
            world.paused = True
            world.advance(250_000_000)
            self.assertEqual(world.snapshot()['water_jump'], start)
            world.paused = False
            while world.elapsed_ns < duration // 2:
                world.advance(min(250_000_000, duration // 2 - world.elapsed_ns))
            apex = world.snapshot()['water_jump']
            self.assertAlmostEqual(apex['x'], 20)
            lifts[calm] = 43 - apex['y']
            self.assertGreater(lifts[calm], 0)
            active = world.snapshot()
            world.reconfigure(settings({'scenery': {'nestEnabled': False}}))
            self.assertEqual(world.snapshot()['water_jump'], active['water_jump'])
            self.assertEqual(world.snapshot()['meteor'], active['meteor'])
            while world.elapsed_ns < duration - 1:
                world.advance(min(250_000_000, duration - 1 - world.elapsed_ns))
            landing = world.snapshot()['water_jump']
            self.assertAlmostEqual(landing['y'], 43, places=6)
            self.assertGreater(landing['x'], start['x'])
            world.advance(1)
            self.assertIsNone(world.snapshot()['water_jump'])
            self.assertIsNotNone(world.snapshot()['meteor'])
            self.assertTrue(world.spawn_water_jump(30, 42))
        self.assertLess(lifts[True], lifts[False])

    def test_lake_hit_region_obeys_world_bounds_parallax_and_actor_occlusion(self):
        world = World(settings({'scenery': {'lilyPadDensity': 0}}))
        pose = dict(world.snapshot(), camera=(1.5, .2), trex_x=-100)
        canvas = Canvas(500, 100, pose['camera'])
        draw_scene(canvas, pose, world.config)
        canvas.depth = WATER_DEPTH
        for point, expected in (((20, 42), 'water'), ((-12, 42), None),
                                ((123, 42), None), ((20, 50), None),
                                ((69+FOCAL_OFFSET_X, 44), 'brachiosaurus')):
            x, y = map(round, canvas.project(*point))
            self.assertEqual(canvas.owners[y][x], expected, point)

    def test_water_leap_renders_and_remains_behind_opaque_dinosaur(self):
        world = World(settings({'population': {'maxVisible': 128}}))
        self.assertTrue(world.spawn_water_jump(20, 43))
        for _ in range(4):
            world.advance(250_000_000)
        pose = dict(world.snapshot(), trex_x=-100)
        active = self.scene(world, pose)
        baseline = self.scene(world, dict(pose, water_jump=None))
        changed = [(x, y) for y in range(active.height) for x in range(active.width)
                   if (active.chars[y][x], active.colors[y][x]) !=
                      (baseline.chars[y][x], baseline.colors[y][x])]
        self.assertTrue(any(active.unproject(x, y, WATER_DEPTH)[1] < 40
                            for x, y in changed))
        hidden = dict(pose['water_jump'], x=69+FOCAL_OFFSET_X, y=43,
                      origin=(69+FOCAL_OFFSET_X, 44))
        occluded = self.scene(world, dict(pose, water_jump=hidden))
        for y, row in enumerate(baseline.owners):
            for x, owner in enumerate(row):
                if owner == 'brachiosaurus':
                    self.assertEqual((occluded.chars[y][x], occluded.colors[y][x]),
                                     (baseline.chars[y][x], baseline.colors[y][x]))


if __name__ == '__main__':
    unittest.main()
