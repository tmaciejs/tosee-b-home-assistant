# SPDX-License-Identifier: GPL-3.0-or-later
"""Offline tests for ToSee-B PPCS DRW_ACK."""

import unittest

from tosee_b.ack import build_drw_ack
from tosee_b.crypto import decrypt_packet, is_valid_ppcs_packet


class AckTests(unittest.TestCase):
    def test_single_ack(self):
        packet = decrypt_packet(build_drw_ack(0, [3]))
        self.assertEqual(
            packet,
            bytes.fromhex("f1 d1 00 06 d1 00 00 01 00 03")
        )
        self.assertTrue(is_valid_ppcs_packet(packet))

    def test_duplicate_sequences(self):
        packet = decrypt_packet(build_drw_ack(0, [1, 1]))
        self.assertEqual(
            packet,
            bytes.fromhex("f1 d1 00 08 d1 00 00 02 00 01 00 01")
        )

    def test_video_channel(self):
        packet = decrypt_packet(build_drw_ack(1, [0, 2]))
        self.assertEqual(packet[5], 1)
        self.assertEqual(packet[6:8], bytes.fromhex("00 02"))

    def test_invalid_channel(self):
        with self.assertRaises(ValueError):
            build_drw_ack(256, [0])

    def test_empty_sequences(self):
        with self.assertRaises(ValueError):
            build_drw_ack(0, [])

    def test_invalid_sequence(self):
        with self.assertRaises(ValueError):
            build_drw_ack(0, [65536])


if __name__ == "__main__":
    unittest.main()
