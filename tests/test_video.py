import struct
import unittest

from tosee_b.video import VideoFrameParser


def make_frame(number, nal_type, payload=b"data"):
    h264 = bytes((0, 0, 0, 1, nal_type)) + payload
    return struct.pack("<IIII", number, len(h264), 0, 0) + h264


class VideoFrameParserTests(unittest.TestCase):

    def test_complete_frame(self):
        parser = VideoFrameParser()
        frames = parser.feed(make_frame(83, 0x41))
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].number, 83)
        self.assertTrue(frames[0].h264.startswith(bytes((0, 0, 0, 1))))
        self.assertEqual(parser.buffered_bytes, 0)

    def test_fragmented_input(self):
        parser = VideoFrameParser()
        packet = make_frame(84, 0x41, b"x" * 200)
        frames = []
        for index in range(0, len(packet), 7):
            frames.extend(parser.feed(packet[index:index + 7]))
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].number, 84)

    def test_multiple_frames(self):
        parser = VideoFrameParser()
        frames = parser.feed(
            make_frame(85, 0x41) + make_frame(86, 0x65)
        )
        self.assertEqual([frame.number for frame in frames], [85, 86])

    def test_invalid_size(self):
        parser = VideoFrameParser(max_frame_size=100)
        with self.assertRaises(ValueError):
            parser.feed(struct.pack("<IIII", 1, 101, 0, 0))

    def test_missing_start_code(self):
        parser = VideoFrameParser()
        bad = struct.pack("<IIII", 1, 4, 0, 0) + b"ABCD"
        with self.assertRaises(ValueError):
            parser.feed(bad)


if __name__ == "__main__":
    unittest.main()
