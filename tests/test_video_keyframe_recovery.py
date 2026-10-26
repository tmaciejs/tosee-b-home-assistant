"""Tests for identifying a ToSee-B keyframe during recovery."""

import struct
import unittest

from tosee_b.video import VideoFrameParser


def make_frame(number, field2, *nal_headers):
    h264 = b"".join(
        b"\x00\x00\x00\x01" + bytes((nal,))
        for nal in nal_headers
    )
    return struct.pack("<IIII", number, len(h264), field2, 0) + h264


class VideoKeyframeRecoveryTests(unittest.TestCase):

    def test_recovery_skips_normal_frame_and_finds_keyframe(self):
        parser = VideoFrameParser()

        damaged = b"\xff" * 25
        normal = make_frame(300, 0, 0x41)
        keyframe = make_frame(301, 1, 0x67, 0x68, 0x06, 0x65)

        frames = parser.feed_keyframe_resync(damaged + normal + keyframe)

        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].number, 301)
        self.assertEqual(frames[0].field2, 1)
        self.assertEqual(frames[0].field3, 0)


if __name__ == "__main__":
    unittest.main()


class VideoKeyframeFragmentTests(unittest.TestCase):

    def test_keyframe_split_across_packets(self):
        parser = VideoFrameParser()

        keyframe = make_frame(
            400, 1, 0x67, 0x68, 0x06, 0x65
        )

        first = parser.feed_keyframe_resync(
            b"\xff" * 25 + keyframe[:30]
        )

        self.assertEqual(first, [])
        self.assertGreater(parser.buffered_bytes, 0)

        second = parser.feed_keyframe_resync(keyframe[30:])

        self.assertEqual(len(second), 1)
        self.assertEqual(second[0].number, 400)
        self.assertEqual(parser.buffered_bytes, 0)


class VideoKeyframeFalseCandidateTests(unittest.TestCase):

    def test_resync_rejects_false_keyframe_candidate(self):
        parser = VideoFrameParser()

        # Nagłówek wygląda jak ramka kluczowa ToSee-B,
        # ale H.264 nie zawiera PPS ani IDR.
        false_frame = make_frame(999, 1, 0x67, 0x41)
        valid_frame = make_frame(
            401, 1, 0x67, 0x68, 0x06, 0x65
        )

        frames = parser.feed_keyframe_resync(
            b"\xff" * 25 + false_frame + valid_frame
        )

        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].number, 401)
        self.assertEqual(parser.buffered_bytes, 0)


class VideoKeyframeIncompleteCandidateTests(unittest.TestCase):

    def test_resync_skips_incomplete_false_candidate(self):
        parser = VideoFrameParser()

        false_candidate = (
            struct.pack("<IIII", 999, 5000, 1, 0)
            + bytes((0, 0, 0, 1, 0x67))
            + b"INVALID"
        )
        valid_frame = make_frame(
            402, 1, 0x67, 0x68, 0x06, 0x65
        )

        frames = parser.feed_keyframe_resync(
            b"\xff" * 25 + false_candidate + valid_frame
        )

        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].number, 402)
        self.assertEqual(parser.buffered_bytes, 0)


class VideoKeyframeContinuationTests(unittest.TestCase):

    def test_normal_parsing_continues_after_keyframe_recovery(self):
        parser = VideoFrameParser()

        damaged = b"\xff" * 25
        keyframe = make_frame(500, 1, 0x67, 0x68, 0x06, 0x65)
        normal1 = make_frame(501, 0, 0x41)
        normal2 = make_frame(502, 0, 0x41)

        recovered = parser.feed_keyframe_resync(
            damaged + keyframe + normal1 + normal2
        )

        self.assertEqual(
            [frame.number for frame in recovered],
            [500],
        )
        self.assertGreater(parser.buffered_bytes, 0)

        continued = parser.feed(b"")

        self.assertEqual(
            [frame.number for frame in continued],
            [501, 502],
        )
        self.assertEqual(parser.buffered_bytes, 0)
