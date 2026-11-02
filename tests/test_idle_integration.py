"""Private desktop transports only: these tests never invoke the user's shell."""
import fcntl
import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import idle_integration as idle
from safe_io import Directory

HOST = '''import os, sys
from pathlib import Path
root = Path(os.environ['FIXTURE_ROOT'])
if sys.argv[1:] == ['idle', 'status']:
    sys.stdout.write((root / 'host-status').read_text())
elif sys.argv[1:] == ['lock', 'isLocked']:
    sys.stdout.write((root / 'host-lock').read_text())
else:
    raise SystemExit(2)
'''


class IdleIntegration(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='omarchasaurus-idle-test-')
        self.root = Path(self.temporary.name)
        self.home = self.root / 'home'
        self.home.mkdir(mode=0o700)
        self.config = self.root / 'config'
        (self.config / 'omarchasaurus').mkdir(parents=True, mode=0o700)
        self.settings = self.config / 'omarchasaurus/settings.json'
        self.settings.write_text('{"integration":{"idleEnabled":true}}')
        self.bin = self.root / 'bin'
        self.bin.mkdir(mode=0o700)
        host = self.bin / 'omarchy-shell'
        host.write_text('#!' + sys.executable + '\n' + HOST)
        host.chmod(0o700)
        self.plugin = self.root / 'plugin'
        scripts = self.plugin / 'scripts'
        scripts.mkdir(parents=True, mode=0o700)
        for name in ('idle_integration.py', 'configuration.py', 'safe_io.py', 'bounded_process.py'):
            shutil.copyfile(ROOT / 'scripts' / name, scripts / name)
        self.script = scripts / 'idle_integration.py'
        self.env = os.environ | {'HOME': str(self.home), 'PATH': str(self.bin),
                                 'XDG_CONFIG_HOME': str(self.config),
                                 'XDG_STATE_HOME': str(self.root / 'ignored-state'),
                                 'XDG_RUNTIME_DIR': str(self.root / 'runtime'),
                                 'FIXTURE_ROOT': str(self.root), 'PYTHONDONTWRITEBYTECODE': '1'}
        self.environment = patch.dict(os.environ, self.env, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.addCleanup(self.temporary.cleanup)
        self.processes = []
        self.addCleanup(self.stop_processes)
        self.host = dict(enabled=True, stayAwake=False, stayAwakeStateLoaded=True,
                         screensaver=150, screensaverWindows=0)
        self.set_host()
        self.toggle = self.home / '.local/state/omarchy/toggles/screensaver-off'
        self.ownership = self.home / '.local/state/omarchasaurus'
        self.record = self.ownership / idle.RECORD

    def set_host(self, lock='false', **changes):
        (self.root / 'host-status').write_text(json.dumps(self.host | changes))
        (self.root / 'host-lock').write_text(lock)

    def command(self, command='status'):
        return subprocess.run([sys.executable, str(self.script), command], env=self.env,
                              capture_output=True, text=True, timeout=5)

    def status(self):
        result = self.command()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLessEqual(len(result.stdout.encode()), 4096)
        value = json.loads(result.stdout)
        self.assertEqual(set(value), {'version', 'owned', 'eligible', 'timeout',
                                     'keepAwake', 'locked', 'reason'})
        self.assertLessEqual(len(value['reason']), 240)
        return value

    def wait_for(self, predicate):
        deadline = time.monotonic() + 5
        while not predicate():
            self.assertLess(time.monotonic(), deadline, 'idle lifecycle transition timed out')
            time.sleep(.02)

    def start(self):
        child = subprocess.Popen([sys.executable, str(self.script), 'lease'], env=self.env,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.processes.append(child)
        with selectors.DefaultSelector() as selector:
            selector.register(child.stdout, selectors.EVENT_READ)
            self.assertTrue(selector.select(5), 'lease did not report readiness')
        self.assertEqual(child.stdout.readline(), 'owned\n')
        return child

    def stop_processes(self):
        for child in self.processes:
            if child.poll() is None:
                child.terminate()
            try:
                child.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.communicate(timeout=5)

    def test_absent_status_is_read_only_and_uses_home_not_xdg_state(self):
        before = sorted(str(p.relative_to(self.root)) for p in self.root.rglob('*'))
        value = self.status()
        self.assertFalse(value['owned'])
        self.assertFalse(value['eligible'])
        self.assertEqual(value['timeout'], 150)
        self.assertEqual(before, sorted(str(p.relative_to(self.root)) for p in self.root.rglob('*')))
        self.assertFalse((self.root / 'ignored-state').exists())
        self.settings.unlink()
        missing_settings = self.status()
        self.assertFalse(missing_settings['owned'])
        self.assertFalse(missing_settings['eligible'])
        self.assertIn('Enable automatic idle activation', missing_settings['reason'])
        self.toggle.parent.mkdir(parents=True, mode=0o755)
        self.toggle.write_text('')
        self.toggle.chmod(0o644)
        stock_disabled = self.status()
        self.assertFalse(stock_disabled['owned'])
        self.assertFalse(stock_disabled['eligible'])
        self.assertIn('disabled by the user or another saver', stock_disabled['reason'])

    def test_lease_requires_persisted_explicit_true(self):
        for document in ({}, {'integration': {'idleEnabled': False}},
                         {'integration': {'idleEnabled': 1}}, {'integration': []}):
            self.settings.write_text(json.dumps(document))
            result = self.command('lease')
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn('owned\n', result.stdout)
            self.assertIn('idleEnabled=true', result.stderr)
            self.assertFalse(self.toggle.exists())

    def test_live_lease_status_concurrent_exclusion_and_term_release(self):
        child = self.start()
        self.assertTrue(self.status()['eligible'])
        self.assertEqual(json.loads(self.toggle.read_text()), json.loads(self.record.read_text()))
        self.assertEqual(self.toggle.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.ownership.stat().st_mode & 0o777, 0o700)
        duplicate = self.command('lease')
        self.assertNotEqual(duplicate.returncode, 0)
        self.assertNotIn('owned\n', duplicate.stdout)
        self.assertTrue(self.status()['eligible'])
        child.terminate()
        output, errors = child.communicate(timeout=5)
        self.assertEqual(child.returncode, 0, errors)
        self.assertLess(len(output.encode()), 2048)
        self.assertFalse(self.toggle.exists())
        self.assertFalse(self.record.exists())
        with (self.ownership / idle.LOCK).open('rb') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_foreign_marker_kinds_are_never_claimed_or_removed(self):
        self.toggle.parent.mkdir(parents=True, mode=0o700)
        victim = self.root / 'victim'
        victim.write_text('foreign')
        for kind in ('regular', 'symlink', 'hardlink', 'fifo', 'directory'):
            with self.subTest(kind=kind):
                if kind == 'symlink':
                    self.toggle.symlink_to(victim)
                elif kind == 'hardlink':
                    os.link(victim, self.toggle)
                elif kind == 'fifo':
                    os.mkfifo(self.toggle, 0o600)
                elif kind == 'directory':
                    self.toggle.mkdir(mode=0o700)
                else:
                    self.toggle.write_text('foreign')
                original = self.toggle.lstat()
                self.assertFalse(self.status()['eligible'])
                result = self.command('lease')
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.toggle.lstat().st_ino, original.st_ino)
                self.assertEqual(victim.read_text(), 'foreign')
                self.assertFalse(self.record.exists())
                self.toggle.rmdir() if kind == 'directory' else self.toggle.unlink()

    def test_stale_matching_pair_is_not_a_live_lease_or_reclaimed(self):
        self.toggle.parent.mkdir(parents=True, mode=0o700)
        self.ownership.mkdir(mode=0o700)
        with Directory.open(self.toggle.parent) as directory, Directory.open(self.ownership, private=True) as ownership:
            lease = idle.Lease(directory, ownership)
            lease.acquire()
            for _, _, fd, _ in lease.files:
                os.close(fd)
            lease.files.clear()
            os.close(lease.lock)
            lease.lock = None
        before = self.toggle.read_bytes()
        value = self.status()
        self.assertFalse(value['eligible'])
        self.assertIn('Stale', value['reason'])
        self.assertNotEqual(self.command('lease').returncode, 0)
        self.assertEqual(self.toggle.read_bytes(), before)

    def test_replaced_marker_or_record_survives_automatic_release(self):
        for path in (self.toggle, self.record):
            with self.subTest(path=path.name):
                child = self.start()
                replacement = self.root / 'replacement'
                replacement.write_text('foreign replacement')
                replacement.chmod(0o600)
                replacement.replace(path)
                child.communicate(timeout=5)
                self.assertEqual(path.read_text(), 'foreign replacement')
                other = self.record if path == self.toggle else self.toggle
                self.assertFalse(other.exists())
                path.unlink()

    def test_parent_sigkill_closed_pipes_still_releases_owned_markers(self):
        child = self.start()
        child.kill()
        child.wait(timeout=5)
        child.stdout.close()
        child.stderr.close()
        self.wait_for(lambda: not self.toggle.exists() and not self.record.exists())

    def test_ui_parent_death_not_only_direct_guardian_kill_releases(self):
        wrapper = subprocess.Popen([sys.executable, '-c',
            'import subprocess,sys,time; subprocess.Popen([sys.executable,sys.argv[1],"lease"]); time.sleep(30)',
            str(self.script)], env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.processes.append(wrapper)
        self.wait_for(self.toggle.exists)
        wrapper.kill()
        wrapper.wait(timeout=5)
        self.wait_for(lambda: not self.toggle.exists() and not self.record.exists())
        wrapper.communicate(timeout=5)

    def test_source_deletion_needs_no_modules_from_deleted_tree_to_release(self):
        child = self.start()
        shutil.rmtree(self.plugin)
        child.communicate(timeout=5)
        self.assertEqual(child.returncode, 0)
        self.assertFalse(self.toggle.exists())
        self.assertFalse(self.record.exists())

    def test_disabled_saved_preference_releases_without_ui_assistance(self):
        child = self.start()
        self.settings.write_text('{"integration":{"idleEnabled":false}}')
        child.communicate(timeout=5)
        self.assertFalse(self.toggle.exists())
        self.assertFalse(self.record.exists())

    def test_host_policy_fail_closed_for_disabled_zero_keepawake_lock_and_bad_types(self):
        self.start()
        for changes in ({'enabled': False}, {'screensaver': 0}, {'stayAwake': True},
                        {'stayAwakeStateLoaded': False}, {'screensaver': True},
                        {'screensaver': -1}, {'screensaverWindows': '0'}, {'enabled': 1}):
            with self.subTest(changes=changes):
                self.set_host(**changes)
                self.assertFalse(self.status()['eligible'])
        for lock in ('true', 'TRUE', '{}', ''):
            self.set_host(lock=lock)
            self.assertFalse(self.status()['eligible'])
        self.set_host()
        indicators = self.home / '.local/state/omarchy/indicators'
        indicators.mkdir(mode=0o700)
        (indicators / 'stay-awake').write_text('')
        value = self.status()
        self.assertTrue(value['keepAwake'])
        self.assertFalse(value['eligible'])
        (indicators / 'stay-awake').unlink()
        (self.root / 'host-status').write_text('{malformed')
        self.assertFalse(self.status()['eligible'])
        (self.root / 'host-status').write_text('x' * 16385)
        self.assertFalse(self.status()['eligible'])

    def test_unsafe_ownership_parents_and_lock_types_leave_stock_unchanged(self):
        self.ownership.parent.mkdir(parents=True, mode=0o700)
        victim = self.root / 'victim-directory'
        victim.mkdir(mode=0o700)
        self.ownership.symlink_to(victim)
        self.assertNotEqual(self.command('lease').returncode, 0)
        self.assertFalse(self.toggle.exists())
        self.assertEqual(list(victim.iterdir()), [])
        self.ownership.unlink()
        self.ownership.mkdir(mode=0o700)
        self.ownership.chmod(0o777)
        self.assertNotEqual(self.command('lease').returncode, 0)
        self.assertFalse(self.toggle.exists())
        self.ownership.chmod(0o700)
        lock = self.ownership / idle.LOCK
        for kind in ('fifo', 'symlink', 'hardlink', 'permissions'):
            with self.subTest(kind=kind):
                target = self.root / 'lock-target'
                target.write_text('')
                target.chmod(0o600)
                if kind == 'fifo':
                    os.mkfifo(lock, 0o600)
                elif kind == 'symlink':
                    lock.symlink_to(target)
                elif kind == 'hardlink':
                    os.link(target, lock)
                else:
                    lock.write_text('')
                    lock.chmod(0o666)
                self.assertNotEqual(self.command('lease').returncode, 0)
                self.assertFalse(self.toggle.exists())
                self.assertFalse(self.record.exists())
                lock.unlink()

    def test_partial_acquire_failure_removes_only_created_record(self):
        self.toggle.parent.mkdir(parents=True, mode=0o700)
        self.ownership.mkdir(mode=0o700)
        original = idle.open_file
        def fail_marker(directory_fd, name, *args, **kwargs):
            if name == idle.TOGGLE:
                raise OSError('fixture publish failure')
            return original(directory_fd, name, *args, **kwargs)
        with Directory.open(self.toggle.parent) as directory, Directory.open(self.ownership, private=True) as ownership:
            lease = idle.Lease(directory, ownership)
            try:
                with patch.object(idle, 'open_file', side_effect=fail_marker):
                    with self.assertRaises(OSError):
                        lease.acquire()
            finally:
                lease.release()
        self.assertFalse(self.toggle.exists())
        self.assertFalse(self.record.exists())
