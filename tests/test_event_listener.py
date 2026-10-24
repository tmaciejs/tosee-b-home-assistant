"""Tests for passive ToSee-B event detection."""

import unittest

from tosee_b.event_listener import EventDeduplicator, parse_packet


class TestPacketParser(unittest.TestCase):
    def test_doorbell(self):
        line = (
            "06:39:44.943942 IP 192.168.1.138.25290 > "
            "18.231.70.126.25000: UDP, length 1104"
        )
        self.assertEqual(parse_packet(line), "doorbell")

    def test_motion(self):
        line = (
            "06:19:34.447756 IP 192.168.1.138.25290 > "
            "18.231.70.126.25000: UDP, length 1052"
        )
        self.assertEqual(parse_packet(line), "motion")

    def test_other_packet_ignored(self):
        self.assertIsNone(
            parse_packet(
                "06:19:34 IP 192.168.1.138.25290 > "
                "18.231.70.126.25000: UDP, length 80"
            )
        )

    def test_other_device_ignored(self):
        self.assertIsNone(
            parse_packet(
                "06:19:34 IP 192.168.1.139.25290 > "
                "18.231.70.126.25000: UDP, length 1052"
            )
        )


class TestDeduplication(unittest.TestCase):
    def test_duplicate_suppressed(self):
        dedup = EventDeduplicator(interval=3.0)

        self.assertTrue(dedup.accept("doorbell", now=10.0))
        self.assertFalse(dedup.accept("doorbell", now=10.02))
        self.assertTrue(dedup.accept("doorbell", now=13.1))

    def test_different_events_independent(self):
        dedup = EventDeduplicator(interval=3.0)

        self.assertTrue(dedup.accept("doorbell", now=10.0))
        self.assertTrue(dedup.accept("motion", now=10.1))

    def test_invalid_interval(self):
        with self.assertRaises(ValueError):
            EventDeduplicator(interval=-1)


if __name__ == "__main__":
    unittest.main()
