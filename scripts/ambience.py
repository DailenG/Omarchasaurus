"""Optional local wind/water noise; one owned PipeWire stream per runtime.

The renderer owns a worker through a pipe, not a thread. EOF (including renderer
SIGKILL) lets that separate-session worker stop/reap its transport before releasing
leadership. Transport stderr is discarded, never collected or forwarded.
"""
import fcntl
import math
import os
from pathlib import Path
import random
import select
import shutil
import signal
import struct
import subprocess
import sys
import time

from bounded_process import exited, finish_group
from safe_io import Directory, diagnostic, open_file

RATE = 12000
FRAMES = 600
BLOCK_SECONDS = FRAMES / RATE
BLOCK_BYTES = FRAMES * 2
WRITE_DEADLINE = .75
LEADER_RETRY = 2.0
MAX_DIAGNOSTIC = 384


def checked_volume(value):
    if type(value) is not int or not 0 <= value <= 100:
        raise ValueError('ambience volume must be an integer in 0..100')
    return value


class PCM:
    """Fixed-size mono native-endian signed-16 noise, independent of scene RNG."""
    def __init__(self, seed=None):
        self.rng = random.Random(seed)
        self.wind = 0.0
        self.water = 0.0

    def render(self, volume):
        gain = checked_volume(volume) / 100
        block = bytearray(BLOCK_BYTES)
        wind, water = self.wind, self.water
        for index in range(FRAMES):
            noise = self.rng.random() * 2 - 1
            wind += .02 * (noise - wind)
            water += .18 * (noise - water)
            # Soft, non-tonal wind and water hiss, never animal vocalisations.
            level = max(-.45, min(.45, (1.2 * wind + .3 * water) * gain))
            struct.pack_into('=h', block, index * 2, int(level * 32767))
        self.wind, self.water = wind, water
        return block


class Leadership:
    """A retained flock on a validated private, descriptor-relative inode."""
    def __init__(self, runtime=None):
        self.directory = None
        self.fd = None
        runtime = os.environ.get('XDG_RUNTIME_DIR') if runtime is None else runtime
        if not runtime:
            raise ValueError('XDG_RUNTIME_DIR is unavailable; no audio runtime fallback')
        with Directory.open(runtime, private=True) as root:
            try:
                os.mkdir('omarchasaurus-terminal', 0o700, dir_fd=root.fd)
            except FileExistsError:
                pass
            self.directory = root.child('omarchasaurus-terminal')
        try:
            self.fd = open_file(self.directory.fd, 'audio.lock', os.O_RDWR,
                                private=True, create=True)
        except BaseException:
            self.close()
            raise

    def acquire(self):
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            return False

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        if self.directory is not None:
            self.directory.close()
            self.directory = None


def playback_command():
    executable = shutil.which('pw-cat')
    if executable is None:
        raise ValueError('pw-cat is unavailable; optional ambience needs PipeWire tools')
    return [executable, '--playback', '--raw', '--format', 's16',
            '--rate', str(RATE), '--channels', '1', '-']


def run_worker(volume, transport=None, control_fd=0, runtime=None):
    """Run actual synthesis/ownership; transport injection is for private tests.

    The control pipe carries only single-byte volumes, and EOF always means stop.
    There is at most one 50ms PCM block, with an absolute write deadline. Standby
    contenders sleep via select and retry leadership only every two seconds.
    """
    volume = checked_volume(volume)
    stopping = False
    child = None
    leadership = None
    handlers = {}

    def stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    try:
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT):
            handlers[sig] = signal.signal(sig, stop)
        os.set_blocking(control_fd, False)
        leadership = Leadership(runtime)
        next_try = 0.0
        next_block = 0.0
        pending = None
        offset = 0
        pending_since = 0.0
        pcm = None
        while not stopping:
            # Check EOF before acquiring leadership or creating any transport.
            try:
                commands = os.read(control_fd, 64)
            except BlockingIOError:
                commands = None
            if commands == b'':
                return 0
            if commands:
                if any(value > 100 for value in commands):
                    raise ValueError('invalid ambience control byte')
                volume = commands[-1]
            now = time.monotonic()
            if child is None and now >= next_try:
                next_try = now + LEADER_RETRY
                if leadership.acquire():
                    argv = playback_command() if transport is None else transport
                    child = subprocess.Popen(argv, stdin=subprocess.PIPE,
                                             stdout=subprocess.DEVNULL,
                                             stderr=subprocess.DEVNULL,
                                             start_new_session=True, bufsize=0)
                    os.set_blocking(child.stdin.fileno(), False)
                    try:
                        # Bound kernel pipe buffering (~170ms at 12kHz mono s16)
                        # for prompt volume updates and fast wedged-reader detection.
                        fcntl.fcntl(child.stdin.fileno(), getattr(fcntl, 'F_SETPIPE_SZ', 1031), 4096)
                    except OSError:
                        pass
                    pcm = PCM()
                    next_block = now
            if child is not None:
                if exited(child):
                    raise ValueError('audio transport exited before ambience stopped')
                if pending is None and now >= next_block:
                    pending = pcm.render(volume)
                    offset = 0
                    pending_since = now
                    next_block = now + BLOCK_SECONDS
                if pending is not None and now - pending_since >= WRITE_DEADLINE:
                    raise ValueError('audio transport exceeded its PCM write deadline')
            timeout = min(.05, max(0, (next_try if child is None else next_block) - now))
            # Once a block is due but pipe-full, do not spin on the expired clock.
            if pending is not None:
                timeout = .05
            _, writable, _ = select.select(
                [control_fd], [child.stdin.fileno()] if pending is not None else [],
                [], timeout)
            if writable:
                try:
                    written = os.write(child.stdin.fileno(), memoryview(pending)[offset:])
                except BlockingIOError:
                    continue
                if written <= 0:
                    raise ValueError('audio transport refused PCM bytes')
                offset += written
                if offset == len(pending):
                    pending = None
        return 0
    except (OSError, ValueError) as error:
        message = ('Omarchasaurus ambience: ' + diagnostic(error)).encode('utf-8')[:MAX_DIAGNOSTIC]
        try:
            os.write(1, message + b'\n')
        except OSError:
            pass
        return 1
    finally:
        # Keep the lock until the entire owned transport group has been stopped.
        try:
            if child is not None:
                try:
                    child.stdin.close()
                finally:
                    finish_group(child, grace=.2)
        finally:
            if leadership is not None:
                leadership.close()
            for sig, handler in handlers.items():
                signal.signal(sig, handler)


class AmbientAudio:
    """Renderer lifecycle adapter; failure never stops visuals or retries noisily."""
    def __init__(self, report=None, worker_command=None):
        self.report = report if report is not None else lambda text: print(text, file=sys.stderr)
        self.worker_command = worker_command
        self.child = None
        self.attempted = False
        self.sent_volume = None
        self.command_since = None
        self.message = bytearray()

    def _drain(self):
        if self.child is None:
            return
        remaining = MAX_DIAGNOSTIC - len(self.message)
        if remaining:
            try:
                data = os.read(self.child.stdout.fileno(), remaining)
            except BlockingIOError:
                return
            self.message.extend(data)

    def _close_child(self):
        child, self.child = self.child, None
        if child is None:
            return
        try:
            child.stdin.close()
        finally:
            try:
                # Worker cleanup takes at most .2s; leave room for scheduling.
                finish_group(child, grace=.7)
            finally:
                child.stdout.close()
        self.sent_volume = None
        self.command_since = None

    def _failure(self, message):
        self._close_child()
        self.report(diagnostic(message))

    def update(self, settings):
        enabled = settings.get('enabled', False)
        raw_volume = settings.get('volume', 20)
        if (isinstance(raw_volume, bool) or not isinstance(raw_volume, (int, float))
                or not math.isfinite(raw_volume) or not 0 <= raw_volume <= 100):
            raise ValueError('ambience volume must be a finite number in 0..100')
        volume = checked_volume(round(raw_volume))
        if not enabled or volume == 0:
            self.close()
            return
        self._drain()
        if self.child is not None and exited(self.child):
            self._drain()
            message = self.message.decode('utf-8', errors='replace').strip()
            self._failure(message or 'Omarchasaurus ambience: audio worker exited unexpectedly')
            return
        if self.child is None:
            if self.attempted:
                return
            self.attempted = True
            self.message.clear()
            command = self.worker_command
            if command is None:
                command = [sys.executable, str(Path(__file__).resolve()), str(volume)]
            try:
                self.child = subprocess.Popen(command, stdin=subprocess.PIPE,
                                              stdout=subprocess.PIPE,
                                              stderr=subprocess.DEVNULL,
                                              start_new_session=True, bufsize=0)
                os.set_blocking(self.child.stdin.fileno(), False)
                os.set_blocking(self.child.stdout.fileno(), False)
            except OSError as error:
                self._failure('Omarchasaurus ambience: cannot start audio worker: ' + diagnostic(error))
                return
            self.sent_volume = None
        if self.sent_volume != volume:
            try:
                os.write(self.child.stdin.fileno(), bytes([volume]))
            except BlockingIOError:
                now = time.monotonic()
                if self.command_since is None:
                    self.command_since = now
                elif now - self.command_since >= WRITE_DEADLINE:
                    self._failure('Omarchasaurus ambience: audio control exceeded its deadline')
                return
            except OSError:
                self._drain()
                self._failure(self.message.decode('utf-8', errors='replace').strip()
                              or 'Omarchasaurus ambience: audio control pipe failed')
                return
            self.sent_volume = volume
            self.command_since = None

    def close(self):
        self._close_child()
        self.attempted = False
        self.message.clear()


if __name__ == '__main__':
    if len(sys.argv) != 2 or not sys.argv[1].isascii() or not sys.argv[1].isdigit() or len(sys.argv[1]) > 3:
        raise SystemExit('ambience worker requires a volume in 0..100')
    raise SystemExit(run_worker(checked_volume(int(sys.argv[1]))))
