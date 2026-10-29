import fcntl
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from dinosaurs import notify_dismissal, session_alive
from safe_io import Directory, atomic_json, read_json, remove_session


class DescriptorBoundIO(unittest.TestCase):
    def test_renamed_parent_does_not_redirect_reads_or_atomic_publication(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            intended = root / 'settings'
            intended.mkdir(mode=0o700)
            (intended / 'settings.json').write_text('{"seed":1}')
            victim = root / 'victim'
            victim.mkdir(mode=0o700)
            (victim / 'settings.json').write_text('{"seed":99}')
            with Directory.open(intended, private=True) as held:
                intended.rename(root / 'retained')
                intended.symlink_to(victim, target_is_directory=True)
                self.assertEqual(read_json(held.fd, 'settings.json'), {'seed': 1})
                atomic_json(held.fd, 'settings.json', {'seed': 2})
            self.assertEqual(json.loads((root / 'retained/settings.json').read_text()), {'seed': 2})
            self.assertEqual(json.loads((victim / 'settings.json').read_text()), {'seed': 99})
            self.assertFalse(list((root / 'retained').glob('.settings-*')))

    def test_session_authority_and_dismissal_remain_bound_after_parent_replacement(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = root / 'preview-session'
            session.mkdir(mode=0o700)
            token = secrets.token_urlsafe(32)
            with Directory.open(session, private=True) as held:
                atomic_json(held.fd, 'authority.json', {'token': token}, private=True)
                session.rename(root / 'retained-session')
                victim = root / 'victim'
                victim.mkdir(mode=0o700)
                session.symlink_to(victim, target_is_directory=True)
                notify_dismissal(held)
                self.assertEqual(read_json(held.fd, 'dismissed.json', private=True), {'token': token})
                self.assertFalse((victim / 'dismissed.json').exists())
                remove_session(held.parent_fd, session.name, held)
                self.assertTrue(session.is_symlink())
                self.assertFalse((root / 'retained-session/authority.json').exists())

    def test_dismissal_rejects_symlink_or_fifo_authority_without_touching_victim(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = root / 'session'
            session.mkdir(mode=0o700)
            victim = root / 'victim'
            original = json.dumps({'token': secrets.token_urlsafe(32)})
            victim.write_text(original)
            victim.chmod(0o600)
            authority = session / 'authority.json'
            for kind in ('symlink', 'fifo'):
                with self.subTest(kind=kind):
                    authority.symlink_to(victim) if kind == 'symlink' else os.mkfifo(authority, 0o600)
                    try:
                        with self.assertRaises((OSError, ValueError)):
                            notify_dismissal(session)
                        self.assertFalse((session / 'dismissed.json').exists())
                        self.assertEqual(victim.read_text(), original)
                    finally:
                        authority.unlink()

    def test_dismissal_rejects_unsafe_existing_leaf_without_replacing_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = root / 'session'
            session.mkdir(mode=0o700)
            victim = root / 'victim'
            victim.write_text('untouched')
            with Directory.open(session, private=True) as held:
                atomic_json(held.fd, 'authority.json', {'token': secrets.token_urlsafe(32)}, private=True)
                (session / 'dismissed.json').symlink_to(victim)
                with self.assertRaises((OSError, ValueError)):
                    notify_dismissal(held)
                self.assertTrue((session / 'dismissed.json').is_symlink())
                self.assertEqual(victim.read_text(), 'untouched')

    def test_renderer_liveness_fails_closed_for_fifo_symlink_and_hardlink_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = root / 'preview-session'
            session.mkdir(mode=0o700)
            victim = root / 'victim'
            victim.touch(mode=0o600)
            lock = root / 'preview.lock'
            with victim.open('r+') as coordinator:
                fcntl.flock(coordinator, fcntl.LOCK_EX)
                for kind in ('fifo', 'symlink', 'hardlink'):
                    with self.subTest(kind=kind):
                        if kind == 'fifo':
                            os.mkfifo(lock, 0o600)
                        elif kind == 'symlink':
                            lock.symlink_to(victim)
                        else:
                            os.link(victim, lock)
                        try:
                            self.assertFalse(session_alive(session, True))
                        finally:
                            lock.unlink()

    def test_held_renderer_liveness_probes_original_parent_after_rename(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime = root / 'runtime'
            runtime.mkdir(mode=0o700)
            session = runtime / 'preview-session'
            session.mkdir(mode=0o700)
            lock = runtime / 'preview.lock'
            lock.touch(mode=0o600)
            with lock.open('r+') as coordinator, Directory.open(session, private=True) as held:
                fcntl.flock(coordinator, fcntl.LOCK_EX)
                runtime.rename(root / 'retained-runtime')
                runtime.mkdir(mode=0o700)
                (runtime / 'preview.lock').touch(mode=0o600)
                self.assertTrue(session_alive(held, True))
                fcntl.flock(coordinator, fcntl.LOCK_UN)
                self.assertFalse(session_alive(held, True))

    def test_real_write_failure_preserves_old_document_and_removes_its_temporary(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / 'settings.json'
            target.write_text('{"seed":1}')
            code = (
                'import resource, signal, sys\n'
                f'sys.path.insert(0, {str(ROOT / "scripts")!r})\n'
                'from safe_io import Directory, atomic_json\n'
                'signal.signal(signal.SIGXFSZ, signal.SIG_IGN)\n'
                'resource.setrlimit(resource.RLIMIT_FSIZE, (64, 64))\n'
                f'with Directory.open({str(root)!r}, private=True) as directory:\n'
                ' try:\n'
                '  atomic_json(directory.fd, "settings.json", {"payload": "X" * 1024})\n'
                ' except OSError:\n'
                '  raise SystemExit(7)\n'
            )
            result = subprocess.run([sys.executable, '-c', code], capture_output=True,
                                    text=True, timeout=3)
            self.assertEqual(result.returncode, 7, result.stderr)
            self.assertEqual(target.read_text(), '{"seed":1}')
            self.assertFalse(list(root.glob('.settings-*')))
