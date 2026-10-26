"""Tests for ToSee-B G.711 A-law frame extraction."""

import unittest

from tosee_b.audio import extract_alaw


HEADER = bytes.fromhex("000000004001000000000000")


class TestAudio(unittest.TestCase):

    def test_single_frame(self):
        payload = HEADER + bytes([0xD5]) * 320
        self.assertEqual(
            extract_alaw(payload),
            bytes([0xD5]) * 320,
        )

    def test_two_frames(self):
        payload = (
            HEADER + bytes([0xD5]) * 320
            + HEADER + bytes([0x50]) * 320
        )
        self.assertEqual(
            extract_alaw(payload),
            bytes([0xD5]) * 320 + bytes([0x50]) * 320,
        )

    def test_three_frames(self):
        payload = (HEADER + bytes([0xD5]) * 320) * 3
        self.assertEqual(len(extract_alaw(payload)), 960)

    def test_invalid_size(self):
        with self.assertRaises(ValueError):
            extract_alaw(b"\x00" * 100)

    def test_invalid_header(self):
        with self.assertRaises(ValueError):
            extract_alaw(b"\x00" * 332)

    def test_empty_payload(self):
        with self.assertRaises(ValueError):
            extract_alaw(b"")

    def test_invalid_type(self):
        with self.assertRaises(TypeError):
            extract_alaw("not bytes")


if __name__ == "__main__":
    unittest.main()
