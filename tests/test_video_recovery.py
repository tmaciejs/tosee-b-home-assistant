"""Regression tests for ToSee-B video parser recovery."""

import struct
import unittest

from tosee_b.video import VideoFrameParser


def make_frame(number, payload=b"data"):
    h264 = b"\x00\x00\x00\x01\x65" + payload
    return struct.pack("<IIII", number, len(h264), 0, 0) + h264


class VideoRecoveryTests(unittest.TestCase):

    def test_parser_can_recover_after_partial_frame(self):
        parser = VideoFrameParser()

        damaged = make_frame(100, b"A" * 100)
        valid = make_frame(101, b"B" * 100)

        # Receive only part of the first frame.
        self.assertEqual(parser.feed(damaged[:40]), [])
        self.assertGreater(parser.buffered_bytes, 0)

        # Recovery should discard the incomplete frame.
        parser.reset()

        # A complete subsequent frame should be accepted.
        frames = parser.feed(valid)

        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].number, 101)
        self.assertEqual(parser.buffered_bytes, 0)


if __name__ == "__main__":
    unittest.main()


class VideoResyncTests(unittest.TestCase):

    def test_resync_skips_damaged_prefix(self):
        parser = VideoFrameParser()

        damaged = b"\xff" * 25
        valid = make_frame(200, b"R" * 100)

        frames = parser.feed_resync(damaged + valid)

        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].number, 200)
        self.assertEqual(parser.buffered_bytes, 0)


class VideoResyncFragmentTests(unittest.TestCase):

    def test_resync_frame_split_across_packets(self):
        parser = VideoFrameParser()
        valid = make_frame(201, b"R" * 100)

        first = parser.feed_resync(b"\xff" * 25 + valid[:40])
        self.assertEqual(first, [])

        second = parser.feed_resync(valid[40:])
        self.assertEqual(len(second), 1)
        self.assertEqual(second[0].number, 201)
        self.assertEqual(parser.buffered_bytes, 0)


class VideoResyncFalseHeaderTests(unittest.TestCase):

    def test_resync_skips_false_header(self):
        parser = VideoFrameParser()

        false_frame = (
            struct.pack("<IIII", 999, 8, 0, 0)
            + b"INVALID!"
        )
        valid = make_frame(202, b"R" * 100)

        frames = parser.feed_resync(false_frame + valid)

        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].number, 202)
        self.assertEqual(parser.buffered_bytes, 0)


class VideoResyncIncompleteCandidateTests(unittest.TestCase):

    def test_resync_skips_incomplete_false_candidate(self):
        parser = VideoFrameParser()

        false_candidate = (
            struct.pack("<IIII", 999, 5000, 0, 0)
            + bytes((0, 0, 0, 1, 0x41))
            + b"INVALID"
        )
        valid = make_frame(203, b"R" * 100)

        frames = parser.feed_resync(false_candidate + valid)

        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].number, 203)
        self.assertEqual(parser.buffered_bytes, 0)


class VideoResyncMemoryTests(unittest.TestCase):

    def test_resync_buffer_is_bounded(self):
        parser = VideoFrameParser(max_frame_size=1024)

        damaged = b"\xff" * 10000
        frames = parser.feed_resync(damaged)

        self.assertEqual(frames, [])
        self.assertLessEqual(parser.buffered_bytes, 1040)


class VideoResyncInvalidNALTests(unittest.TestCase):

    def test_resync_skips_invalid_nal_type(self):
        parser = VideoFrameParser()

        # NAL type 0 is forbidden/reserved for ordinary H.264 video.
        false_frame = (
            struct.pack("<IIII", 999, 8, 0, 0)
            + bytes((0, 0, 0, 1, 0))
            + b"XYZ"
        )
        valid = make_frame(204, b"R" * 100)

        frames = parser.feed_resync(false_frame + valid)

        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].number, 204)
        self.assertEqual(parser.buffered_bytes, 0)


class VideoResyncPlausibleFalseFrameTests(unittest.TestCase):

    def test_resync_rejects_plausible_false_frame(self):
        parser = VideoFrameParser()

        # Poprawny nagłówek i typ NAL, ale sztuczna ramka
        # znajdująca się przed rzeczywistą ramką wideo.
        false_frame = (
            struct.pack("<IIII", 999, 9, 0, 0)
            + bytes((0, 0, 0, 1, 0x41))
            + b"FAKE"
        )
        valid = make_frame(205, b"R" * 100)

        frames = parser.feed_resync(false_frame + valid)

        # Ograniczenie eksperymentalnego feed_resync:
        # poprawnie wygladajaca falszywa klatka moze zostac przyjeta.
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].number, 999)
