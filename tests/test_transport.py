# SPDX-License-Identifier: GPL-3.0-or-later
"""Offline unit tests for the ToSee-B UDP transport."""

import socket
import unittest
from unittest.mock import Mock

from tosee_b.crypto import encrypt_packet
from tosee_b.punch import build_punch_packet
from tosee_b.transport import perform_punch


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.did = bytes(range(20))
        self.address = ("192.0.2.10", 10000)
        self.sock = Mock()

    def ack(self, did=None):
        payload = self.did if did is None else did
        return encrypt_packet(b"\xf1\x42\x00\x14" + payload)

    def test_successful_punch(self):
        self.sock.recvfrom.return_value = (self.ack(), self.address)
        self.assertTrue(perform_punch(self.sock, self.address, self.did))
        self.sock.sendto.assert_called_once_with(
            build_punch_packet(self.did), self.address
        )

    def test_wrong_did(self):
        self.sock.recvfrom.side_effect = [
            (self.ack(bytes(20)), self.address),
            socket.timeout(),
        ]
        self.assertFalse(
            perform_punch(self.sock, self.address, self.did, retries=1)
        )

    def test_timeout(self):
        self.sock.recvfrom.side_effect = socket.timeout()
        self.assertFalse(
            perform_punch(self.sock, self.address, self.did, retries=1)
        )

    def test_ignore_other_sender(self):
        self.sock.recvfrom.side_effect = [
            (self.ack(), ("192.0.2.11", 10000)),
            (self.ack(), self.address),
        ]
        self.assertTrue(perform_punch(self.sock, self.address, self.did))
        self.assertEqual(self.sock.recvfrom.call_count, 2)

    def test_retry_after_timeout(self):
        self.sock.recvfrom.side_effect = [
            socket.timeout(),
            (self.ack(), self.address),
        ]
        self.assertTrue(
            perform_punch(self.sock, self.address, self.did, retries=3)
        )
        self.assertEqual(self.sock.sendto.call_count, 2)

    def test_ignore_invalid_ack(self):
        self.sock.recvfrom.side_effect = [
            (b"invalid", self.address),
            (self.ack(), self.address),
        ]
        self.assertTrue(perform_punch(self.sock, self.address, self.did))
        self.sock.sendto.assert_called_once()

    def test_retry_limit(self):
        self.sock.recvfrom.side_effect = socket.timeout()
        self.assertFalse(
            perform_punch(self.sock, self.address, self.did, retries=3)
        )
        self.assertEqual(self.sock.sendto.call_count, 3)

    def test_invalid_retries(self):
        with self.assertRaises(ValueError):
            perform_punch(self.sock, self.address, self.did, retries=0)

    def test_invalid_port(self):
        with self.assertRaises(ValueError):
            perform_punch(self.sock, ("192.0.2.10", 0), self.did)

    def test_invalid_timeout(self):
        with self.assertRaises(ValueError):
            perform_punch(self.sock, self.address, self.did, timeout=0)


if __name__ == "__main__":
    unittest.main()
