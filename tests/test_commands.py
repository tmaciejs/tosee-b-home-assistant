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



    def test_init_command_structure(self):
        import struct
        from tosee_b.commands import build_init_command

        example_uuid = "00000000-0000-0000-0000-000000000001"
        data = build_init_command(example_uuid)

        self.assertEqual(len(data), 184)
        self.assertEqual(struct.unpack_from("<II", data, 0), (0, 176))
        self.assertEqual(data[0x0C:0x0E], b"11")
        self.assertEqual(data[0x12:0x17], b"1.0.0")
        self.assertEqual(
            data[0x32:0x56],
            example_uuid.encode("ascii")
        )

        expected = bytearray(184)
        struct.pack_into("<II", expected, 0, 0, 176)
        expected[0x0C:0x0E] = b"11"
        expected[0x12:0x17] = b"1.0.0"
        expected[0x32:0x56] = example_uuid.encode("ascii")

        self.assertEqual(data, bytes(expected))


if __name__ == "__main__":
    unittest.main()
