from pathlib import Path
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from bounded_process import run_bounded


class BoundedDiscovery(unittest.TestCase):
    def run_helper(self, code, **kwargs):
        return run_bounded([sys.executable, '-c', code], **kwargs)

    def test_success_preserves_utf8_stdout_without_mixing_stderr(self):
        value = self.run_helper("import os; os.write(2, b'diagnostic'); os.write(1, 'valley \\u263a'.encode())")
        self.assertEqual(value, 'valley \u263a')

    def test_stdout_and_stderr_have_independent_raw_byte_budgets(self):
        for descriptor in (1, 2):
            with self.subTest(descriptor=descriptor):
                code = f'import os\nwhile True: os.write({descriptor}, b"X" * 4096)'
                started = time.monotonic()
                with self.assertRaisesRegex(ValueError, 'output limit'):
                    self.run_helper(code, timeout=2, stdout_limit=1024, stderr_limit=1024)
                self.assertLess(time.monotonic() - started, 1.5)

    def test_nonzero_output_does_not_leak_client_metadata_into_diagnostics(self):
        code = "import os; os.write(1, b'PRIVATE CLIENT TITLE'); os.write(2, b'PRIVATE APP METADATA'); raise SystemExit(7)"
        with self.assertRaises(ValueError) as caught:
            self.run_helper(code)
        self.assertIn('exit 7', str(caught.exception))
        self.assertNotIn('PRIVATE', str(caught.exception))

    def test_trickling_output_cannot_extend_the_absolute_deadline(self):
        code = 'import os, time\nfor _ in range(100):\n os.write(1, b".")\n time.sleep(.05)'
        started = time.monotonic()
        with self.assertRaisesRegex(ValueError, 'deadline'):
            self.run_helper(code, timeout=.25)
        self.assertLess(time.monotonic() - started, 1.5)

    def test_exited_leader_with_pipe_holding_descendant_is_killed_as_an_owned_group(self):
        with tempfile.TemporaryDirectory() as temporary:
            record = Path(temporary) / 'descendant'
            code = (
                'import os, signal, time\n'
                'pid = os.fork()\n'
                'if pid:\n'
                ' os._exit(0)\n'
                'signal.signal(signal.SIGTERM, signal.SIG_IGN)\n'
                f'open({str(record)!r}, "w").write(str(os.getpid()))\n'
                'time.sleep(30)\n'
            )
            started = time.monotonic()
            with self.assertRaisesRegex(ValueError, 'deadline'):
                self.run_helper(code, timeout=.5)
            self.assertLess(time.monotonic() - started, 1.5)
            pid = int(record.read_text())
            # The orphan may briefly remain a zombie awaiting the host reaper;
            # it must not be a living descendant retaining the helper's pipes.
            status = Path(f'/proc/{pid}/stat')
            deadline = time.monotonic() + 1
            while status.exists() and status.read_text().split(') ', 1)[1][0] != 'Z':
                self.assertLess(time.monotonic(), deadline, 'owned descendant survived KILL')
                time.sleep(.01)

    def test_invalid_utf8_is_a_controlled_failure(self):
        with self.assertRaisesRegex(ValueError, 'UTF-8'):
            self.run_helper('import os; os.write(1, b"\\xff")')
