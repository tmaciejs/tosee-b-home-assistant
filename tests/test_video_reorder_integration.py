"""Integration tests for UDP reordering and H.264 frame parsing."""

import struct
import unittest

from tosee_b.video import VideoFrameParser
from tosee_b.video_reorder import VideoReorderBuffer


class VideoReorderIntegrationTests(unittest.TestCase):

    def test_out_of_order_fragments_reassemble_frame(self):
        reorder = VideoReorderBuffer(window_size=16)
        parser = VideoFrameParser()

        h264 = bytes((0, 0, 0, 1, 0x65)) + b"A" * 100
        frame = struct.pack("<IIII", 300, len(h264), 0, 0) + h264

        fragments = (
            frame[:30],
            frame[30:70],
            frame[70:],
        )

        received = (
            (100, fragments[0]),
            (102, fragments[2]),
            (101, fragments[1]),
        )

        frames = []

        for sequence, payload in received:
            for ordered_payload in reorder.push(sequence, payload):
                frames.extend(parser.feed(ordered_payload))

        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].number, 300)
        self.assertEqual(frames[0].h264, h264)
        self.assertEqual(parser.buffered_bytes, 0)
        self.assertFalse(reorder.has_gap)


if __name__ == "__main__":
    unittest.main()
