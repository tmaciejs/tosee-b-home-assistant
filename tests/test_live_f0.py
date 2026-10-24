import socket
import unittest
from unittest.mock import Mock

from tosee_b.crypto import encrypt_packet
from tosee_b.live import ToSeeBLive


ADDRESS = ("192.0.2.10", 10000)
F0 = encrypt_packet(bytes.fromhex("f1f00000"))


class LiveCloseTests(unittest.TestCase):

    def setUp(self):
        self.sock = Mock()
        self.client = ToSeeBLive(
            self.sock,
            ADDRESS,
            b"A" * 20,
            "12345678-1234-4234-8234-123456789abc",
            lambda data: None,
        )

    def test_f0_acknowledged(self):
        self.sock.recvfrom.return_value = (F0, ADDRESS)

        result = self.client._close_session()

        self.assertTrue(result)
        self.sock.sendto.assert_called_once_with(F0, ADDRESS)

    def test_f0_timeout(self):
        self.sock.recvfrom.side_effect = socket.timeout

        result = self.client._close_session()

        self.assertFalse(result)
        self.sock.sendto.assert_called_once_with(F0, ADDRESS)

    def test_f0_from_other_sender_ignored(self):
        self.sock.recvfrom.side_effect = [
            (F0, ("192.0.2.99", 10000)),
            (F0, ADDRESS),
        ]

        result = self.client._close_session()

        self.assertTrue(result)
        self.assertEqual(self.sock.recvfrom.call_count, 2)


if __name__ == "__main__":
    unittest.main()
