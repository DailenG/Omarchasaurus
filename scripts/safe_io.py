"""Bounded local JSON and descriptor-relative user-owned file operations."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import secrets
import stat
import time

UID = os.getuid()
READ_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
DIR_FLAGS = READ_FLAGS | os.O_DIRECTORY
MAX_JSON_BYTES = 256 * 1024


def diagnostic(error):
    """Never forward terminal escapes, multiline payloads, or huge diagnostics."""
    return ''.join(c if c.isprintable() else ' ' for c in str(error)[:320])


def parse_json(raw, limit=MAX_JSON_BYTES, blank=False):
    if len(raw) > limit:
        raise ValueError('JSON exceeds its size limit')
    try:
        text = raw.decode('utf-8') if isinstance(raw, bytes) else raw
        if len(text.encode('utf-8')) > limit:
            raise ValueError('JSON exceeds its size limit')
        value = {} if blank and not text.strip() else json.loads(text)
    except (UnicodeError, RecursionError, json.JSONDecodeError) as error:
        raise ValueError('Invalid JSON encoding or nesting') from error
    pending = [(value, 0)]
    nodes = 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        if depth > 16 or nodes > 8192:
            raise ValueError('JSON structure exceeds its limit')
        if isinstance(item, dict):
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
    return value


def validate_file(fd, private=False):
    info = os.fstat(fd)
    forbidden = 0o077 if private else 0o022
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != UID
            or info.st_nlink != 1 or info.st_mode & forbidden):
        raise ValueError('Refusing unsafe regular file')
    return info


def open_file(directory_fd, name, flags=os.O_RDONLY, private=False, create=False):
    fd = os.open(name, flags | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
                 | (os.O_CREAT if create else 0), 0o600, dir_fd=directory_fd)
    try:
        validate_file(fd, private)
        return fd
    except BaseException:
        os.close(fd)
        raise


def read_json(directory_fd, name, limit=MAX_JSON_BYTES, private=False,
              blank=False, missing=False):
    try:
        fd = open_file(directory_fd, name, private=private)
    except FileNotFoundError:
        if missing:
            return {}
        raise
    try:
        if os.fstat(fd).st_size > limit:
            raise ValueError('JSON file exceeds its size limit')
        raw = bytearray()
        while len(raw) <= limit:
            chunk = os.read(fd, min(65536, limit + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        return parse_json(bytes(raw), limit, blank)
    finally:
        os.close(fd)


def _directory_info(fd, private=False, ancestor=False):
    info = os.fstat(fd)
    # Root-owned sticky ancestors (notably /tmp in private test fixtures) are
    # traversable; every child is still opened no-follow and validated itself.
    sticky_root = ancestor and info.st_uid == 0 and info.st_mode & stat.S_ISVTX
    if (not stat.S_ISDIR(info.st_mode)
            or info.st_uid not in ((0, UID) if ancestor else (UID,))
            or (info.st_mode & (0o077 if private else 0o022) and not sticky_root)):
        raise ValueError('Refusing unsafe directory')
    return info


class Directory:
    """Hold the complete verified ancestry until all relative operations finish."""
    def __init__(self, path, fds):
        self.path = Path(path)
        self.fds = fds

    @property
    def fd(self):
        return self.fds[-1]

    @property
    def parent_fd(self):
        return self.fds[-2]

    @property
    def proc_path(self):
        # AF_UNIX bind/connect lack dir_fd; Linux resolves this through the held
        # directory, not through a subsequently substituted pathname ancestor.
        return f'/proc/self/fd/{self.fd}'

    @classmethod
    def open(cls, path, private=False, create=False):
        path = Path(path)
        if not path.is_absolute() or '..' in path.parts:
            raise ValueError('Directory path must be absolute without parent traversal')
        fds = [os.open('/', DIR_FLAGS)]
        try:
            parts = path.parts[1:]
            for index, part in enumerate(parts):
                if create:
                    try:
                        os.mkdir(part, 0o700, dir_fd=fds[-1])
                    except FileExistsError:
                        pass
                fd = os.open(part, DIR_FLAGS, dir_fd=fds[-1])
                fds.append(fd)
                final = index == len(parts) - 1
                _directory_info(fd, private=private and final, ancestor=not final or not private)
            if not parts:
                _directory_info(fds[-1], private=private, ancestor=not private)
            return cls(path, fds)
        except BaseException:
            for fd in reversed(fds):
                os.close(fd)
            raise

    def child(self, name, create=False):
        if not name or '/' in name or name in ('.', '..'):
            raise ValueError('Invalid directory component')
        if create:
            os.mkdir(name, 0o700, dir_fd=self.fd)
        fds = []
        try:
            for fd in self.fds:
                fds.append(os.dup(fd))
            fds.append(os.open(name, DIR_FLAGS, dir_fd=self.fd))
            _directory_info(fds[-1], private=True)
            return Directory(self.path / name, fds)
        except BaseException:
            for fd in reversed(fds):
                os.close(fd)
            raise

    def close(self):
        for fd in reversed(self.fds):
            os.close(fd)
        self.fds.clear()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


@contextmanager
def held_directory(directory):
    if isinstance(directory, Directory):
        yield directory
    else:
        with Directory.open(directory, private=True) as held:
            yield held


@contextmanager
def writer_lock(directory_fd, name, timeout=2.0):
    fd = open_file(directory_fd, name, os.O_RDWR, private=True, create=True)
    try:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise ValueError('Timed out waiting for settings writer')
                time.sleep(min(.025, max(0, deadline - time.monotonic())))
        yield
    finally:
        os.close(fd)


def atomic_json(directory_fd, name, value, private=False):
    """Publish through the original exclusive 0600 fd, then fsync its directory.

    Callers validate the current leaf and hold their cooperative writer lock.
    External editors that ignore that lock can still race the comparison/replace.
    """
    try:
        current = open_file(directory_fd, name, private=private)
    except FileNotFoundError:
        pass
    else:
        os.close(current)
    data = (json.dumps(value, indent=2, allow_nan=False) + '\n').encode('utf-8')
    if len(data) > MAX_JSON_BYTES:
        raise ValueError('JSON exceeds its size limit')
    temporary = '.settings-' + secrets.token_hex(16)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                 | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                 0o600, dir_fd=directory_fd)
    original = None
    try:
        original = os.fstat(fd)
        os.fchmod(fd, 0o600)
        validate_file(fd, private=True)
        remaining = memoryview(data)
        while remaining:
            written = os.write(fd, remaining)
            if written <= 0:
                raise OSError('Short JSON write')
            remaining = remaining[written:]
        os.fsync(fd)
        published = os.stat(temporary, dir_fd=directory_fd, follow_symlinks=False)
        if (published.st_dev, published.st_ino) != (original.st_dev, original.st_ino):
            raise ValueError('Temporary JSON file changed before publication')
        os.replace(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        temporary = None
        os.fsync(directory_fd)
    finally:
        os.close(fd)
        if temporary is not None and original is not None:
            try:
                remaining = os.stat(temporary, dir_fd=directory_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                if (remaining.st_dev, remaining.st_ino) == (original.st_dev, original.st_ino):
                    os.unlink(temporary, dir_fd=directory_fd)


def remove_socket(directory_fd, name, expected=None):
    try:
        info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if (not stat.S_ISSOCK(info.st_mode) or info.st_uid != UID or info.st_mode & 0o077):
        raise ValueError('Refusing unsafe session control socket')
    if expected is None or (info.st_dev, info.st_ino) == expected:
        os.unlink(name, dir_fd=directory_fd)


def remove_session(parent_fd, name, session):
    # Only our protocol leaves are cleanup targets; never recursively follow or
    # remove a substituted directory or unrelated object.
    for leaf in ('authority.json', 'dismissed.json'):
        try:
            fd = open_file(session.fd, leaf, private=True)
        except FileNotFoundError:
            continue
        os.close(fd)
        os.unlink(leaf, dir_fd=session.fd)
    try:
        info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    held = os.fstat(session.fd)
    if (info.st_dev, info.st_ino) == (held.st_dev, held.st_ino):
        os.rmdir(name, dir_fd=parent_fd)
