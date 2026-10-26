"""Tests for receiving G.711 A-law audio from ToSee-B."""

import struct
import unittest
from unittest.mock import Mock

from tosee_b.ack import build_drw_ack
from tosee_b.crypto import encrypt_packet
from tosee_b.live import ToSeeBLive


ADDRESS = ("192.0.2.10", 10000)
HEADER = bytes.fromhex("000000004001000000000000")


class LiveAudioTests(unittest.TestCase):

    def test_receives_audio_and_acknowledges(self):
        sock = Mock()
        received_audio = []

        client = ToSeeBLive(
            sock=sock,
            address=ADDRESS,
            did=b"A" * 20,
            client_uuid="12345678-1234-4234-8234-123456789abc",
            on_h264=Mock(),
            on_audio=received_audio.append,
        )

        samples = bytes([0xD5]) * 320
        payload = HEADER + samples

        plain = (
            b"\xf1\xd0"
            + struct.pack(">H", 4 + len(payload))
            + b"\xd1\x02\x00\x07"
            + payload
        )

        sock.recvfrom.return_value = (
            encrypt_packet(plain),
            ADDRESS,
        )

        client._receive(0.1)

        self.assertEqual(client.stats.audio_packets, 1)
        self.assertEqual(received_audio, [samples])

        sock.sendto.assert_called_once_with(
            build_drw_ack(2, [7]),
            ADDRESS,
        )


if __name__ == "__main__":
    unittest.main()
