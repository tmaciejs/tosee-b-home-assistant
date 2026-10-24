# SPDX-License-Identifier: GPL-3.0-or-later
"""Offline tests for ToSee-B initialization session helpers."""

import struct
import unittest

from tosee_b.crypto import decrypt_packet, encrypt_packet
from tosee_b.ack import build_drw_ack
from tosee_b.session import (
    build_init_drw_packet,
    parse_drw_ack,
    InitResponseTracker,
)

TEST_UUID = "12345678-1234-4234-8234-123456789abc"


def device_response():
    payload = b"\xd1\x00\x00\x00" + b"test"
    return encrypt_packet(struct.pack(">BBH", 0xF1, 0xD0, len(payload)) + payload)


class SessionTests(unittest.TestCase):
    def test_full_init_packet(self):
        packet = decrypt_packet(build_init_drw_packet(TEST_UUID))
        self.assertEqual(len(packet), 192)
        self.assertEqual(packet[:8], bytes.fromhex("f1 d0 00 bc d1 00 00 00"))
        self.assertEqual(len(packet[8:]), 184)

    def test_ack_parser(self):
        self.assertEqual(parse_drw_ack(build_drw_ack(0, [0, 0])), (0, [0, 0]))

    def test_ack_parser_rejects_drw(self):
        self.assertIsNone(parse_drw_ack(device_response()))

    def test_ack_first(self):
        tracker = InitResponseTracker()
        self.assertTrue(tracker.accept(build_drw_ack(0, [0])))
        self.assertFalse(tracker.complete)
        self.assertTrue(tracker.accept(device_response()))
        self.assertTrue(tracker.complete)

    def test_response_first(self):
        tracker = InitResponseTracker()
        self.assertTrue(tracker.accept(device_response()))
        self.assertFalse(tracker.complete)
        self.assertTrue(tracker.accept(build_drw_ack(0, [0, 0])))
        self.assertTrue(tracker.complete)

    def test_wrong_sequence_does_not_complete(self):
        tracker = InitResponseTracker()
        self.assertFalse(tracker.accept(build_drw_ack(0, [1])))
        self.assertTrue(tracker.accept(device_response()))
        self.assertFalse(tracker.complete)


if __name__ == "__main__":
    unittest.main()
