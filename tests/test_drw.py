# SPDX-License-Identifier: GPL-3.0-or-later
"""Offline tests for incoming PPCS DRW packets."""

import unittest

from tosee_b.crypto import encrypt_packet
from tosee_b.ack import build_drw_ack
from tosee_b.drw import parse_drw_packet


class DrwTests(unittest.TestCase):
    def test_channel_zero_response(self):
        packet = encrypt_packet(
            bytes.fromhex("f1 d0 00 08 d1 00 00 03")
            + bytes.fromhex("03 00 00 00")
        )
        self.assertEqual(
            parse_drw_packet(packet),
            (0, 3, bytes.fromhex("03 00 00 00"))
        )

    def test_video_channel(self):
        packet = encrypt_packet(
            bytes.fromhex("f1 d0 00 07 d1 01 00 05")
            + b"abc"
        )
        self.assertEqual(parse_drw_packet(packet), (1, 5, b"abc"))

    def test_invalid_packet(self):
        self.assertIsNone(parse_drw_packet(b"invalid"))

    def test_not_drw(self):
        self.assertIsNone(parse_drw_packet(build_drw_ack(0, [0])))

    def test_truncated_header(self):
        packet = encrypt_packet(bytes.fromhex("f1 d0 00 02 d1 00"))
        self.assertIsNone(parse_drw_packet(packet))

    def test_invalid_input_type(self):
        self.assertIsNone(parse_drw_packet(None))


if __name__ == "__main__":
    unittest.main()
