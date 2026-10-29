import fcntl
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import socket
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / 'scripts/launch-dinosaurs'

# These replace external desktop processes, not the coordinator under test.
# PATH contains only this private bin directory: no real window can be opened.
TERMINAL = '''from pathlib import Path
import json, os, sys, time
root = Path(os.environ['FIXTURE_ROOT'])
output = sys.argv[sys.argv.index('--output') + 1]
session = Path(sys.argv[sys.argv.index('--session-dir') + 1])
token = json.loads((session / 'authority.json').read_text())['token']
record = root / ('child-' + output + '.json')
temporary = record.with_suffix('.tmp')
temporary.write_text(json.dumps({'pid': os.getpid(), 'output': output}))
temporary.replace(record)
while not (root / ('exit-' + output)).exists():
    if (root / 'dismiss').exists() and not (session / 'dismissed.json').exists():
        fd = os.open(session / 'dismissed.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump({'token': token}, stream)
    time.sleep(.02)
'''

COMPOSITOR = '''from pathlib import Path
import json, os, sys
root = Path(os.environ['FIXTURE_ROOT'])
if sys.argv[1] == 'monitors':
    print(json.dumps([{'name': 'FIX-A', 'focused': True}, {'name': 'FIX-B'}]))
elif sys.argv[1] == 'clients':
    records = [json.loads(path.read_text()) for path in root.glob('child-*.json')]
    print(json.dumps([{'pid': item['pid'], 'address': hex(item['pid'])} for item in records]))
else:
    request = ' '.join(sys.argv[2:])
    failure = os.environ.get('FIXTURE_FAILURE')
    terminal = root / 'bin/ghostty'
    good = (root / 'terminal-source').read_text()
    if failure and 'monitor = "FIX-A"' in request:
        if failure == 'command':
            terminal.chmod(0o600)
        else:
            terminal.write_text('#!/nonexistent-omarchasaurus-test-interpreter\\n')
            terminal.chmod(0o700)
    elif failure and 'monitor = "FIX-B"' in request:
        if terminal.read_text() != good:
            terminal.write_text(good)
        terminal.chmod(0o700)
    print('ok')
'''


class LauncherReleaseLayout(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='omarchasaurus-release-test-')
        self.root = Path(self.temporary.name)
        self.plugin = self.root / 'plugin'
        scripts = self.plugin / 'scripts'
        scripts.mkdir(parents=True, mode=0o700)
        for name in ('launch-dinosaurs', 'event_preview.py', 'bounded_process.py',
                     'safe_io.py', 'session_control.py'):
            shutil.copyfile(ROOT / 'scripts' / name, scripts / name)
        self.launcher = scripts / 'launch-dinosaurs'
        self.bin = self.root / 'bin'
        self.bin.mkdir(mode=0o700)
        quickshell = self.bin / 'quickshell'
        quickshell.write_text(
            '#!' + sys.executable + '\nimport json, os, sys\n'
            'if sys.argv[1] == "list": print(os.environ.get("FIXTURE_INSTANCES", "[]"))\n'
            'else: print(json.dumps(sys.argv[1:]))\n')
        quickshell.chmod(0o700)
        runtime = self.root / 'runtime'
        runtime.mkdir(mode=0o700)
        self.environment = os.environ | {
            'PATH': str(self.bin), 'XDG_CONFIG_HOME': str(self.root / 'config'),
            'XDG_RUNTIME_DIR': str(runtime),
        }
        self.manifest = {
            'schemaVersion': 1, 'id': 'dailen.omarchasaurus', 'version': '0.2.0',
            'kinds': ['service', 'overlay'], 'keepLoaded': False,
            'entryPoints': {'service': 'qml/0.2.0/Service.qml', 'overlay': 'qml/0.2.0/Config.qml'},
        }
        self.release('0.2.0')
        self.write_manifest()

    def tearDown(self):
        self.temporary.cleanup()

    def release(self, version):
        directory = self.plugin / 'qml' / version
        directory.mkdir(parents=True, mode=0o700)
        for name in ('Service.qml', 'Config.qml', 'Settings.qml'):
            (directory / name).write_text('import QtQuick\nItem {}\n')
        return directory

    def write_manifest(self):
        (self.plugin / 'manifest.json').write_text(json.dumps(self.manifest))

    def command(self, command='configure', **environment):
        return subprocess.run(
            [sys.executable, str(self.launcher), command],
            env=self.environment | environment, capture_output=True, text=True, timeout=6)

    def test_standalone_discovers_current_release_without_creating_user_state(self):
        result = self.command()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout),
                         ['--no-duplicate', '--path', str(self.plugin / 'qml/0.2.0/Settings.qml')])
        self.assertFalse((self.root / 'config').exists())
        self.assertEqual(list((self.root / 'runtime').iterdir()), [])

    def test_new_manifest_selects_new_standalone_identity_and_existing_instance_ipc(self):
        self.release('0.3.0')
        self.manifest['version'] = '0.3.0'
        self.manifest['entryPoints'] = {
            'service': 'qml/0.3.0/Service.qml', 'overlay': 'qml/0.3.0/Config.qml'}
        self.write_manifest()
        result = self.command(FIXTURE_INSTANCES='[{}]')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [
            'ipc', '--path', str(self.plugin / 'qml/0.3.0/Settings.qml'),
            'call', 'omarchasaurus-control', 'open'])

    def test_manifest_rejects_wrong_identity_schema_and_unversioned_or_traversing_paths(self):
        changes = (
            {'id': 'other.plugin'}, {'schemaVersion': True}, {'version': '../0.2.0'},
            {'version': '00.2.0'}, {'version': '0.3.0'}, {'keepLoaded': True},
            {'kinds': ['overlay']}, {'entryPoints': {'service': 'Service.qml', 'overlay': 'Config.qml'}},
            {'entryPoints': {'service': '/tmp/Service.qml', 'overlay': '../Config.qml'}},
        )
        original = self.manifest.copy()
        for change in changes:
            with self.subTest(change=change):
                self.manifest = original | change
                self.write_manifest()
                result = self.command()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, '')
        self.assertFalse((self.root / 'config').exists())

    def test_unsafe_manifest_files_fail_without_blocking_or_launching(self):
        manifest = self.plugin / 'manifest.json'
        saved = self.root / 'saved-manifest'
        manifest.rename(saved)
        for kind in ('symlink', 'hardlink', 'fifo', 'writable', 'oversized'):
            with self.subTest(kind=kind):
                if kind == 'symlink':
                    manifest.symlink_to(saved)
                elif kind == 'hardlink':
                    os.link(saved, manifest)
                elif kind == 'fifo':
                    os.mkfifo(manifest, 0o600)
                elif kind == 'writable':
                    manifest.write_text(saved.read_text())
                    manifest.chmod(0o666)
                else:
                    manifest.write_text(' ' * 16385)
                result = self.command()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, '')
                manifest.unlink()

    def test_release_symlink_and_unsafe_settings_file_are_rejected(self):
        release = self.plugin / 'qml/0.2.0'
        saved = self.root / 'saved-release'
        release.rename(saved)
        release.symlink_to(saved, target_is_directory=True)
        self.assertNotEqual(self.command().returncode, 0)
        release.unlink()
        saved.rename(release)
        settings = release / 'Settings.qml'
        settings.unlink()
        settings.symlink_to(release / 'Config.qml')
        self.assertNotEqual(self.command().returncode, 0)
        settings.unlink()
        settings.write_text('import QtQuick\nItem {}\n')
        settings.chmod(0o666)
        self.assertNotEqual(self.command().returncode, 0)

    def test_missing_release_never_falls_back_to_obsolete_root_settings(self):
        (self.plugin / 'qml/0.2.0/Settings.qml').unlink()
        (self.plugin / 'Settings.qml').write_text('import QtQuick\nItem {}\n')
        result = self.command()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '')

    def test_stop_and_status_remain_available_without_manifest_or_qml(self):
        (self.plugin / 'manifest.json').unlink()
        shutil.rmtree(self.plugin / 'qml')
        for command in ('stop', 'status'):
            with self.subTest(command=command):
                result = self.command(command)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('No running Omarchasaurus', result.stdout)
        self.assertFalse((self.root / 'config').exists())


class LauncherSessions(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='omarchasaurus-session-test-')
        self.root = Path(self.temporary.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir(mode=0o700)
        runtime = self.root / 'runtime'
        runtime.mkdir(mode=0o700)
        terminal = '#!' + sys.executable + '\n' + TERMINAL
        (self.root / 'terminal-source').write_text(terminal)
        for name, content in (('ghostty', terminal), ('hyprctl', '#!' + sys.executable + '\n' + COMPOSITOR)):
            path = self.bin / name
            path.write_text(content)
            path.chmod(0o700)
        self.environment = os.environ | {
            'PATH': str(self.bin), 'FIXTURE_ROOT': str(self.root),
            'XDG_RUNTIME_DIR': str(runtime), 'XDG_CONFIG_HOME': str(self.root / 'config'),
        }
        self.session_root = runtime / 'omarchasaurus-terminal'
        self.coordinator = None

    def command(self, *arguments):
        return subprocess.run([sys.executable, str(LAUNCHER), *arguments],
                              env=self.environment, capture_output=True, text=True, timeout=6)

    def records(self):
        return [json.loads(path.read_text()) for path in self.root.glob('child-*.json')]

    def wait_for(self, predicate):
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            if predicate():
                return
            if self.coordinator is not None and self.coordinator.poll() is not None:
                self.fail('coordinator exited before the expected lifecycle transition')
            time.sleep(.02)
        self.fail('coordinator lifecycle transition timed out')

    def start(self, count=2, supervised=False):
        options = ['--supervised'] if supervised else []
        self.coordinator = subprocess.Popen(
            [sys.executable, str(LAUNCHER), 'start', *options], env=self.environment,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
        self.wait_for(lambda: len(self.records()) == count)
        self.wait_for(lambda: self.command('status', '--mode', 'start').returncode == 0)
        return {item['output']: item['pid'] for item in self.records()}

    def assert_released(self, pids):
        self.assertFalse((self.session_root / 'start.sock').exists())
        self.assertFalse(any(path.is_dir() for path in self.session_root.iterdir()))
        for pid in pids:
            self.assertFalse(Path(f'/proc/{pid}').exists(), 'owned terminal was not reaped')
        with (self.session_root / 'start.lock').open('rb') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def stop(self, expected=0):
        stopped = self.command('stop', '--mode', 'start')
        self.assertEqual(stopped.returncode, 0, stopped.stderr)
        _, errors = self.coordinator.communicate(timeout=6)
        self.assertEqual(self.coordinator.returncode, expected, errors)

    def tearDown(self):
        try:
            if self.coordinator is not None and self.coordinator.poll() is None:
                try:
                    self.command('stop', '--mode', 'start')
                    self.coordinator.communicate(timeout=6)
                except (OSError, subprocess.SubprocessError):
                    self.coordinator.kill()
                    self.coordinator.communicate()
            # Only signal a leftover process whose command still names our
            # private executable; never trust a recorded PID after reuse.
            for item in self.records():
                try:
                    command = Path(f'/proc/{item["pid"]}/cmdline').read_bytes().split(b'\0')
                    if os.fsencode(self.bin / 'ghostty') in command:
                        os.killpg(item['pid'], signal.SIGKILL)
                except (FileNotFoundError, ProcessLookupError):
                    pass
        finally:
            self.temporary.cleanup()

    def test_status_and_exclusive_ownership_then_stop_reap_all_children(self):
        pids = self.start()
        with (self.session_root / 'start.lock').open('rb') as stream:
            with self.assertRaises(BlockingIOError):
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        duplicate = self.command('start')
        self.assertEqual(duplicate.returncode, 0, duplicate.stderr)
        self.assertEqual({item['pid'] for item in self.records()}, set(pids.values()))
        self.assertTrue(all(Path(f'/proc/{pid}').exists() for pid in pids.values()))
        self.stop()
        self.assert_released(pids.values())

    def test_supervised_stop_waits_for_coordinator_to_reap_every_owned_terminal(self):
        pids = self.start(supervised=True)
        self.stop()
        self.assert_released(pids.values())

    def test_supervised_ui_sigkill_and_closed_pipes_still_reap_owned_terminals(self):
        pids = self.start(supervised=True)
        guardian = self.coordinator.pid
        children = Path(f'/proc/{guardian}/task/{guardian}/children').read_text().split()
        self.assertEqual(len(children), 1)
        cleanup_pid = int(children[0])
        self.coordinator.kill()
        self.coordinator.wait(timeout=6)
        self.coordinator.stdout.close()
        self.coordinator.stderr.close()
        deadline = time.monotonic() + 6
        while True:
            status = Path(f'/proc/{cleanup_pid}/stat')
            if not status.exists():
                break
            try:
                if status.read_text().split(') ', 1)[1][0] == 'Z':
                    break
            except FileNotFoundError:
                break
            self.assertLess(time.monotonic(), deadline, 'cleanup coordinator did not finish after UI death')
            time.sleep(.02)
        self.assert_released(pids.values())

    def test_supervised_flag_is_rejected_outside_owned_session_commands(self):
        result = self.command('stop', '--supervised')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('--supervised is only valid with start or preview', result.stderr)
        self.assertFalse(self.session_root.exists())

    def test_event_requires_preview_without_starting_a_session(self):
        for mode in ('start', 'configure', 'stop', 'status', 'save-settings', 'resolve-settings'):
            with self.subTest(mode=mode):
                result = self.command(mode, '--test-event', 'shower')
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('--test-event is only valid with preview', result.stderr)
        self.assertFalse(self.session_root.exists())

    def test_unknown_event_is_rejected_before_startup(self):
        result = self.command('preview', '--test-event', 'meteor')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('invalid choice', result.stderr)
        self.assertFalse(self.session_root.exists())

    def test_event_refuses_busy_preview_and_explains_surface_first(self):
        self.session_root.mkdir(mode=0o700)
        descriptor = os.open(self.session_root / 'preview.lock', os.O_CREAT | os.O_RDWR, 0o600)
        with os.fdopen(descriptor, 'wb') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.command('preview', '--fullscreen', '--test-event', 'rainbow')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Surface the existing preview first', result.stderr)
            duplicate = self.command('preview')
            self.assertEqual(duplicate.returncode, 0, duplicate.stderr)
            self.assertIn('already running', duplicate.stdout)
        self.assertEqual(self.records(), [])
        self.assertFalse((self.session_root / 'preview.sock').exists())

    def test_one_output_exit_keeps_the_other_owned_output_running(self):
        pids = self.start()
        (self.root / 'exit-FIX-A').touch()
        self.wait_for(lambda: not Path(f'/proc/{pids["FIX-A"]}').exists())
        self.assertTrue(Path(f'/proc/{pids["FIX-B"]}').exists())
        self.assertEqual(self.command('status', '--mode', 'start').returncode, 0)
        self.stop()
        self.assert_released(pids.values())

    def test_authenticated_dismissal_stops_and_reaps_every_output(self):
        pids = self.start()
        (self.root / 'dismiss').touch()
        _, errors = self.coordinator.communicate(timeout=6)
        self.assertEqual(self.coordinator.returncode, 0, errors)
        self.assert_released(pids.values())

    def assert_failed_output_isolated(self, kind):
        self.environment['FIXTURE_FAILURE'] = kind
        pids = self.start(count=1)
        self.assertEqual(set(pids), {'FIX-B'})
        self.assertTrue(Path(f'/proc/{pids["FIX-B"]}').exists())
        self.stop(expected=1)
        self.assert_released(pids.values())

    def test_terminal_selection_failure_does_not_abort_other_outputs(self):
        self.assert_failed_output_isolated('command')

    def test_process_creation_failure_does_not_abort_other_outputs(self):
        self.assert_failed_output_isolated('spawn')


    def test_runtime_nonce_is_not_exposed_in_terminal_arguments(self):
        pids = self.start()
        sessions = [path for path in self.session_root.iterdir() if path.is_dir()]
        self.assertEqual(len(sessions), 1)
        self.assertEqual((self.session_root / 'start.sock').stat().st_mode & 0o777, 0o600)
        authority = sessions[0] / 'authority.json'
        token = json.loads(authority.read_text())['token']
        self.assertEqual(authority.stat().st_mode & 0o777, 0o600)
        for pid in pids.values():
            arguments = Path(f'/proc/{pid}/cmdline').read_bytes()
            self.assertNotIn(b'--session-token', arguments)
            self.assertNotIn(token.encode(), arguments)
        self.stop()
        self.assert_released(pids.values())

    def test_slow_control_clients_cannot_delay_signal_shutdown_or_accumulate_descriptors(self):
        pids = self.start()
        clients = []
        before = len(os.listdir(f'/proc/{self.coordinator.pid}/fd'))
        try:
            for _ in range(48):
                connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                connection.setblocking(False)
                try:
                    connection.connect(str(self.session_root / 'start.sock'))
                except (BlockingIOError, ConnectionRefusedError):
                    pass
                clients.append(connection)
            time.sleep(.3)
            self.assertLessEqual(len(os.listdir(f'/proc/{self.coordinator.pid}/fd')), before + 16)
            started = time.monotonic()
            self.coordinator.send_signal(signal.SIGTERM)
            _, errors = self.coordinator.communicate(timeout=6)
            self.assertEqual(self.coordinator.returncode, 0, errors)
            self.assertLess(time.monotonic() - started, 4)
            self.assert_released(pids.values())
        finally:
            for connection in clients:
                connection.close()


    def test_compositor_discovery_rejects_overflow_and_bad_shapes_before_launch(self):
        cases = (
            'import os; os.write(1, b\"PRIVATE TITLE\" * 100000)',
            'import os; os.write(2, b\"PRIVATE STDERR\" * 1000)',
            'print(\"{}\")',
            'import json; print(json.dumps([{\"name\":\"FIX-A\"}] * 65))',
            'import json; print(json.dumps([{\"name\":\"FIX-A\", \"specialWorkspace\":[]}]))',
        )
        for code in cases:
            with self.subTest(code=code):
                (self.bin / 'hyprctl').write_text('#!' + sys.executable + '\n' + code + '\n')
                result = self.command('start')
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('PRIVATE', result.stderr)
                self.assertNotIn('Traceback', result.stderr)
                self.assertLess(len(result.stderr), 400)
                self.assertEqual(self.records(), [])
                self.assert_released([])

    def test_configure_discovery_has_a_deadline_without_opening_a_real_app(self):
        executable = self.bin / 'quickshell'
        executable.write_text('#!' + sys.executable + '\nimport time; time.sleep(30)\n')
        executable.chmod(0o700)
        started = time.monotonic()
        result = subprocess.run([sys.executable, str(LAUNCHER), 'configure'], env=self.environment,
                                capture_output=True, text=True, timeout=8)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('deadline', result.stderr)
        self.assertLess(time.monotonic() - started, 7)
        self.assertEqual(self.records(), [])


    def test_runtime_requires_an_absolute_private_owned_directory_without_fallback(self):
        for value in ('', 'relative-runtime', str(self.root / 'unsafe-runtime')):
            with self.subTest(value=value):
                if value.endswith('/unsafe-runtime'):
                    Path(value).mkdir(mode=0o777)
                    Path(value).chmod(0o777)
                self.environment['XDG_RUNTIME_DIR'] = value
                result = self.command('status')
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.session_root.exists())
        self.assertEqual(self.records(), [])

    def test_unsafe_socket_leaf_is_never_deleted_or_followed(self):
        self.session_root.mkdir(mode=0o700)
        victim = self.root / 'victim'
        victim.write_text('unchanged')
        endpoint = self.session_root / 'start.sock'
        endpoint.symlink_to(victim)
        for command in ('start', 'status', 'stop'):
            with self.subTest(command=command):
                result = self.command(command, '--mode', 'start')
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(endpoint.is_symlink())
                self.assertEqual(victim.read_text(), 'unchanged')
        self.assertEqual(self.records(), [])


class SettingsPersistence(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='omarchasaurus-settings-test-')
        self.root = Path(self.temporary.name)
        self.target = self.root / 'omarchasaurus/settings.json'
        self.environment = os.environ | {'XDG_CONFIG_HOME': str(self.root)}

    def tearDown(self):
        self.temporary.cleanup()

    def save(self, document, expected):
        return subprocess.run(
            [sys.executable, str(LAUNCHER), 'save-settings', json.dumps(document),
             '--expected', json.dumps(expected)], env=self.environment,
            capture_output=True, text=True, timeout=6)

    def test_save_preserves_sparse_choices_and_private_permissions(self):
        sparse = {'preset': 'dusk', 'animals': {'pteranodonEnabled': False}}
        result = self.save(sparse, {})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.target.read_text()), sparse)
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o600)
        self.assertFalse(list(self.target.parent.glob('.settings-*')))

    def test_stale_expected_document_cannot_overwrite_an_external_edit(self):
        current = {'scenery': {'cloudDensity': .5}}
        self.assertEqual(self.save(current, {}).returncode, 0)
        before = self.target.read_bytes()
        refused = self.save({'preset': 'dusk'}, {})
        self.assertNotEqual(refused.returncode, 0)
        self.assertEqual(self.target.read_bytes(), before)

    def test_invalid_settings_leave_existing_document_untouched(self):
        current = {'preset': 'dusk'}
        self.assertEqual(self.save(current, {}).returncode, 0)
        before = self.target.read_bytes()
        refused = self.save({'population': {'maxVisible': True}}, current)
        self.assertNotEqual(refused.returncode, 0)
        self.assertEqual(self.target.read_bytes(), before)
        self.assertFalse(list(self.target.parent.glob('.settings-*')))

    def read(self, *extra):
        return subprocess.run([sys.executable, str(LAUNCHER), 'read-settings', *extra],
                              env=self.environment, capture_output=True, text=True, timeout=6)

    def test_read_missing_and_blank_settings_returns_sparse_object_without_creating_paths(self):
        result = self.read()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {})
        self.assertFalse(self.target.parent.exists())
        self.target.parent.mkdir(mode=0o700)
        self.target.write_text(' \t\n')
        self.assertEqual(json.loads(self.read().stdout), {})

    def test_read_rejects_positional_json_without_creating_settings(self):
        result = self.read('{}')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.target.parent.exists())

    def test_ordinary_nonsecret_0644_settings_read_and_save_remain_supported(self):
        self.target.parent.mkdir(mode=0o700)
        current = {'preset': 'dusk'}
        self.target.write_text(json.dumps(current))
        self.target.chmod(0o644)
        result = self.read()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), current)
        result = self.save({'seed': 7}, current)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o600)

    def test_unsafe_leaf_types_fail_promptly_without_overwriting_a_victim(self):
        self.target.parent.mkdir(mode=0o700)
        victim = self.root / 'victim.json'
        original = b'{"preset":"dusk"}'
        victim.write_bytes(original)
        for kind in ('symlink', 'fifo', 'hardlink', 'directory'):
            with self.subTest(kind=kind):
                if kind == 'symlink':
                    self.target.symlink_to(victim)
                elif kind == 'fifo':
                    os.mkfifo(self.target, 0o600)
                elif kind == 'hardlink':
                    os.link(victim, self.target)
                else:
                    self.target.mkdir(mode=0o700)
                try:
                    for result in (self.read(), self.save({'seed': 7}, {})):
                        self.assertNotEqual(result.returncode, 0)
                        self.assertEqual(result.stdout, '')
                        self.assertNotIn('Traceback', result.stderr)
                    self.assertEqual(victim.read_bytes(), original)
                finally:
                    self.target.rmdir() if kind == 'directory' else self.target.unlink()

    def test_unsafe_parent_symlink_is_not_followed_or_repaired(self):
        victim = self.root / 'other'
        victim.mkdir(mode=0o700)
        (victim / 'settings.json').write_text('{"preset":"dusk"}')
        self.target.parent.symlink_to(victim, target_is_directory=True)
        for result in (self.read(), self.save({'seed': 7}, {})):
            self.assertNotEqual(result.returncode, 0)
        self.assertEqual((victim / 'settings.json').read_text(), '{"preset":"dusk"}')
        self.assertFalse((victim / 'settings.lock').exists())
        self.assertTrue(self.target.parent.is_symlink())

    def test_writable_or_multiply_linked_settings_are_rejected(self):
        self.target.parent.mkdir(mode=0o700)
        self.target.write_text('{}')
        self.target.chmod(0o666)
        self.assertNotEqual(self.read().returncode, 0)
        self.assertNotEqual(self.save({'seed': 7}, {}).returncode, 0)
        self.assertEqual(self.target.read_text(), '{}')
        self.target.chmod(0o600)
        self.target.parent.chmod(0o777)
        self.assertNotEqual(self.read().returncode, 0)
        self.assertNotEqual(self.save({'seed': 7}, {}).returncode, 0)
        self.assertEqual(self.target.parent.stat().st_mode & 0o777, 0o777)

    def test_oversize_bad_encoding_and_excessive_nesting_fail_with_bounded_errors(self):
        self.target.parent.mkdir(mode=0o700)
        for content in (b'{}' + b' ' * (256 * 1024), b'\xff', b'[' * 2000 + b']' * 2000,
                        b'{"' + b'X' * 16000 + b'":1}', b'null'):
            with self.subTest(length=len(content)):
                self.target.write_bytes(content)
                result = self.read()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, '')
                self.assertLessEqual(len(result.stderr.encode()), 1400)
                self.assertNotIn('Traceback', result.stderr)
                self.assertNotEqual(self.save({'seed': 7}, {}).returncode, 0)
                self.assertEqual(self.target.read_bytes(), content)

    def test_busy_writer_lock_has_a_finite_wait_and_leaves_preferences_untouched(self):
        self.assertEqual(self.save({'seed': 1}, {}).returncode, 0)
        with (self.target.parent / 'settings.lock').open('r+') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            started = time.monotonic()
            result = self.save({'seed': 2}, {'seed': 1})
            self.assertNotEqual(result.returncode, 0)
            self.assertLess(time.monotonic() - started, 4)
        self.assertEqual(json.loads(self.target.read_text()), {'seed': 1})
        self.assertFalse(list(self.target.parent.glob('.settings-*')))

    def test_fifo_writer_lock_is_rejected_without_blocking(self):
        self.target.parent.mkdir(mode=0o700)
        os.mkfifo(self.target.parent / 'settings.lock', 0o600)
        result = self.save({'seed': 7}, {})
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.target.exists())

    def test_cooperating_writers_with_one_expected_document_cannot_both_publish(self):
        children = []
        try:
            for seed in (1, 2):
                children.append(subprocess.Popen(
                    [sys.executable, str(LAUNCHER), 'save-settings', json.dumps({'seed': seed}),
                     '--expected', '{}'], env=self.environment, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, text=True))
            for child in children:
                child.communicate(timeout=6)
            self.assertEqual(sorted(child.returncode for child in children), [0, 1])
            self.assertIn(json.loads(self.target.read_text()), ({'seed': 1}, {'seed': 2}))
            self.assertFalse(list(self.target.parent.glob('.settings-*')))
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                    child.communicate()

    def test_diagnostic_payload_is_bounded_and_has_no_terminal_controls(self):
        result = self.save({'\x1b[31m\n' + 'X' * 16000: 1}, {})
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('\x1b', result.stderr)
        self.assertEqual(result.stderr.count('\n'), 1)
        self.assertLess(len(result.stderr), 400)

    def test_randomize_returns_valid_staged_choices_without_writing_settings(self):
        sparse = {'preset': 'dusk', 'motion': {'speed': .5, 'reducedMotion': True},
                  'population': {'maxVisible': 3, 'maxFamilies': 0}}
        result = subprocess.run(
            [sys.executable, str(LAUNCHER), 'randomize-settings', json.dumps(sparse)],
            env=self.environment, capture_output=True, text=True, timeout=6)
        self.assertEqual(result.returncode, 0, result.stderr)
        randomized = json.loads(result.stdout)
        self.assertEqual(randomized['preset'], sparse['preset'])
        self.assertEqual(randomized['motion'], sparse['motion'])
        self.assertEqual(randomized['population']['maxVisible'], 3)
        self.assertEqual(randomized['population']['maxFamilies'], 0)
        self.assertIs(randomized['population']['randomVisitors'], True)
        self.assertFalse(self.target.parent.exists())
        resolved = subprocess.run(
            [sys.executable, str(LAUNCHER), 'resolve-settings', result.stdout],
            env=self.environment, capture_output=True, text=True, timeout=6)
        self.assertEqual(resolved.returncode, 0, resolved.stderr)
