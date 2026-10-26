"""Tests for coordinated video recovery after a permanent UDP gap."""

import struct
import unittest

from tosee_b.video import H264Sync, VideoFrameParser
from tosee_b.video_reorder import VideoReorderBuffer


def make_frame(number, *nal_headers):
    h264 = b"".join(
        bytes((0, 0, 0, 1, nal))
        for nal in nal_headers
    )
    return struct.pack("<IIII", number, len(h264), 0, 0) + h264


class VideoGapRecoveryTests(unittest.TestCase):

    def test_reset_discards_partial_data_and_requires_keyframe(self):
        reorder = VideoReorderBuffer(window_size=16)
        parser = VideoFrameParser()
        sync = H264Sync()

        keyframe = make_frame(100, 0x67, 0x68, 0x65)

        for payload in reorder.push(10, keyframe):
            for frame in parser.feed(payload):
                self.assertIsNotNone(sync.accept(frame))

        # Receive an incomplete frame followed by a sequence gap.
        partial = make_frame(101, 0x41)[:18]

        for payload in reorder.push(11, partial):
            parser.feed(payload)

        self.assertEqual(reorder.push(13, b"damaged"), [])
        self.assertTrue(reorder.has_gap)
        self.assertGreater(parser.buffered_bytes, 0)

        # Explicit recovery after a permanent packet loss.
        reorder.discard_gap()
        parser.reset()
        sync.reset()

        self.assertFalse(reorder.has_gap)
        self.assertEqual(parser.buffered_bytes, 0)
        self.assertFalse(sync.synchronized)

        # Non-keyframe video must still be suppressed.
        frames = []
        for payload in reorder.push(14, make_frame(102, 0x41)):
            frames.extend(parser.feed(payload))

        self.assertEqual(len(frames), 1)
        self.assertIsNone(sync.accept(frames[0]))

        # A new SPS + PPS + IDR block restores H.264 output.
        frames = []
        for payload in reorder.push(
            15, make_frame(103, 0x67, 0x68, 0x65)
        ):
            frames.extend(parser.feed(payload))

        self.assertEqual(len(frames), 1)
        self.assertIsNotNone(sync.accept(frames[0]))


if __name__ == "__main__":
    unittest.main()
