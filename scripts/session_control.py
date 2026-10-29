"""Small same-UID control protocol with finite per-pass work and retained state."""
import os
import socket
import struct
import time


class ControlServer:
    MAX_CLIENTS = 8
    ACCEPTS_PER_PASS = 4
    REQUEST_BYTES = 16
    REQUEST_SECONDS = .2

    def __init__(self, listener, mode):
        self.listener = listener
        self.mode = mode
        self.clients = {}
        self.reply = None  # At most one deferred Stop acknowledgement.

    def stop_accepting(self):
        if self.listener is not None:
            self.listener.close()
            self.listener = None
        for connection in self.clients:
            connection.close()
        self.clients.clear()

    def poll(self, stopping=False):
        if stopping:
            self.stop_accepting()
            return True
        if self.listener is None:
            return True
        for _ in range(self.ACCEPTS_PER_PASS):
            if len(self.clients) >= self.MAX_CLIENTS:
                break
            try:
                connection, _ = self.listener.accept()
            except BlockingIOError:
                break
            connection.setblocking(False)
            try:
                _, uid, _ = struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                if uid != os.getuid():
                    connection.close()
                    continue
                self.clients[connection] = (bytearray(), time.monotonic() + self.REQUEST_SECONDS)
            except OSError:
                connection.close()
        for connection, (request, deadline) in list(self.clients.items()):
            close = time.monotonic() >= deadline
            if not close:
                try:
                    data = connection.recv(self.REQUEST_BYTES + 1 - len(request))
                    request.extend(data)
                    close = not data or len(request) > self.REQUEST_BYTES
                except BlockingIOError:
                    continue
                except OSError:
                    close = True
            if not close and request == b'stop':
                self.clients.pop(connection)
                self.reply = connection
                self.stop_accepting()
                return True
            if not close and request == b'status':
                try:
                    connection.send(b'Omarchasaurus ' + self.mode.encode('ascii') + b' session running\n')
                except OSError:
                    pass
                close = True
            if not close and not any(word.startswith(request) for word in (b'stop', b'status')):
                close = True
            if close:
                self.clients.pop(connection)
                connection.close()
        return False

    def close(self):
        self.stop_accepting()
        if self.reply is not None:
            try:
                self.reply.settimeout(.1)
                self.reply.sendall(b'Omarchasaurus owned terminals stopped and reaped\n')
            except OSError:
                pass
            finally:
                self.reply.close()
                self.reply = None
