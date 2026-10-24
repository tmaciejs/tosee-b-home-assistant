# SPDX-License-Identifier: GPL-3.0-or-later
"""Offline tests for ToSee-B PPCS PUNCH handshake."""

import unittest

from tosee_b.crypto import encrypt_packet, decrypt_packet
from tosee_b.punch import build_punch_packet, validate_punch_ack


class PunchTests(unittest.TestCase):
    def setUp(self):
        self.did = bytes(range(20))

    def test_punch_packet(self):
        plain = decrypt_packet(build_punch_packet(self.did))
        self.assertEqual(plain, b"\xf1\x41\x00\x14" + self.did)

    def test_matching_ack(self):
        ack = encrypt_packet(b"\xf1\x42\x00\x14" + self.did)
        self.assertTrue(validate_punch_ack(ack, self.did))

    def test_wrong_did(self):
        ack = encrypt_packet(b"\xf1\x42\x00\x14" + bytes(20))
        self.assertFalse(validate_punch_ack(ack, self.did))

    def test_wrong_message_type(self):
        self.assertFalse(
            validate_punch_ack(build_punch_packet(self.did), self.did)
        )

    def test_invalid_did_length(self):
        with self.assertRaises(ValueError):
            build_punch_packet(b"short")

    def test_truncated_ack(self):
        self.assertFalse(validate_punch_ack(b"\x00", self.did))


if __name__ == "__main__":
    unittest.main()
