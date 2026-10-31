#!/usr/bin/env python3
"""Omarchasaurus: animated truecolor character art inside a terminal."""
from __future__ import annotations
import argparse
import json
import math
import os
from pathlib import Path
import re
import select
import shutil
import signal
import struct
import sys
import termios
import time
import tty
from typing import NamedTuple

from canvas import BACKGROUNDS, Canvas
from engine import ACTOR_NAMES, World
from hatching import NEST_DEPTH
from layout import METEOR_DEPTH, WATER_DEPTH
from configuration import config_path, load_document
from safe_io import Directory, atomic_json, diagnostic, held_directory, open_file, read_json
from character_art import draw_scene
from event_preview import EVENTS, event_world, preview_settings



class Input:
    def __init__(self):
        self.data = bytearray()
        self.since = 0.0

    def feed(self, data, now):
        if data and not self.data:
            self.since = now
        self.data.extend(data)
        if len(self.data) > 4096:
            self.data.clear()
            return [('key', b'overflow')]
        result = []
        while self.data:
            if self.data[0] != 27:
                result.append(('key', bytes(self.data[:1])))
                del self.data[:1]
                continue
            p = bytes(self.data)
            if b'\x1b[<'.startswith(p):
                if now-self.since < .08:
                    break
            if p.startswith(b'\x1b[<'):
                match = re.match(rb'\x1b\[<(\d+);(\d+);(\d+)([Mm])', p)
                if match:
                    code, x, y = (int(match[i]) for i in (1, 2, 3))
                    del self.data[:match.end()]
                    if match[4] == b'M':
                        result.append(('motion' if code & 32 else 'click', (x-1, y-1)))
                    continue
                if len(p) < 64 and now-self.since < .08:
                    break
            if p.startswith((b'\x1b_', b'\x1b]', b'\x1bP')):
                end = p.find(b'\x1b\\')
                bell = p.find(b'\x07')
                if end >= 0:
                    del self.data[:end+2]
                    continue
                if bell >= 0:
                    del self.data[:bell+1]
                    continue
                if now-self.since < .08:
                    break
                self.data.clear()
                continue
            match = re.match(rb'\x1b\[[0-?]*[ -/]*[@-~]', p)
            if match:
                del self.data[:match.end()]
                # Device attribute/status replies are not user dismissal keys.
                if match[0][-1:] not in (b'c', b'n', b'R'):
                    result.append(('key', match[0]))
                continue
            if len(p) == 1 and now-self.since < .08:
                break
            result.append(('key', b'\x1b'))
            del self.data[:1]
        return result


class Terminal:
    def __init__(self):
        self.saved = None
        self.active = False

    def enter(self):
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise RuntimeError('animation needs an interactive terminal; use --snapshot for redirected output')
        self.saved = termios.tcgetattr(sys.stdin.fileno())
        tty.setcbreak(sys.stdin.fileno())
        self.active = True
        sys.stdout.write('\x1b[?1049h\x1b[2J\x1b[H\x1b[?25l\x1b[?1003h\x1b[?1006h')
        sys.stdout.flush()

    def restore(self):
        if not self.active:
            return
        try:
            sys.stdout.write('\x1b[?1003l\x1b[?1006l\x1b[0m\x1b[?25h\x1b[?1049l')
            sys.stdout.flush()
        finally:
            if self.saved is not None:
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, self.saved)
            self.active = False


def dimensions():
    size = shutil.get_terminal_size((120, 36))
    return max(1, min(500, size.columns-1)), max(1, min(200, size.lines-1))


def cell_aspect():
    try:
        import fcntl
        rows, cols, px, py = struct.unpack('HHHH', fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, b'\0'*8))
        if rows and cols and px and py:
            return (py/rows)/(px/cols)
    except (OSError, ValueError):
        pass
    return 2.0


def notify_dismissal(directory):
    if directory is None:
        return
    with held_directory(directory) as held:
        authority = read_json(held.fd, 'authority.json', limit=256, private=True)
        if (not isinstance(authority, dict) or set(authority) != {'token'}
                or not isinstance(authority['token'], str)
                or not re.fullmatch(r'[A-Za-z0-9_-]{43}', authority['token'])):
            raise ValueError('Invalid session dismissal authority')
        atomic_json(held.fd, 'dismissed.json', authority, private=True)


def session_alive(directory, preview):
    """Probe the held coordinator lock without blocking on an unsafe FIFO."""
    if directory is None:
        return True
    import fcntl
    try:
        with held_directory(directory) as held:
            fd = open_file(held.parent_fd, 'preview.lock' if preview else 'start.lock', private=True)
            try:
                try:
                    fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
                    return False
                except BlockingIOError:
                    return True
            finally:
                os.close(fd)
    except (OSError, ValueError):
        return False


class PreviewAction(NamedTuple):
    stop: bool = False
    redraw: bool = False
    reload: bool = False
    diagnostic: str | None = None


def _apply_preview_event(world, event, canvas, origin, document, overrides, preview_overrides, test_event=None):
    kind, payload = event
    if kind == 'key':
        key = payload.lower()
        if key in (b'q', b'\x1b', b'\x03'):
            return PreviewAction(stop=True)
        if key == b' ':
            world.paused = not world.paused
            return PreviewAction(redraw=True)
        if key == b'p':
            preview_overrides['preset'] = 'dusk' if world.config['preset'] == 'morning' else 'morning'
        elif key == b'n':
            preview_overrides['seed'] = (world.config['seed']+1) % (2**53)
        elif key == b'r':
            preview_overrides.clear()
        else:
            return PreviewAction()
        world.reconfigure(preview_settings(document, overrides | preview_overrides, test_event))
        return PreviewAction(redraw=True, reload=key == b'r')
    if kind != 'click' or canvas is None:
        return PreviewAction()
    x, y = payload[0]-origin[0], payload[1]-origin[1]
    if not (0 <= x < canvas.width and 0 <= y < canvas.height):
        return PreviewAction()
    owner = canvas.owners[y][x]
    if owner == 'sky':
        if world.spawn_meteor(*canvas.unproject(x, y, METEOR_DEPTH)):
            return PreviewAction(redraw=True, diagnostic='preview reaction: meteor')
    elif owner == 'water':
        if world.spawn_water_jump(*canvas.unproject(x, y, WATER_DEPTH)):
            return PreviewAction(redraw=True, diagnostic='preview reaction: water jump')
        return PreviewAction(diagnostic='lake jump already active or no free animal slot; visible animals keep their places')
    elif owner == 'nest':
        if world.hatch_egg(canvas.unproject(x, y, NEST_DEPTH)[0]):
            return PreviewAction(redraw=True, diagnostic='preview reaction: Brachiosaurus egg hatching')
        reason = ('paused' if world.paused else
                  'already active' if world.hatching.active else
                  'no free animal slot' if not world.cast.available(world.config['population']['maxVisible'])
                  else 'nest unavailable')
        return PreviewAction(diagnostic=f'egg hatch unavailable: {reason}; visible animals keep their places')
    elif world.react(owner):
        return PreviewAction(redraw=True, diagnostic=f'preview reaction: {ACTOR_NAMES[owner]}')
    return PreviewAction()


class PreviewTooltip(NamedTuple):
    x: int
    y: int
    text: str


def _preview_tooltip(canvas, pointer, origin):
    """Read only the current scene's painted ownership, in terminal cells."""
    if pointer is None:
        return None
    x, y = pointer[0]-origin[0], pointer[1]-origin[1]
    if not (0 <= x < canvas.width and 0 <= y < canvas.height):
        return None
    owner = canvas.owners[y][x]
    name = ACTOR_NAMES.get(owner)
    # Flyers have painted identities but deliberately have no click reaction.
    if name is None and owner is not None and owner.startswith('pteranodon:'):
        name = 'Pteranodon'
    if name is None:
        return None
    text = f' {name} '
    if len(text) > canvas.width:
        text = name if len(name) <= canvas.width else (
            name[:canvas.width-3]+'...' if canvas.width > 3 else name[:canvas.width])
    left = max(0, min(x+1, canvas.width-len(text)))
    row = y-1 if y > 0 else min(1, canvas.height-1)
    return PreviewTooltip(left, row, text)


def _preview_frame(canvas, background, origin, pointer):
    frame = canvas.ansi(background, origin)
    tooltip = _preview_tooltip(canvas, pointer, origin)
    if tooltip is not None:
        # A display-only overlay: never write into chars/colors/owners. Clicks
        # and the next hover still see the undecorated scene under this label.
        frame += (f'\x1b[{tooltip.y+origin[1]+1};{tooltip.x+origin[0]+1}H'
                  '\x1b[1;38;2;246;240;220;48;2;22;29;40m'
                  f'{tooltip.text}\x1b[0m')
    return frame


def animate(args, config, overrides, document):
    world = World(config)
    pending_test = args.test_event
    terminal = Terminal()
    decoder = Input()
    stopping = False
    suspending = False
    diagnostics = []
    reload_error = None
    def stop(_sig, _frame):
        nonlocal stopping
        stopping = True
    def suspend(_sig, _frame):
        nonlocal suspending
        suspending = True
    handlers = {sig: signal.signal(sig, stop) for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT)}
    handlers[signal.SIGTSTP] = signal.signal(signal.SIGTSTP, suspend)
    started = time.monotonic()
    last = time.monotonic_ns()
    last_config = None
    last_probe = 0.0
    baseline = None
    dismissed = False
    frames = 0
    last_canvas = None
    pointer = None
    redraw = True
    preview_overrides = {}
    previous_size = None
    try:
        if args.test_event:
            print(f'Omarchasaurus: session-only {args.test_event} test; saved settings unchanged.', file=sys.stderr)
        terminal.enter()
        while not stopping:
            now = time.monotonic()
            if args.duration is not None and now-started >= args.duration:
                break
            if suspending:
                terminal.restore()
                os.kill(os.getpid(), signal.SIGSTOP)
                terminal.enter()
                suspending = False
                last = time.monotonic_ns()
                baseline = None
                pointer = None
                previous_size = None
                redraw = True
                continue
            if now-last_probe >= 1:
                last_probe = now
                if not session_alive(args.session_dir, args.preview):
                    break
                try:
                    signature = (args.config.stat().st_mtime_ns, args.config.stat().st_size) if args.config.exists() else None
                    if signature != last_config:
                        candidate_document = load_document(args.config)
                        candidate = preview_settings(candidate_document, overrides | preview_overrides, args.test_event)
                        if candidate != world.config:
                            world.reconfigure(candidate)
                            redraw = True
                        document = candidate_document
                        last_config = signature
                        reload_error = None
                except (OSError, ValueError) as error:
                    reload_error = 'invalid reload retained last valid scene: ' + diagnostic(error)
            tick_now = time.monotonic_ns()
            width, height = dimensions()
            aspect = cell_aspect()
            screen = shutil.get_terminal_size((160, 48))
            left = max(0, (screen.columns-1-width)//2)
            top = max(0, (screen.lines-1-height)//2)
            background = BACKGROUNDS[world.config['preset']]
            geometry = (width, height, left, top, background, aspect)
            # Keep polling paused input/reloads/geometry without rasterizing an
            # unchanged scene. A restored terminal buffer must be painted again.
            paint = redraw or not world.paused or previous_size != geometry
            if paint:
                canvas = Canvas(width, height, cell_aspect=aspect)
                if pending_test:
                    world = event_world(world.config, pending_test, canvas.world_bounds)
                    pending_test = None
                    # Bootstrap time is not an interactive frame's elapsed time.
                    tick_now = last = time.monotonic_ns()
                world.set_viewport(canvas.world_bounds)
            world.advance(tick_now-last)
            last = tick_now
            if paint:
                if previous_size != geometry:
                    sys.stdout.write(f'\x1b[48;2;{background[0]};{background[1]};{background[2]}m\x1b[2J')
                    previous_size = geometry
                pose = world.snapshot()
                canvas.camera = pose['camera']
                draw_scene(canvas, pose, world.config)
                if args.preview:
                    sys.stdout.write(_preview_frame(canvas, background, (left, top), pointer))
                else:
                    sys.stdout.write(canvas.ansi(background, (left, top)))
                sys.stdout.flush()
                last_canvas = canvas
                redraw = False
                frames += 1
            wait = max(0, 1/args.fps-(time.monotonic()-now))
            ready = select.select([sys.stdin], [], [], wait)[0]
            data = os.read(sys.stdin.fileno(), 4096) if ready else b''
            if ready and not data:
                break
            for kind, payload in decoder.feed(data, time.monotonic()):
                if not args.preview:
                    if time.monotonic()-started < .75:
                        baseline = payload if kind == 'motion' else baseline
                        continue
                    if kind == 'motion':
                        if baseline is None:
                            baseline = payload
                            continue
                        if not world.config['integration']['exitOnPointerMotion'] or math.dist(payload, baseline) < 2:
                            continue
                    dismissed = True
                    stopping = True
                else:
                    if kind in ('motion', 'click') and pointer != payload:
                        pointer = payload
                        redraw = True
                    action = _apply_preview_event(
                        world, (kind, payload), last_canvas, (left, top),
                        document, overrides, preview_overrides, args.test_event)
                    stopping = stopping or action.stop
                    redraw = redraw or action.redraw
                    if action.reload:
                        last_config = object()
                    if action.diagnostic is not None:
                        diagnostics[:] = [action.diagnostic]
    finally:
        try:
            terminal.restore()
        finally:
            for sig, handler in handlers.items():
                signal.signal(sig, handler)
    if dismissed:
        notify_dismissal(args.session_dir)
    elapsed = time.monotonic()-started
    print(f'Omarchasaurus: {frames} terminal frames in {elapsed:.2f}s, {frames/max(elapsed,.001):.1f} fps; terminal restored.', file=sys.stderr)
    if reload_error is not None:
        print(reload_error, file=sys.stderr)
    for message in diagnostics:
        print(message, file=sys.stderr)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description='Omarcharium-style truecolor terminal dinosaur valley')
    parser.add_argument('--config', type=Path)
    parser.add_argument('--seed', type=int)
    parser.add_argument('--preset', choices=('morning', 'dusk'))
    parser.add_argument('--preview', action='store_true')
    parser.add_argument('--test-event', choices=EVENTS,
                        help='session-only real event test; requires --preview; isolates optional animals, '
                             'reserves seats and enables prerequisites without saving; keeps palette and motion settings')
    parser.add_argument('--snapshot', action='store_true')
    parser.add_argument('--ansi', action='store_true', help='ANSI colors for snapshots; no image protocol')
    parser.add_argument('--width', type=int, default=160)
    parser.add_argument('--height', type=int, default=48)
    parser.add_argument('--time', type=float, default=12)
    parser.add_argument('--fps', type=int, default=15)
    parser.add_argument('--duration', type=float)
    parser.add_argument('--check-config', action='store_true')
    parser.add_argument('--session-dir', type=Path)
    parser.add_argument('--output')
    args = parser.parse_args(argv)
    if args.test_event and (not args.preview or args.snapshot or args.check_config):
        parser.error('--test-event requires an interactive --preview; it cannot be used with --snapshot or --check-config')
    if not 1 <= args.fps <= 30:
        parser.error('--fps must be 1..30')
    if not math.isfinite(args.time) or not 0 <= args.time <= 86400:
        parser.error('--time must be finite seconds in 0..86400')
    if args.duration is not None and (not math.isfinite(args.duration) or not 0 < args.duration <= 86400):
        parser.error('--duration must be positive finite seconds up to 86400')
    overrides = {}
    if args.seed is not None:
        overrides['seed'] = args.seed
    if args.preset is not None:
        overrides['preset'] = args.preset
    try:
        args.config = args.config if args.config is not None else config_path()
        document = load_document(args.config)
        config = preview_settings(document, overrides, args.test_event)
        if args.check_config:
            print(json.dumps(config, indent=2))
            return 0
        if args.snapshot:
            if not 1 <= args.width <= 500 or not 1 <= args.height <= 200:
                parser.error('snapshot dimensions: width1..500 height1..200')
            world = World(config, elapsed_ns=round(args.time*1e9))
            canvas = Canvas(args.width, args.height)
            world.set_viewport(canvas.world_bounds)
            pose = world.snapshot()
            canvas.camera = pose['camera']
            draw_scene(canvas, pose, config)
            print(canvas.ansi(BACKGROUNDS[config['preset']]) if args.ansi else canvas.plain())
            return 0
        if args.session_dir is None:
            return animate(args, config, overrides, document)
        with Directory.open(args.session_dir, private=True) as session:
            args.session_dir = session
            return animate(args, config, overrides, document)
    except (OSError, ValueError, RuntimeError) as error:
        print('Omarchasaurus: ' + diagnostic(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
