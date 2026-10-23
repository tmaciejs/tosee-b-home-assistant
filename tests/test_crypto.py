# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the ToSee-B PPCS decryptor."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tosee_b.crypto import decrypt_packet, is_valid_ppcs_packet


class CryptoTests(unittest.TestCase):

    def test_known_encrypted_header(self):
        encrypted = bytes.fromhex("b57cd1bb")
        expected = bytes.fromhex("f1d00404")
        self.assertEqual(decrypt_packet(encrypted), expected)

    def test_ppcs_header_validation(self):
        self.assertTrue(
            is_valid_ppcs_packet(bytes.fromhex("f1d00000"))
        )

    def test_invalid_header(self):
        self.assertFalse(
            is_valid_ppcs_packet(bytes.fromhex("b57cd1bb"))
        )

    def test_invalid_length(self):
        self.assertFalse(
            is_valid_ppcs_packet(bytes.fromhex("f1d00010"))
        )

    def test_invalid_cipher_state(self):
        with self.assertRaises(ValueError):
            decrypt_packet(b"\xb5", state=b"\x00")



    def test_encrypt_decrypt_roundtrip(self):
        from tosee_b.crypto import encrypt_packet, decrypt_packet

        for data in (
            b"",
            b"\\xf1\\xd0\\x00\\x04\\xd1\\x01\\x00\\x01",
            bytes(range(256)),
        ):
            with self.subTest(length=len(data)):
                self.assertEqual(decrypt_packet(encrypt_packet(data)), data)

    def test_encrypt_invalid_state(self):
        from tosee_b.crypto import encrypt_packet

        with self.assertRaises(ValueError):
            encrypt_packet(b"test", state=b"bad")


if __name__ == "__main__":
    unittest.main()
