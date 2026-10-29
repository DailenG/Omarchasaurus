import os
from pathlib import Path
import socket
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from session_control import ControlServer


class BoundedControlProtocol(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.endpoint = str(Path(self.temporary.name) / 'control.sock')
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(self.endpoint)
        listener.listen(8)
        listener.setblocking(False)
        self.server = ControlServer(listener, 'preview')
        self.clients = []

    def tearDown(self):
        self.server.close()
        for client in self.clients:
            client.close()
        self.temporary.cleanup()

    def connect(self):
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(.5)
        client.connect(self.endpoint)
        self.clients.append(client)
        return client

    def test_fragmented_request_is_bounded_and_status_reply_is_finite(self):
        client = self.connect()
        client.sendall(b'sta')
        self.assertFalse(self.server.poll())
        client.sendall(b'tus')
        self.assertFalse(self.server.poll())
        self.assertEqual(client.recv(1024), b'Omarchasaurus preview session running\n')
        self.assertEqual(client.recv(1), b'')

    def test_stop_closes_listener_promptly_and_defers_one_ack_until_cleanup(self):
        stop = self.connect()
        later = self.connect()
        stop.sendall(b'stop')
        later.sendall(b'stop')
        self.assertTrue(self.server.poll())
        stop.setblocking(False)
        with self.assertRaises(BlockingIOError):
            stop.recv(1024)
        self.assertTrue(self.server.poll())
        self.server.close()
        stop.settimeout(.5)
        self.assertEqual(stop.recv(1024), b'Omarchasaurus owned terminals stopped and reaped\n')
        later.settimeout(.5)
        try:
            self.assertEqual(later.recv(1024), b'')
        except ConnectionResetError:
            pass

    def test_slow_request_expires_without_blocking_other_work(self):
        slow = self.connect()
        slow.sendall(b's')
        started = time.monotonic()
        self.assertFalse(self.server.poll())
        self.assertLess(time.monotonic() - started, .1)
        time.sleep(.25)
        self.assertFalse(self.server.poll())
        self.assertEqual(slow.recv(1), b'')
        valid = self.connect()
        valid.sendall(b'status')
        self.assertFalse(self.server.poll())
        self.assertIn(b'session running', valid.recv(1024))

    def test_oversized_and_unknown_requests_are_closed_without_response(self):
        for request in (b'x' * 4096, b'unknown'):
            with self.subTest(length=len(request)):
                client = self.connect()
                client.sendall(request)
                self.assertFalse(self.server.poll())
                try:
                    self.assertEqual(client.recv(1024), b'')
                except ConnectionResetError:
                    pass

    def test_repeated_idle_clients_have_bounded_open_descriptor_cost(self):
        before = len(os.listdir('/proc/self/fd'))
        for _ in range(8):
            self.connect()
        # Eight peer-side descriptors are ours; at most eight server-side
        # descriptors can be retained even after repeated polling.
        for _ in range(50):
            self.assertFalse(self.server.poll())
        self.assertLessEqual(len(os.listdir('/proc/self/fd')), before + 16)
        self.assertTrue(self.server.poll(stopping=True))
        self.assertLessEqual(len(os.listdir('/proc/self/fd')), before + 8)
