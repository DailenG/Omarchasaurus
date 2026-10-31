import fcntl
from contextlib import ExitStack
from io import StringIO
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
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from canvas import BACKGROUNDS, Canvas
from engine import ACTOR_NAMES, World
from configuration import load_settings, settings
from dinosaurs import (Input, _apply_preview_event, _preview_frame,
                       _preview_tooltip, animate, session_alive)
from character_art import _brachiosaurus_pose, _trex_pose, draw_scene
from hatching import NEST_DEPTH, egg_offsets
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


class PreviewHover(unittest.TestCase):
    def test_painted_owners_keep_species_and_young_names(self):
        names = {
            'brachiosaurus': 'Brachiosaurus',
            'brachiosaurus:young': 'Young Brachiosaurus',
            'triceratops:calf': 'Triceratops calf',
            'parasaurolophus:1:3': 'Parasaurolophus juvenile',
            'pteranodon:0': 'Pteranodon',
            'pteranodon:flock:4': 'Pteranodon',
        }
        for owner, name in names.items():
            with self.subTest(owner=owner):
                canvas = Canvas(80, 24)
                # Opaque blank interiors are animal pixels, not just strokes.
                canvas.put(12, 8, ' ', (50, 100, 80), owner=owner)
                label = _preview_tooltip(canvas, (19, 11), (7, 3))
                self.assertEqual(label.text.strip(), name)
                self.assertEqual(label.y, 7)
                frame = _preview_frame(canvas, BACKGROUNDS['morning'], (7, 3), (19, 11))
                self.assertIn(f'\x1b[{label.y+4};{label.x+8}H', frame)
                self.assertIn(name, frame)

    def test_background_occlusion_and_unidentified_water_animal_have_no_name(self):
        canvas = Canvas(80, 24)
        for owner in (None, 'sky', 'water', 'nest', 'water_jump'):
            canvas.put(5, 5, '.', (80, 100, 80), owner=owner)
            self.assertIsNone(_preview_tooltip(canvas, (5, 5), (0, 0)), owner)
        canvas.put(4, 5, 'x', (80, 100, 80), owner='trex')
        canvas.put(6, 5, 'x', (80, 100, 80), owner='trex')
        # The hole inside an animal's rectangular bounds is not its pixel.
        self.assertIsNone(_preview_tooltip(canvas, (5, 5), (0, 0)))
        canvas.put(4, 5, '.', (80, 100, 80))
        self.assertIsNone(_preview_tooltip(canvas, (4, 5), (0, 0)))

    def test_edges_tiny_grids_and_letterbox_offsets_stay_visible(self):
        for width, height in ((80, 24), (24, 3), (8, 2), (3, 1), (1, 1)):
            for x, y in ((0, 0), (width-1, 0), (0, height-1), (width-1, height-1)):
                with self.subTest(size=(width, height), pointer=(x, y)):
                    canvas = Canvas(width, height)
                    canvas.put(x, y, 'o', (50, 100, 80), owner='parasaurolophus:0:1')
                    label = _preview_tooltip(canvas, (x+9, y+4), (9, 4))
                    self.assertTrue(label.text.strip())
                    self.assertGreaterEqual(label.x, 0)
                    self.assertLessEqual(label.x+len(label.text), width)
                    self.assertGreaterEqual(label.y, 0)
                    self.assertLess(label.y, height)
                    if height > 1:
                        self.assertNotEqual(label.y, y)
                    for outside in ((8, y+4), (x+9, 3), (width+9, y+4), (x+9, height+4)):
                        self.assertIsNone(_preview_tooltip(canvas, outside, (9, 4)))
                    self.assertIsNone(_preview_tooltip(canvas, None, (9, 4)))

    def test_current_frame_recomputes_after_movement_culling_and_resize(self):
        pointer, origin = (12, 7), (7, 3)
        canvas = Canvas(80, 24)
        canvas.put(5, 4, 'o', (50, 100, 80), owner='triceratops:calf')
        self.assertIn('Triceratops calf', _preview_frame(canvas, BACKGROUNDS['morning'], origin, pointer))
        canvas.put(5, 4, '.', (50, 100, 80))
        canvas.put(9, 4, 'o', (50, 100, 80), owner='triceratops:calf')
        self.assertIsNone(_preview_tooltip(canvas, pointer, origin))
        self.assertIn('Triceratops calf', _preview_tooltip(canvas, (16, 7), origin).text)
        # A newly rasterized, culled scene cannot retain the old label.
        self.assertIsNone(_preview_tooltip(Canvas(80, 24), (16, 7), origin))
        resized = Canvas(3, 2)
        self.assertIsNone(_preview_tooltip(resized, pointer, origin))
        resized.put(1, 1, 'o', (50, 100, 80), owner='brachiosaurus')
        self.assertIsNotNone(_preview_tooltip(resized, (21, 11), (20, 10)))

    def test_real_scene_uses_current_visible_pixels_not_animal_bounds(self):
        world = World(settings(), elapsed_ns=12_000_000_000)
        canvas = Canvas(160, 60)
        world.set_viewport(canvas.world_bounds)
        pose = world.snapshot()
        canvas.camera = pose['camera']
        draw_scene(canvas, pose, world.config)
        cells = [(x, y) for y, row in enumerate(canvas.owners)
                 for x, owner in enumerate(row) if owner == 'brachiosaurus']
        self.assertTrue(cells)
        pointer = cells[len(cells)//2]
        self.assertEqual(_preview_tooltip(canvas, pointer, (0, 0)).text.strip(), 'Brachiosaurus')
        x, y, width, height = canvas.bounds('brachiosaurus')
        holes = [(px, py) for py in range(y, y+height) for px in range(x, x+width)
                 if canvas.owners[py][px] not in ACTOR_NAMES
                 and not (canvas.owners[py][px] or '').startswith('pteranodon:')]
        self.assertTrue(holes)
        for hole in holes:
            self.assertIsNone(_preview_tooltip(canvas, hole, (0, 0)))
        decorated = _preview_frame(canvas, BACKGROUNDS['morning'], (0, 0), pointer)
        self.assertIn('Brachiosaurus', decorated)
        self.assertEqual(world.snapshot(), pose)

    def test_overlay_preserves_scene_ownership_admission_and_underlying_clicks(self):
        config = settings({'animals': {name: False for name in settings()['animals']},
                           'population': {'maxVisible': 2}})
        world = World(config)
        canvas = Canvas(160, 48)
        canvas.depth = WATER_DEPTH
        water_x, water_y = map(round, canvas.project(65, 42))
        anchor = (water_x - 1, water_y + 1)
        canvas.put(*anchor, 'x', (50, 100, 80), owner='brachiosaurus')
        label = _preview_tooltip(canvas, anchor, (0, 0))
        canvas.put(label.x, label.y, '.', (50, 100, 80), owner='water')
        original = tuple(tuple(tuple(row) for row in grid)
                         for grid in (canvas.chars, canvas.colors, canvas.owners))
        pose, cast = world.snapshot(), tuple(world.cast.members)
        decorated = _preview_frame(canvas, BACKGROUNDS['morning'], (0, 0), anchor)
        self.assertIn('Brachiosaurus', decorated)
        self.assertEqual(original, tuple(tuple(tuple(row) for row in grid)
                                       for grid in (canvas.chars, canvas.colors, canvas.owners)))
        self.assertEqual(world.snapshot(), pose)
        self.assertEqual(tuple(world.cast.members), cast)
        self.assertIsNone(world.water_jump)
        action = _apply_preview_event(
            world, ('click', (label.x, label.y)), canvas, (0, 0), config, {}, {})
        self.assertIsNotNone(world.water_jump)
        self.assertTrue(action.redraw)
        _apply_preview_event(world, ('click', anchor), canvas, (0, 0), config, {}, {})
        self.assertIn('brachiosaurus', world.reactions)
        canvas.put(*anchor, 'v', (50, 100, 80), owner='pteranodon:0')
        self.assertIn('Pteranodon', _preview_frame(canvas, BACKGROUNDS['morning'], (0, 0), anchor))
        action = _apply_preview_event(
            world, ('click', anchor), canvas, (0, 0), config, {}, {})
        self.assertFalse(action.redraw)
        self.assertIsNone(action.diagnostic)

    def run_paused_loop(self, events, *, preview=True, motion_exit=True, sizes=None, expected_reads=None):
        world = World(settings({'integration': {'exitOnPointerMotion': motion_exit}}))
        world.paused = True
        clock = [0.0]
        output, rendered, poses = StringIO(), [], []
        pending = iter(events)
        received = []
        current = [b'']
        dimensions = iter(sizes or [(80, 24)]*len(events))

        def ready(*_args):
            current[0] = next(pending)
            received.append(current[0])
            clock[0] += .25
            return ([] if current[0] is None else [sys.stdin], [], [])

        def draw(canvas, pose, _config):
            poses.append(pose)
            canvas.put(2, 2, 'o', (50, 100, 80), owner='brachiosaurus:young')

        def frame(*args):
            result = _preview_frame(*args)
            rendered.append(result)
            return result

        args = SimpleNamespace(test_event=None, duration=None, session_dir=None,
                               config=Path('/unused-hover-test-config'), preview=preview, fps=24)
        with ExitStack() as stack:
            replacements = {
                'World': lambda _config: world,
                'Terminal.enter': lambda _self: None,
                'Terminal.restore': lambda _self: None,
                'time.monotonic': lambda: clock[0],
                'time.monotonic_ns': lambda: int(clock[0]*1_000_000_000),
                'dimensions': lambda: next(dimensions),
                'cell_aspect': lambda: 2.0,
                'shutil.get_terminal_size': lambda _fallback: os.terminal_size((81, 25)),
                'select.select': ready,
                'os.read': lambda *_args: current[0],
                'sys.stdout': output,
                'sys.stderr': StringIO(),
                'draw_scene': draw,
                '_preview_frame': frame,
                'load_document': lambda _path: world.config,
            }
            for target, replacement in replacements.items():
                stack.enter_context(patch('dinosaurs.'+target, replacement))
            dismissal = stack.enter_context(patch('dinosaurs.notify_dismissal'))
            self.assertEqual(animate(args, world.config, {}, world.config), 0)
        self.assertEqual(len(received), len(events) if expected_reads is None else expected_reads)
        self.assertEqual((world.tick, world.elapsed_ns), (0, 0))
        if sizes is None:
            self.assertTrue(all(pose == poses[0] for pose in poses))
            self.assertEqual(world.snapshot(), poses[-1])
        return rendered, output.getvalue(), dismissal

    def test_motion_redraws_paused_preview_and_clears_after_background_and_resize(self):
        motion = b'\x1b[<35;3;3M'
        rendered, _output, dismissal = self.run_paused_loop([
            motion, b'\x1b[<35;20;20M', motion, b'q'])
        self.assertEqual(len(rendered), 4)
        self.assertNotIn('Young Brachiosaurus', rendered[0])
        self.assertIn('Young Brachiosaurus', rendered[1])
        self.assertNotIn('Young Brachiosaurus', rendered[2])
        self.assertIn('Young Brachiosaurus', rendered[3])
        dismissal.assert_not_called()
        rendered, _output, _dismissal = self.run_paused_loop(
            [motion, None, b'q'], sizes=[(80, 24), (80, 24), (2, 1)])
        self.assertIn('Young Brachiosaurus', rendered[1])
        self.assertNotIn('Young Brachiosaurus', rendered[2])

    def test_ordinary_start_retains_arming_motion_threshold_and_key_dismissal(self):
        events = [b'\x1b[<35;1;1M', b'\x1b[<0;3;3M',
                  b'\x1b[<35;2;1M', b'\x1b[<35;4;1M', b'q']
        rendered, _output, dismissal = self.run_paused_loop(events, preview=False, expected_reads=4)
        self.assertFalse(rendered)
        dismissal.assert_called_once_with(None)
        rendered, _output, dismissal = self.run_paused_loop(
            events, preview=False, motion_exit=False)
        self.assertFalse(rendered)
        dismissal.assert_called_once_with(None)


class PreviewInteractions(unittest.TestCase):
    def hatch_world(self, maximum=2):
        return World(settings({
            'animals': {name: False for name in settings()['animals']},
            'population': {'maxVisible': maximum, 'maxFamilies': 0, 'randomVisitors': False},
        }))

    def click(self, world, canvas, cell, origin=(0, 0)):
        x, y = cell[0]+origin[0], cell[1]+origin[1]
        events = Input().feed(f'\x1b[<0;{x+1};{y+1}M'.encode(), 0)
        self.assertEqual(events, [('click', (x, y))])
        return _apply_preview_event(world, events[0], canvas, origin, world.config, {}, {})

    def owner_cell(self, canvas, owner, near=None):
        cells = [(x, y) for y, row in enumerate(canvas.owners)
                 for x, value in enumerate(row) if value == owner]
        self.assertTrue(cells, owner)
        return cells[0] if near is None else min(
            cells, key=lambda cell: math.dist(cell, near))

    def test_rendered_egg_click_unprojects_nest_depth_and_selects_that_egg(self):
        for camera in ((-4, -2), (0, 0), (4, 2)):
            for index in range(self.hatch_world().layout.nest.eggs):
                world = self.hatch_world()
                snapshot = dict(world.snapshot(), camera=camera)
                canvas = Canvas(480, 180, camera)
                world.set_viewport(canvas.world_bounds)
                draw_scene(canvas, snapshot, world.config)
                nest = world.layout.nest
                canvas.depth = NEST_DEPTH
                point = canvas.project(nest.x+egg_offsets(nest)[index], nest.y-.8)
                cell = self.owner_cell(canvas, 'nest', point)
                deadline, rng = world.hatching.deadline, world.hatching.rng.getstate()
                with patch.object(world, 'hatch_egg', wraps=world.hatch_egg) as hatch:
                    action = self.click(world, canvas, cell, origin=(7, 3))
                hatch.assert_called_once_with(canvas.unproject(*cell, NEST_DEPTH)[0])
                self.assertTrue(action.redraw)
                self.assertEqual(action.diagnostic, 'preview reaction: Brachiosaurus egg hatching')
                self.assertEqual(world.hatching.egg_index, index)
                self.assertIn('brachiosaurus:young', world.cast.members)
                self.assertEqual(world.hatching.deadline, deadline)
                self.assertEqual(world.hatching.rng.getstate(), rng)
                identity = world.hatching.generation, world.hatching.born, world.hatching.egg_index
                repeated = self.click(world, canvas, cell)
                self.assertFalse(repeated.redraw)
                self.assertIn('already active', repeated.diagnostic)
                self.assertEqual((world.hatching.generation, world.hatching.born,
                                  world.hatching.egg_index), identity)
                self.assertEqual(world.hatching.deadline, deadline)
                self.assertEqual(world.hatching.rng.getstate(), rng)

    def test_bowl_pixel_selects_nearest_egg_and_baby_pixels_keep_their_reaction(self):
        world = self.hatch_world()
        canvas = self.scene(world)
        nest = world.layout.nest
        canvas.depth = NEST_DEPTH
        near = canvas.project(nest.x-nest.radius+.3, nest.y-.3)
        cell = self.owner_cell(canvas, 'nest', near)
        world_x = canvas.unproject(*cell, NEST_DEPTH)[0]
        index = min(range(nest.eggs),
                    key=lambda egg: abs(nest.x+egg_offsets(nest)[egg]-world_x))
        self.assertTrue(self.click(world, canvas, cell).redraw)
        self.assertEqual(world.hatching.egg_index, index)
        for _ in range(88):
            world.advance(250_000_000)
        self.assertEqual(world.hatching.current()['state'], 'lingering')
        frame = self.scene(world)
        with patch.object(world, 'hatch_egg', wraps=world.hatch_egg) as hatch:
            action = self.click(world, frame, self.owner_cell(frame, 'brachiosaurus:young'))
        hatch.assert_not_called()
        self.assertTrue(action.redraw)
        self.assertEqual(action.diagnostic, 'preview reaction: Young Brachiosaurus')

    def test_paused_and_full_cast_egg_clicks_refuse_without_replacing_occupants(self):
        for paused, maximum, reason in ((True, 2, 'paused'), (False, 1, 'no free animal slot')):
            world = self.hatch_world(maximum)
            world.paused = paused
            canvas = self.scene(world)
            before = world.cast.members
            deadline, rng = world.hatching.deadline, world.hatching.rng.getstate()
            action = self.click(world, canvas, self.owner_cell(canvas, 'nest'))
            self.assertFalse(action.redraw)
            self.assertIn(reason, action.diagnostic)
            self.assertFalse(world.hatching.active)
            self.assertEqual(world.cast.members, before)
            self.assertEqual(world.hatching.deadline, deadline)
            self.assertEqual(world.hatching.rng.getstate(), rng)

    def test_opaque_scenery_and_dinosaur_remove_nest_clickthrough(self):
        for owner in (None, 'brachiosaurus'):
            world = self.hatch_world()
            canvas = self.scene(world)
            x, y = self.owner_cell(canvas, 'nest')
            a = canvas.unproject(x-1, y-1)
            b = canvas.unproject(x+1, y+1)
            canvas.polygon(((a[0], a[1]), (b[0], a[1]),
                            (b[0], b[1]), (a[0], b[1])),
                           (50, 80, 30), owner=owner, fill=' ')
            self.assertEqual(canvas.owners[y][x], owner)
            with patch.object(world, 'hatch_egg', wraps=world.hatch_egg) as hatch:
                action = self.click(world, canvas, (x, y))
            hatch.assert_not_called()
            self.assertFalse(world.hatching.active)
            self.assertEqual(action.redraw, owner == 'brachiosaurus')

    def test_sky_water_and_dinosaur_click_precedence_stays_separate_from_eggs(self):
        for owner, diagnostic in (('sky', 'meteor'), ('water', 'water jump'),
                                  ('brachiosaurus', 'Brachiosaurus')):
            world = self.hatch_world()
            canvas = self.scene(world)
            with patch.object(world, 'hatch_egg', wraps=world.hatch_egg) as hatch:
                action = self.click(world, canvas, self.owner_cell(canvas, owner))
            hatch.assert_not_called()
            self.assertTrue(action.redraw)
            self.assertIn(diagnostic, action.diagnostic)
            self.assertFalse(world.hatching.active)

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
