import json
import socket
import struct
import unittest
from unittest.mock import Mock, patch

from tosee_b.ack import build_drw_ack
from tosee_b.crypto import encrypt_packet
from tosee_b.live import ToSeeBLive
from tosee_b.video import VideoFrame


ADDRESS = ("192.0.2.10", 10000)


def make_video_block(number, *nal_types):
    h264 = b"".join(
        b"\x00\x00\x00\x01" + bytes((nal,))
        for nal in nal_types
    )
    return struct.pack("<IIII", number, len(h264), 0, 0) + h264


class LiveTests(unittest.TestCase):

    def setUp(self):
        self.sock = Mock()
        self.output = []
        self.client = ToSeeBLive(
            self.sock,
            ADDRESS,
            b"A" * 20,
            "12345678-1234-4234-8234-123456789abc",
            self.output.append,
        )

    def test_control_responses(self):
        valid = ToSeeBLive._valid_response

        self.assertTrue(valid(0, bytes(12)))
        self.assertTrue(valid(1, json.dumps({"sw_ver": "test"}).encode()))
        self.assertTrue(valid(2, struct.pack("<III", 0, 0, 5)))
        self.assertTrue(valid(3, struct.pack("<III", 0, 0, 3)))

        self.assertFalse(valid(0, bytes(11)))
        self.assertFalse(valid(1, b"not-json"))
        self.assertFalse(valid(2, struct.pack("<III", 0, 0, 3)))
        self.assertFalse(valid(3, None))

    def test_video_requires_keyframe(self):
        self.assertIsNone(
            self.client.sync.accept(
                VideoFrame(83, b"\x00\x00\x00\x01\x41", 0, 0)
            )
        )

        keyframe = VideoFrame(
            93,
            b"\x00\x00\x00\x01\x67"
            b"\x00\x00\x00\x01\x68"
            b"\x00\x00\x00\x01\x65",
            0,
            0,
        )
        self.assertEqual(self.client.sync.accept(keyframe), keyframe.h264)

    def test_receives_video_and_acknowledges(self):
        keyframe = make_video_block(93, 0x67, 0x68, 0x65)
        packet = b"\xf1\xd0" + struct.pack(">H", 4 + len(keyframe)) \
            + b"\xd1\x01\x00\x00" + keyframe
        self.sock.recvfrom.return_value = (encrypt_packet(packet), ADDRESS)

        self.client._receive(0.1)

        self.assertEqual(self.client.stats.video_packets, 1)
        self.assertEqual(self.client.stats.video_blocks, 1)
        self.assertEqual(self.client.stats.output_blocks, 1)
        self.assertEqual(len(self.output), 1)
        self.sock.sendto.assert_called_once_with(
            build_drw_ack(1, [0]), ADDRESS
        )

    def test_other_sender_ignored(self):
        self.sock.recvfrom.return_value = (
            b"invalid",
            ("192.0.2.99", 10000),
        )

        self.assertIsNone(self.client._receive(0.1))
        self.sock.sendto.assert_not_called()

    def test_socket_timeout(self):
        self.sock.recvfrom.side_effect = socket.timeout
        self.assertIsNone(self.client._receive(0.1))

    def test_invalid_duration(self):
        with self.assertRaises(ValueError):
            self.client.run(duration=0)
        self.sock.sendto.assert_not_called()


if __name__ == "__main__":
    unittest.main()
