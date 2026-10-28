import socket
import unittest
from unittest.mock import MagicMock

from tosee_b.commands import build_drw_packet
from tosee_b.crypto import encrypt_packet
from tosee_b.session_control import build_close_packets, close_session


ADDRESS = ("192.168.1.138", 10000)
F0 = encrypt_packet(bytes.fromhex("f1f00000"))


class SessionControlTests(unittest.TestCase):

    def test_close_packet_construction(self):
        packets = build_close_packets(42)
        self.assertEqual(packets, (
            build_drw_packet(42, 4),
            build_drw_packet(43, 6),
            F0,
        ))

    def test_sequence_wraparound(self):
        packets = build_close_packets(65535)
        self.assertEqual(packets[1], build_drw_packet(0, 6))

    def test_successful_close_with_intermediate_packet(self):
        sock = MagicMock()
        sock.recvfrom.side_effect = [
            (build_drw_packet(42, 4), ADDRESS),
            (F0, ADDRESS),
        ]

        self.assertTrue(close_session(sock, ADDRESS, 42))
        self.assertEqual(
            [call.args[0] for call in sock.sendto.call_args_list],
            list(build_close_packets(42)),
        )
        self.assertEqual(sock.recvfrom.call_count, 2)

    def test_timeout(self):
        sock = MagicMock()
        sock.recvfrom.side_effect = socket.timeout

        self.assertFalse(close_session(sock, ADDRESS, 42, timeout=0.1))
        self.assertEqual(sock.sendto.call_count, 3)

    def test_foreign_sender_ignored(self):
        sock = MagicMock()
        sock.recvfrom.side_effect = [
            (F0, ("192.0.2.100", 10000)),
            socket.timeout(),
        ]

        self.assertFalse(close_session(sock, ADDRESS, 42, timeout=0.1))


if __name__ == "__main__":
    unittest.main()
