import unittest

from tosee_b.crypto import decrypt_packet, is_valid_ppcs_packet
from tosee_b.talkback import build_audio_packet


class TalkbackTests(unittest.TestCase):

    def test_audio_packet_structure(self):
        audio = bytes([0xD5]) * 320

        encrypted = build_audio_packet(
            drw_sequence=269,
            audio_sequence=0,
            alaw_samples=audio,
        )

        packet = decrypt_packet(encrypted)

        self.assertEqual(len(packet), 340)
        self.assertTrue(is_valid_ppcs_packet(packet))
        self.assertEqual(packet[4:6], b"\xd1\x03")
        self.assertEqual(
            int.from_bytes(packet[6:8], "big"), 269
        )
        self.assertEqual(
            int.from_bytes(packet[8:12], "little"), 0
        )
        self.assertEqual(
            packet[12:20],
            bytes.fromhex("4001000000000000"),
        )
        self.assertEqual(packet[20:], audio)

    def test_invalid_audio_length(self):
        with self.assertRaises(ValueError):
            build_audio_packet(0, 0, bytes(319))


if __name__ == "__main__":
    unittest.main()
