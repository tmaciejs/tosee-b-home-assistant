# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for ToSee-B channel-zero control packets."""

import unittest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from tosee_b.commands import build_control_command, build_drw_packet
from tosee_b.crypto import decrypt_packet, is_valid_ppcs_packet


class CommandTests(unittest.TestCase):

    def test_command_5(self):
        self.assertEqual(
            build_control_command(5),
            bytes.fromhex("0500000000000000")
        )

    def test_command_3(self):
        self.assertEqual(
            build_control_command(3),
            bytes.fromhex("0300000000000000")
        )

    def test_encrypted_drw_command_5(self):
        packet = build_drw_packet(2, 5)
        self.assertEqual(len(packet), 16)
        self.assertEqual(
            decrypt_packet(packet),
            bytes.fromhex("f1d0000cd10000020500000000000000")
        )

    def test_encrypted_drw_command_3(self):
        packet = build_drw_packet(3, 3)
        self.assertEqual(len(packet), 16)
        self.assertEqual(
            decrypt_packet(packet),
            bytes.fromhex("f1d0000cd10000030300000000000000")
        )

    def test_invalid_sequence(self):
        with self.assertRaises(ValueError):
            build_drw_packet(65536, 3)

    def test_invalid_command(self):
        with self.assertRaises(ValueError):
            build_control_command(-1)


if __name__ == "__main__":
    unittest.main()
