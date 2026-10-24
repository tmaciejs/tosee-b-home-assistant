"""Tests for passive video sequence diagnostics."""

import unittest
from unittest.mock import Mock, patch

from tosee_b.live import ToSeeBLive


class VideoSequenceTests(unittest.TestCase):

    def setUp(self):
        self.client = ToSeeBLive(
            sock=Mock(),
            address=("192.0.2.10", 10000),
            did=b"A" * 20,
            client_uuid="12345678-1234-4234-8234-123456789abc",
            on_h264=Mock(),
        )

        self.assertIsNone(self.client._last_video_sequence)

    def test_sequence_starts_unknown(self):
        self.assertIsNone(self.client._last_video_sequence)

    def test_sequence_can_track_increment(self):
        self.client._last_video_sequence = 100
        expected = (self.client._last_video_sequence + 1) & 0xFFFF
        self.assertEqual(expected, 101)

    def test_sequence_wraparound(self):
        self.client._last_video_sequence = 65535
        expected = (self.client._last_video_sequence + 1) & 0xFFFF
        self.assertEqual(expected, 0)


if __name__ == "__main__":
    unittest.main()

class VideoSequenceReceiveTests(unittest.TestCase):
    """Check diagnostics using simulated encrypted DRW packets."""

    def test_detects_sequence_gap(self):
        import struct
        from unittest.mock import Mock, patch
        from tosee_b.crypto import encrypt_packet

        address = ("192.0.2.10", 10000)
        sock = Mock()

        client = ToSeeBLive(
            sock=sock,
            address=address,
            did=b"A" * 20,
            client_uuid="12345678-1234-4234-8234-123456789abc",
            on_h264=Mock(),
        )

        def packet(sequence):
            plain = (
                b"\xf1\xd0"
                + struct.pack(">H", 4)
                + b"\xd1\x01"
                + struct.pack(">H", sequence)
            )
            return encrypt_packet(plain)

        sock.recvfrom.side_effect = [
            (packet(100), address),
            (packet(102), address),
        ]

        with patch("tosee_b.live.logging.warning") as warning:
            client._receive(0.1)
            client._receive(0.1)

        warning.assert_called_once_with(
            "TOSEE_VIDEO_SEQUENCE previous=%d expected=%d received=%d",
            100, 101, 102,
        )

        self.assertEqual(client.stats.video_packets, 2)
