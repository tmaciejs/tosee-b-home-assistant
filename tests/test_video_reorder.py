"""Unit tests for ToSee-B UDP video packet reordering."""

import unittest

from tosee_b.video_reorder import VideoReorderBuffer


class VideoReorderTests(unittest.TestCase):

    def setUp(self):
        self.buffer = VideoReorderBuffer(window_size=16)

    def test_in_order_packets(self):
        self.assertEqual(
            self.buffer.push(100, b"A"), [b"A"]
        )
        self.assertEqual(
            self.buffer.push(101, b"B"), [b"B"]
        )
        self.assertEqual(
            self.buffer.push(102, b"C"), [b"C"]
        )

    def test_out_of_order_packets(self):
        self.assertEqual(self.buffer.push(100, b"A"), [b"A"])
        self.assertEqual(self.buffer.push(102, b"C"), [])
        self.assertEqual(
            self.buffer.push(101, b"B"),
            [b"B", b"C"],
        )

    def test_multiple_out_of_order_packets(self):
        self.assertEqual(self.buffer.push(100, b"A"), [b"A"])
        self.assertEqual(self.buffer.push(103, b"D"), [])
        self.assertEqual(self.buffer.push(102, b"C"), [])
        self.assertEqual(
            self.buffer.push(101, b"B"),
            [b"B", b"C", b"D"],
        )

    def test_duplicate_packet(self):
        self.assertEqual(self.buffer.push(100, b"A"), [b"A"])
        self.assertEqual(self.buffer.push(100, b"A"), [])
        self.assertEqual(self.buffer.push(101, b"B"), [b"B"])

    def test_sequence_wraparound(self):
        buffer = VideoReorderBuffer(
            window_size=16,
            initial_sequence=65535,
        )

        self.assertEqual(buffer.push(65535, b"A"), [b"A"])
        self.assertEqual(buffer.push(1, b"C"), [])
        self.assertEqual(
            buffer.push(0, b"B"),
            [b"B", b"C"],
        )

    def test_missing_packet_is_buffered(self):
        self.assertEqual(self.buffer.push(100, b"A"), [b"A"])
        self.assertEqual(self.buffer.push(102, b"C"), [])
        self.assertEqual(self.buffer.push(103, b"D"), [])

        self.assertEqual(
            self.buffer.push(101, b"B"),
            [b"B", b"C", b"D"],
        )


if __name__ == "__main__":
    unittest.main()


class VideoReorderGapTests(unittest.TestCase):

    def test_pending_gap_is_reported(self):
        buffer = VideoReorderBuffer(window_size=16)

        self.assertEqual(buffer.push(100, b"A"), [b"A"])
        self.assertEqual(buffer.push(102, b"C"), [])

        self.assertTrue(buffer.has_gap)
        self.assertEqual(buffer.expected_sequence, 101)

        self.assertEqual(
            buffer.push(101, b"B"),
            [b"B", b"C"],
        )
        self.assertFalse(buffer.has_gap)


class VideoReorderTimeoutTests(unittest.TestCase):

    def test_gap_timeout_reports_loss_without_releasing_data(self):
        buffer = VideoReorderBuffer(window_size=16)

        self.assertEqual(buffer.push(100, b"A"), [b"A"])
        self.assertEqual(buffer.push(102, b"C"), [])

        # Before the deadline, the missing packet may still arrive.
        self.assertFalse(buffer.gap_expired(now=1.04, timeout=0.1,
                                            gap_started_at=1.0))

        # After the deadline, report the loss.
        self.assertTrue(buffer.gap_expired(now=1.11, timeout=0.1,
                                           gap_started_at=1.0))

        # Detection must not silently release incomplete video data.
        self.assertEqual(buffer.expected_sequence, 101)
        self.assertTrue(buffer.has_gap)


class VideoReorderDiscardTests(unittest.TestCase):

    def test_discard_gap_does_not_release_incomplete_data(self):
        buffer = VideoReorderBuffer(window_size=16)

        self.assertEqual(buffer.push(100, b"A"), [b"A"])
        self.assertEqual(buffer.push(102, b"C"), [])
        self.assertEqual(buffer.push(103, b"D"), [])

        # A permanent gap must not release potentially damaged video.
        buffer.discard_gap()

        self.assertFalse(buffer.has_gap)
        self.assertEqual(buffer.push(104, b"E"), [b"E"])


class VideoReorderRestartTests(unittest.TestCase):

    def test_restart_rejects_old_packets(self):
        reorder = VideoReorderBuffer(window_size=128)

        reorder.push(100, b"A")
        reorder.push(102, b"B")

        reorder.discard_gap()
        reorder.expected_sequence = 103

        self.assertEqual(reorder.push(101, b"OLD"), [])
        self.assertFalse(reorder.has_gap)

        self.assertEqual(reorder.push(103, b"NEW"), [b"NEW"])
        self.assertFalse(reorder.has_gap)

    def test_restart_handles_sequence_wraparound(self):
        reorder = VideoReorderBuffer(window_size=128)

        reorder.expected_sequence = 0

        self.assertEqual(reorder.push(65535, b"OLD"), [])
        self.assertEqual(reorder.push(0, b"NEW"), [b"NEW"])
        self.assertFalse(reorder.has_gap)
