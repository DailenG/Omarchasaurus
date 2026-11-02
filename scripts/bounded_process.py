"""Finite raw-pipe collection for same-UID desktop discovery helpers."""
import os
import selectors
import signal
import subprocess
import time


def exited(child):
    # Keep the unreaped leader as the process-group identity until cleanup ends.
    return os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None


def finish_groups(children, grace=2.0):
    for child in children:
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + grace
    while any(not exited(child) for child in children) and time.monotonic() < deadline:
        time.sleep(min(.025, max(0, deadline - time.monotonic())))
    # A dead leader does not mean its descendants released their inherited pipes.
    # WNOWAIT still protects every group ID until all signals have been sent.
    for child in children:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    return [child.wait() for child in children]


def finish_group(child, grace=2.0):
    return finish_groups([child], grace)[0]


def run_bounded(argv, timeout=5.0, stdout_limit=1024 * 1024, stderr_limit=8192):
    """Return UTF-8 stdout, never collecting beyond either raw-byte budget."""
    deadline = time.monotonic() + timeout
    child = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, start_new_session=True)
    buffers = {child.stdout: bytearray(), child.stderr: bytearray()}
    limits = {child.stdout: stdout_limit, child.stderr: stderr_limit}
    failure = None
    code = None
    try:
        with selectors.DefaultSelector() as selector:
            for stream in buffers:
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ)
            while selector.get_map() or not exited(child):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ValueError('Discovery command exceeded its deadline')
                for key, _ in selector.select(min(.05, remaining)):
                    stream = key.fileobj
                    budget = limits[stream] - len(buffers[stream])
                    data = os.read(stream.fileno(), min(65536, budget + 1))
                    if not data:
                        selector.unregister(stream)
                    elif len(data) > budget:
                        raise ValueError('Discovery command exceeded its output limit')
                    else:
                        buffers[stream].extend(data)
    except BaseException as error:
        failure = error
    finally:
        code = finish_group(child, grace=.2)
        for stream in buffers:
            stream.close()
    if failure is not None:
        raise failure
    if code:
        # Helper output can contain complete client titles/metadata. Do not
        # forward it into QML diagnostics, even when it fits the byte budget.
        raise ValueError(f'Discovery command failed (exit {code})')
    try:
        return buffers[child.stdout].decode('utf-8')
    except UnicodeError as error:
        raise ValueError('Discovery command returned invalid UTF-8') from error


def supervise(callback, *args):
    """Keep cleanup in a worker when its UI-owned guardian receives SIGKILL.

    Both generations get a parent-death signal; the worker handles TERM using
    its normal finally blocks, rather than losing owned resources with the UI.
    All callback modules must already be loaded before entering this function.
    """
    import ctypes

    libc = ctypes.CDLL(None, use_errno=True)
    prctl = libc.prctl
    prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong,
                     ctypes.c_ulong, ctypes.c_ulong]
    prctl.restype = ctypes.c_int
    child_pid = None
    stopping = False
    old_handlers = {}

    def protect(parent):
        if prctl(1, signal.SIGTERM, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), "Cannot protect owned cleanup")
        return os.getppid() == parent

    def forward(signum, frame):
        nonlocal stopping
        stopping = True
        if child_pid:
            try:
                os.kill(child_pid, signum)
            except ProcessLookupError:
                pass

    def early_stop(signum, frame):
        raise SystemExit(0)

    parent = os.getppid()
    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        old_handlers[signum] = signal.signal(signum, forward)
    try:
        if not protect(parent):
            return 0
        guardian = os.getpid()
        child_pid = os.fork()
        if child_pid == 0:
            child_pid = None
            for signum in old_handlers:
                signal.signal(signum, early_stop)
            if not protect(guardian) or stopping:
                return 0
            return callback(*args)
        if stopping:
            forward(signal.SIGTERM, None)
        _, status = os.waitpid(child_pid, 0)
        code = os.waitstatus_to_exitcode(status)
        return code if code >= 0 else 128 - code
    finally:
        for signum, handler in old_handlers.items():
            signal.signal(signum, handler)
