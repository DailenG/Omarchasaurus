"""Opt-in, live idle policy and an exclusively owned stock-saver suppression lease."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time

from bounded_process import run_bounded, supervise
from configuration import config_path, settings
from safe_io import (Directory, _directory_info, diagnostic, open_file, parse_json,
                     read_json, validate_file)

TOGGLE = 'screensaver-off'
RECORD = 'omarchasaurus-idle.json'
LOCK = 'omarchasaurus-idle.lock'
LIMIT = 2048
SOURCE = Path(__file__).absolute()


def state_path():
    home = os.environ.get('HOME', '')
    if not home or not Path(home).is_absolute():
        raise ValueError('HOME must be absolute for Omarchy state')
    return Path(home) / '.local/state/omarchy'


def ownership_path():
    return state_path().parent / 'omarchasaurus'


def settings_enabled(last_signature=object()):
    path = config_path()
    try:
        with Directory.open(path.parent) as directory:
            try:
                info = os.stat(path.name, dir_fd=directory.fd, follow_symlinks=False)
            except FileNotFoundError:
                return False, None
            signature = (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
                         info.st_uid, info.st_mtime_ns, info.st_size)
            if signature == last_signature:
                return True, signature
            document = read_json(directory.fd, path.name, blank=True, missing=True)
    except FileNotFoundError:
        return False, None
    if not isinstance(document, dict):
        return False, signature
    try:
        settings(document)
    except ValueError:
        return False, signature
    integration = document.get('integration')
    enabled = isinstance(integration, dict) and integration.get('idleEnabled') is True
    return enabled, signature

def identity(fd, private=True):
    info = validate_file(fd, private=private)
    return info.st_dev, info.st_ino


def attached(directory, private=False):
    """Check held ancestry without resolving through substituted parent paths."""
    for index, part in enumerate(directory.path.parts[1:], 1):
        info = os.stat(part, dir_fd=directory.fds[index - 1], follow_symlinks=False)
        final = index == len(directory.fds) - 1
        held = _directory_info(directory.fds[index], private=private and final,
                               ancestor=not final or not private)
        if (info.st_dev, info.st_ino) != (held.st_dev, held.st_ino):
            return False
    return True


def bytes_at(fd):
    if os.fstat(fd).st_size > LIMIT:
        raise ValueError('Idle marker exceeds its size limit')
    return os.pread(fd, LIMIT + 1, 0)


def matches(directory, name, fd, data):
    try:
        with_fd = open_file(directory.fd, name, private=True)
        try:
            return identity(with_fd) == identity(fd) and bytes_at(with_fd) == data
        finally:
            os.close(with_fd)
    except (OSError, ValueError):
        return False


def _has_entry(directory, name):
    try:
        os.stat(name, dir_fd=directory.fd, follow_symlinks=False)
        return True
    except FileNotFoundError:
        return False


def owned_lease():
    toggle_dir = None
    try:
        toggle_dir = Directory.open(state_path() / 'toggles')
    except FileNotFoundError:
        pass
    try:
        has_toggle = toggle_dir is not None and _has_entry(toggle_dir, TOGGLE)
        if not has_toggle:
            try:
                ownership = Directory.open(ownership_path(), private=True)
            except FileNotFoundError:
                return False
            with ownership:
                if _has_entry(ownership, RECORD):
                    raise ValueError('Stale idle ownership record requires attention; inspect leftover state before retrying')
                return False
        assert toggle_dir is not None
        try:
            marker = read_json(toggle_dir.fd, TOGGLE, limit=LIMIT, private=True)
        except (OSError, ValueError) as error:
            raise ValueError('Stock screensaver is disabled by the user or another saver; resolve its toggle before enabling') from error
        try:
            ownership = Directory.open(ownership_path(), private=True)
        except FileNotFoundError as error:
            raise ValueError('Stock screensaver is disabled by the user or another saver; resolve its toggle before enabling') from error
        with ownership:
            try:
                record = read_json(ownership.fd, RECORD, limit=LIMIT, private=True)
                lock = open_file(ownership.fd, LOCK, os.O_RDWR, private=True)
            except FileNotFoundError as error:
                raise ValueError('Existing stock toggle has no complete ownership record; resolve foreign or stale state before retrying') from error
            try:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    pass
                else:
                    raise ValueError('Stale idle ownership: no live lease holds the lock; inspect leftover state before retrying')
                if (not isinstance(record, dict) or record != marker
                        or set(record) != {'version', 'token', 'lock'}
                        or type(record.get('version')) is not int or record['version'] != 1
                        or not isinstance(record.get('token'), str) or len(record['token']) != 64
                        or any(c not in '0123456789abcdef' for c in record['token'])
                        or record.get('lock') != list(identity(lock))
                        or not attached(toggle_dir) or not attached(ownership, private=True)):
                    raise ValueError('Stock toggle changed or does not match this owned idle lease')
                return True
            finally:
                os.close(lock)
    finally:
        if toggle_dir is not None:
            toggle_dir.close()


def keep_awake_marker():
    try:
        directory = Directory.open(state_path() / 'indicators')
    except FileNotFoundError:
        return False
    with directory:
        try:
            fd = open_file(directory.fd, 'stay-awake')
        except FileNotFoundError:
            return False
        os.close(fd)
        return True


def host_policy():
    raw = run_bounded(['omarchy-shell', 'idle', 'status'], timeout=1.0,
                      stdout_limit=16384, stderr_limit=1024)
    host = parse_json(raw, limit=16384)
    if (not isinstance(host, dict)
            or any(type(host.get(key)) is not bool for key in
                   ('enabled', 'stayAwake', 'stayAwakeStateLoaded'))
            or type(host.get('screensaver')) is not int
            or not 0 <= host['screensaver'] <= 2**31 - 1
            or type(host.get('screensaverWindows')) is not int
            or not 0 <= host['screensaverWindows'] <= 1024):
        raise ValueError('Omarchy idle status is malformed; check the host idle service')
    lock = run_bounded(['omarchy-shell', 'lock', 'isLocked'], timeout=1.0,
                       stdout_limit=32, stderr_limit=1024).strip()
    if lock not in ('true', 'false'):
        raise ValueError('Omarchy lock status is unavailable or malformed')
    return (host['enabled'], host['stayAwake'] or keep_awake_marker(),
            host['stayAwakeStateLoaded'], host['screensaver'], lock == 'true')


def idle_status():
    result = dict(version=1, owned=False, eligible=False, timeout=0,
                  keepAwake=False, locked=True, reason='Idle integration is unavailable')
    try:
        enabled, awake, loaded, timeout, locked = host_policy()
        result.update(timeout=timeout, keepAwake=awake, locked=locked)
        pref_enabled, _ = settings_enabled()
        owned = owned_lease()
        result['owned'] = owned
        if not pref_enabled:
            result['reason'] = 'Enable automatic idle activation in Omarchasaurus settings'
        elif not owned:
            result['reason'] = 'Waiting for Omarchasaurus idle lease'
        elif not loaded:
            result['reason'] = 'Waiting for Omarchy Keep Awake state to load'
        elif awake:
            result['reason'] = 'Keep Awake is enabled; automatic activation is paused'
        elif not enabled:
            result['reason'] = 'Omarchy idle service is disabled'
        elif timeout == 0:
            result['reason'] = 'Omarchy screensaver timeout is zero; enable it in host settings'
        elif locked:
            result['reason'] = 'Session is locked; automatic activation is paused'
        else:
            result.update(eligible=True, reason='Automatic idle activation is ready')
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        result['reason'] = diagnostic(error)[:240]
    return result


def message(text, error=False):
    try:
        print(text, file=sys.stderr if error else sys.stdout, flush=True)
    except BrokenPipeError:
        pass


class Lease:
    def __init__(self, directory, ownership):
        self.directory = directory
        self.ownership = ownership
        self.lock = None
        self.files = []

    def acquire(self):
        self.lock = open_file(self.ownership.fd, LOCK, os.O_RDWR, private=True, create=True)
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError('Another Omarchasaurus idle lease is already active') from error
        if bytes_at(self.lock) != b'':
            raise ValueError('Idle lock contains foreign data; inspect ownership state before retrying')
        for directory, name in ((self.ownership, RECORD), (self.directory, TOGGLE)):
            try:
                os.stat(name, dir_fd=directory.fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                label = ('Stale idle ownership state requires attention'
                         if name == RECORD else 'Stock screensaver is disabled by the user or another saver')
                raise ValueError(label + '; existing state is never replaced')
        data = (json.dumps({'version': 1, 'token': secrets.token_hex(32),
                            'lock': list(identity(self.lock))}, separators=(',', ':')) + '\n').encode()
        for directory, name in ((self.ownership, RECORD), (self.directory, TOGGLE)):
            temp = f'.idle-{secrets.token_hex(8)}.tmp'
            temp_fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                              | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                              0o600, dir_fd=directory.fd)
            temp_identity = None
            linked = False
            try:
                os.fchmod(temp_fd, 0o600)
                temp_identity = identity(temp_fd)
                remaining = memoryview(data)
                while remaining:
                    written = os.write(temp_fd, remaining)
                    if written <= 0:
                        raise OSError('Short idle marker write')
                    remaining = remaining[written:]
                os.fsync(temp_fd)
                os.link(temp, name, src_dir_fd=directory.fd, dst_dir_fd=directory.fd)
                linked = True
            finally:
                try:
                    os.unlink(temp, dir_fd=directory.fd)
                except FileNotFoundError:
                    pass
                os.close(temp_fd)
            try:
                fd = open_file(directory.fd, name, private=True)
            except BaseException:
                if linked and temp_identity is not None:
                    try:
                        info = os.stat(name, dir_fd=directory.fd, follow_symlinks=False)
                        if (info.st_dev, info.st_ino) == temp_identity:
                            os.unlink(name, dir_fd=directory.fd)
                    except OSError:
                        pass
                raise
            self.files.append((directory, name, fd, data))
        os.fsync(self.directory.fd)
        os.fsync(self.ownership.fd)
        if not self.valid():
            raise ValueError('Idle state changed during lease acquisition')

    def valid(self):
        return (attached(self.directory) and attached(self.ownership, private=True) and self.lock is not None
                and matches(self.ownership, LOCK, self.lock, b'')
                and len(self.files) == 2
                and all(matches(*item) for item in self.files))

    def release(self):
        # The directory descriptors survive source/state directory deletion.
        # Never follow or remove a foreign replacement, even on partial acquire.
        failure = None
        for directory, name, fd, data in reversed(self.files):
            try:
                if matches(directory, name, fd, data):
                    os.unlink(name, dir_fd=directory.fd)
            except OSError as error:
                failure = error
            finally:
                os.close(fd)
        self.files.clear()
        if self.lock is not None:
            os.close(self.lock)
            self.lock = None
        if failure is not None:
            raise failure


def lease():
    stopping = False
    old_handlers = {}

    def stop(signum, frame):
        nonlocal stopping
        stopping = True

    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        old_handlers[signum] = signal.signal(signum, stop)
    try:
        enabled_now, config_sig = settings_enabled()
        if stopping or not enabled_now:
            raise ValueError('Persist integration.idleEnabled=true before starting an idle lease')
        with Directory.open(SOURCE.parent) as source:
            source_fd = open_file(source.fd, SOURCE.name)
            try:
                with Directory.open(state_path() / 'toggles', create=True) as directory, \
                        Directory.open(ownership_path(), private=True, create=True) as ownership:
                    owned = Lease(directory, ownership)
                    try:
                        if stopping:
                            return 0
                        owned.acquire()
                        message('owned')
                        while not stopping:
                            try:
                                current = os.stat(SOURCE.name, dir_fd=source.fd, follow_symlinks=False)
                                source_alive = ((current.st_dev, current.st_ino) == identity(source_fd, private=False)
                                                and attached(source))
                                enabled_now, config_sig = settings_enabled(config_sig)
                                if not source_alive or not enabled_now or not owned.valid():
                                    break
                            except (OSError, ValueError):
                                break
                            time.sleep(.5)
                    finally:
                        owned.release()
                        message('Omarchasaurus idle lease released; foreign replacements left untouched')
            finally:
                os.close(source_fd)
        return 0
    finally:
        for signum, handler in old_handlers.items():
            signal.signal(signum, handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('status', 'lease'))
    args = parser.parse_args()
    if args.command == 'status':
        print(json.dumps(idle_status(), separators=(',', ':'), allow_nan=False), flush=True)
        return 0
    try:
        return supervise(lease)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        message('Omarchasaurus idle lease: ' + diagnostic(error), error=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
