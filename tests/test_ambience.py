from pathlib import Path
import math
import os
import signal
import statistics
import struct
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from ambience import (AmbientAudio, BLOCK_BYTES, FRAMES, Leadership, PCM, RATE,
                      WRITE_DEADLINE)
from bounded_process import finish_group


def samples(raw):
    return [item[0] for item in struct.iter_unpack('=h', raw)]


def rms(raw):
    return math.sqrt(statistics.mean(value * value for value in samples(raw)))


def alive(pid):
    try:
        return Path(f'/proc/{pid}/stat').read_text().split(') ', 1)[1][0] != 'Z'
    except FileNotFoundError:
        return False


class PCMBehaviour(unittest.TestCase):
    def test_fixed_rate_size_and_deterministic_private_rng(self):
        first, second = PCM(71), PCM(71)
        self.assertEqual(RATE, 12000)
        self.assertEqual(FRAMES, 600)
        for _ in range(20):
            block = first.render(20)
            self.assertEqual(len(block), BLOCK_BYTES)
            self.assertEqual(block, second.render(20))

    def test_silence_and_linear_volume_with_gentle_finite_bounds(self):
        loud, quiet, silent = PCM(31), PCM(31), PCM(31)
        high = bytearray()
        low = bytearray()
        for _ in range(100):
            high.extend(loud.render(100))
            low.extend(quiet.render(20))
            self.assertEqual(silent.render(0), bytes(BLOCK_BYTES))
            self.assertTrue(math.isfinite(loud.wind))
            self.assertTrue(math.isfinite(loud.water))
        self.assertGreater(rms(high), 100)
        self.assertLess(rms(high), 5000)
        self.assertGreater(rms(low), 10)
        self.assertAlmostEqual(rms(low) / rms(high), .2, delta=.01)
        self.assertLessEqual(max(map(abs, samples(high))), int(.45 * 32767))
        self.assertLessEqual(max(map(abs, samples(low))), int(.3 * 32767))

    def test_noninteger_and_out_of_range_levels_are_rejected(self):
        for value in (True, False, -1, 101, .5, float('inf'), float('nan'), '20', None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                PCM(1).render(value)


class PrivateRuntime(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='omarchasaurus-audio-test-')
        self.root = Path(self.temporary.name)
        self.runtime = self.root / 'runtime'
        self.runtime.mkdir(mode=0o700)
        self.children = []
        self.audio = []
        self.leaders = []
        self.owned_groups = []
        self.count = 0

    def tearDown(self):
        for audio in self.audio:
            audio.close()
        for child in self.children:
            if child.returncode is None:
                finish_group(child, grace=.7)
            if child.stdin is not None:
                child.stdin.close()
            if child.stdout is not None:
                child.stdout.close()
        for pid in self.owned_groups:
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        for leader in self.leaders:
            leader.close()
        self.temporary.cleanup()

    def wait_for(self, predicate, timeout=4):
        deadline = time.monotonic() + timeout
        while not predicate():
            self.assertLess(time.monotonic(), deadline, 'private audio state missed deadline')
            time.sleep(.01)

    def leader(self, runtime=None):
        leader = Leadership(self.runtime if runtime is None else runtime)
        self.leaders.append(leader)
        return leader

    def recorder(self, stderr_bytes=0):
        self.count += 1
        record = self.root / f'pcm-{self.count}'
        pidfile = self.root / f'transport-{self.count}.pid'
        code = (
            'import os\n'
            f'open({str(pidfile)!r}, "w").write(str(os.getpid()))\n'
            f'os.write(2, b"PRIVATE TRANSPORT DIAGNOSTIC" * {stderr_bytes // 28})\n'
            f'output = open({str(record)!r}, "ab", buffering=0)\n'
            'while True:\n'
            ' data = os.read(0, 4096)\n'
            ' if not data: break\n'
            ' output.write(data)\n'
        )
        return [sys.executable, '-u', '-c', code], record, pidfile

    def worker_command(self, transport, volume=20, prelude=''):
        code = (f'import sys; sys.path.insert(0, {str(ROOT / "scripts")!r}); '
                'from ambience import run_worker; ' + prelude +
                f'raise SystemExit(run_worker({volume}, transport={transport!r}, '
                f'runtime={str(self.runtime)!r}))')
        return [sys.executable, '-u', '-c', code]

    def worker(self, transport, volume=20, prelude=''):
        child = subprocess.Popen(self.worker_command(transport, volume, prelude),
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, start_new_session=True,
                                 bufsize=0)
        self.children.append(child)
        return child

    def controller(self, transport, reports):
        audio = AmbientAudio(report=reports.append,
                             worker_command=self.worker_command(transport))
        self.audio.append(audio)
        return audio

    def wait_pcm(self, record, blocks=3):
        self.wait_for(lambda: record.exists() and record.stat().st_size >= BLOCK_BYTES * blocks)

    def stopped(self, pid):
        self.wait_for(lambda: not alive(pid))

    def test_lock_has_single_leader_and_transfers_after_close_without_unlink(self):
        first, second = self.leader(), self.leader()
        self.assertTrue(first.acquire())
        self.assertFalse(second.acquire())
        path = self.runtime / 'omarchasaurus-terminal' / 'audio.lock'
        inode = path.stat().st_ino
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        first.close()
        self.assertTrue(second.acquire())
        self.assertEqual(path.stat().st_ino, inode)

    def test_no_runtime_fallback_and_rejects_nonprivate_or_symlink_ancestry(self):
        with self.assertRaisesRegex(ValueError, 'absolute'):
            self.leader('relative-runtime')
        link = self.root / 'runtime-link'
        link.symlink_to(self.runtime, target_is_directory=True)
        with self.assertRaises(OSError):
            self.leader(link)
        self.runtime.chmod(0o755)
        with self.assertRaises(ValueError):
            self.leader()

    def test_hostile_lock_leaves_are_rejected_without_opening_targets(self):
        directory = self.runtime / 'omarchasaurus-terminal'
        directory.mkdir(mode=0o700)
        lock = directory / 'audio.lock'
        target = self.root / 'target'
        target.write_bytes(b'untouched')
        target.chmod(0o600)
        lock.symlink_to(target)
        with self.assertRaises(OSError):
            self.leader()
        self.assertEqual(target.read_bytes(), b'untouched')
        lock.unlink()
        os.mkfifo(lock, 0o600)
        with self.assertRaises(ValueError):
            self.leader()
        lock.unlink()
        os.link(target, lock)
        with self.assertRaises(ValueError):
            self.leader()
        lock.unlink()
        lock.write_bytes(b'')
        lock.chmod(0o644)
        with self.assertRaises(ValueError):
            self.leader()

    def test_two_actual_workers_share_one_stream_and_standby_takes_over(self):
        command_a, record_a, pid_a = self.recorder()
        command_b, record_b, pid_b = self.recorder()
        first = self.worker(command_a)
        self.wait_pcm(record_a)
        second = self.worker(command_b)
        time.sleep(.15)
        self.assertFalse(record_b.exists())
        self.assertIsNone(second.poll())
        first.stdin.close()
        self.assertEqual(first.wait(timeout=2), 0)
        self.stopped(int(pid_a.read_text()))
        self.wait_pcm(record_b)
        self.assertIsNone(second.poll())
        self.assertNotEqual(int(pid_a.read_text()), int(pid_b.read_text()))
        second.stdin.close()
        self.assertEqual(second.wait(timeout=2), 0)
        self.stopped(int(pid_b.read_text()))
        self.assertEqual(first.stdout.read(512), b'')
        self.assertEqual(second.stdout.read(512), b'')

    def test_live_volume_and_zero_produce_actual_pcm_not_control_echoes(self):
        command, record, pidfile = self.recorder()
        child = self.worker(command, 100)
        self.wait_pcm(record, 8)
        high = record.read_bytes()[-BLOCK_BYTES * 6:]
        child.stdin.write(bytes([20]))
        baseline = record.stat().st_size
        self.wait_for(lambda: record.stat().st_size >= baseline + BLOCK_BYTES * 8)
        low = record.read_bytes()[-BLOCK_BYTES * 6:]
        self.assertGreater(rms(high), rms(low) * 2)
        child.stdin.write(bytes([0]))
        baseline = record.stat().st_size
        self.wait_for(lambda: record.stat().st_size >= baseline + BLOCK_BYTES * 4)
        self.assertEqual(record.read_bytes()[-BLOCK_BYTES * 2:], bytes(BLOCK_BYTES * 2))
        child.stdin.close()
        self.assertEqual(child.wait(timeout=2), 0)
        self.stopped(int(pidfile.read_text()))

    def test_live_disable_and_zero_stop_transport_and_release_lock(self):
        for disabled in ({'enabled': False, 'volume': 20}, {'enabled': True, 'volume': 0}):
            with self.subTest(settings=disabled):
                command, record, pidfile = self.recorder()
                reports = []
                audio = self.controller(command, reports)
                audio.update({'enabled': True, 'volume': 20})
                self.wait_pcm(record)
                worker = audio.child
                transport_pid = int(pidfile.read_text())
                audio.update(disabled)
                self.assertIsNone(audio.child)
                self.assertIsNotNone(worker.returncode)
                self.stopped(transport_pid)
                with_leadership = self.leader()
                self.assertTrue(with_leadership.acquire())
                with_leadership.close()
                self.assertEqual(reports, [])

    def test_transport_stderr_is_discarded_and_does_not_block_audio(self):
        command, record, pidfile = self.recorder(stderr_bytes=1024 * 1024)
        reports = []
        audio = self.controller(command, reports)
        audio.update({'enabled': True, 'volume': 20})
        self.wait_pcm(record)
        audio.update({'enabled': True, 'volume': 20})
        self.assertEqual(reports, [])
        audio.close()
        self.stopped(int(pidfile.read_text()))

    def test_blocked_writer_has_absolute_deadline_and_releases_leadership(self):
        pidfile = self.root / 'blocked.pid'
        code = ('import os,signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); '
                f'open({str(pidfile)!r}, "w").write(str(os.getpid())); time.sleep(30)')
        started = time.monotonic()
        child = self.worker([sys.executable, '-c', code])
        self.assertEqual(child.wait(timeout=4), 1)
        elapsed = time.monotonic() - started
        self.assertGreater(elapsed, WRITE_DEADLINE)
        self.assertLess(elapsed, 3)
        self.assertIn(b'write deadline', child.stdout.read(512))
        self.stopped(int(pidfile.read_text()))
        self.assertTrue(self.leader().acquire())

    def test_exited_transport_leader_does_not_leave_owned_descendants(self):
        pidfile = self.root / 'descendant.pid'
        code = (
            'import os,signal,time\n'
            'reader,writer=os.pipe()\n'
            'pid=os.fork()\n'
            'if pid:\n'
            ' os.close(writer); os.read(reader,1); os._exit(0)\n'
            'os.close(reader)\n'
            'signal.signal(signal.SIGTERM, signal.SIG_IGN)\n'
            f'open({str(pidfile)!r}, "w").write(str(os.getpid()))\n'
            'os.write(writer,b"R"); os.close(writer); time.sleep(30)\n'
        )
        child = self.worker([sys.executable, '-c', code])
        self.assertEqual(child.wait(timeout=3), 1)
        self.assertIn(b'transport exited', child.stdout.read(512))
        self.stopped(int(pidfile.read_text()))
        self.assertTrue(self.leader().acquire())

    def test_missing_tool_reports_once_until_explicit_disable_reenable(self):
        reports = []
        empty_path = self.root / 'empty-bin'
        empty_path.mkdir(mode=0o700)
        prelude = f'import os; os.environ["PATH"]={str(empty_path)!r}; '
        audio = AmbientAudio(report=reports.append,
                             worker_command=self.worker_command(None, prelude=prelude))
        self.audio.append(audio)
        enabled = {'enabled': True, 'volume': 20}
        audio.update(enabled)
        self.wait_for(lambda: (audio.update(enabled), bool(reports))[1])
        for _ in range(20):
            audio.update(enabled)
        self.assertEqual(len(reports), 1)
        self.assertIn('pw-cat is unavailable', reports[0])
        self.assertLessEqual(len(reports[0]), 384)
        audio.update({'enabled': False, 'volume': 20})
        command, record, _ = self.recorder()
        audio.worker_command = self.worker_command(command)
        audio.update(enabled)
        self.wait_pcm(record)
        self.assertEqual(len(reports), 1)

    def test_unsafe_runtime_is_explicit_and_does_not_retry_or_start_transport(self):
        command, record, _ = self.recorder()
        reports = []
        audio = self.controller(command, reports)
        self.runtime.chmod(0o777)
        enabled = {'enabled': True, 'volume': 20}
        audio.update(enabled)
        self.wait_for(lambda: (audio.update(enabled), bool(reports))[1])
        for _ in range(20):
            audio.update(enabled)
        self.assertEqual(len(reports), 1)
        self.assertIn('unsafe directory', reports[0])
        self.assertFalse(record.exists())

    def test_sigterm_cleanup_stops_actual_transport_before_lock_transfer(self):
        command, record, pidfile = self.recorder()
        child = self.worker(command)
        self.wait_pcm(record)
        child.terminate()
        self.assertEqual(child.wait(timeout=2), 0)
        self.stopped(int(pidfile.read_text()))
        self.assertTrue(self.leader().acquire())

    def test_renderer_sigkill_closes_control_pipe_and_worker_reaps_audio(self):
        command, record, pidfile = self.recorder()
        worker_command = self.worker_command(command)
        worker_pidfile = self.root / 'worker.pid'
        code = (
            f'import sys,time; sys.path.insert(0,{str(ROOT / "scripts")!r}); '
            'from ambience import AmbientAudio; '
            f'audio=AmbientAudio(worker_command={worker_command!r}); '
            'settings={"enabled":True,"volume":20}; audio.update(settings); '
            f'open({str(worker_pidfile)!r},"w").write(str(audio.child.pid))\n'
            'while True: audio.update(settings); time.sleep(.02)\n'
        )
        renderer = subprocess.Popen([sys.executable, '-u', '-c', code],
                                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, start_new_session=True)
        self.children.append(renderer)
        self.wait_pcm(record)
        worker_pid = int(worker_pidfile.read_text())
        self.owned_groups.append(worker_pid)
        transport_pid = int(pidfile.read_text())
        renderer.kill()
        renderer.wait(timeout=2)
        self.stopped(worker_pid)
        self.stopped(transport_pid)
        self.assertTrue(self.leader().acquire())
