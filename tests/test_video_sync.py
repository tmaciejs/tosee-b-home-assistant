import unittest

from tosee_b.video import H264Sync, VideoFrame, h264_nal_types


def make_frame(number, *types):
    data = b"".join(
        b"\x00\x00\x00\x01" + bytes([nal])
        for nal in types
    )
    return VideoFrame(number, data, 0, 0)


class H264SyncTests(unittest.TestCase):

    def test_nal_types(self):
        frame = make_frame(93, 0x67, 0x68, 0x06, 0x65)
        self.assertEqual(h264_nal_types(frame.h264), [7, 8, 6, 5])

    def test_discard_until_keyframe(self):
        sync = H264Sync()

        self.assertIsNone(sync.accept(make_frame(83, 0x41)))
        self.assertIsNone(sync.accept(make_frame(84, 0x41)))

        keyframe = make_frame(93, 0x67, 0x68, 0x06, 0x65)
        self.assertEqual(sync.accept(keyframe), keyframe.h264)
        self.assertTrue(sync.synchronized)

        next_frame = make_frame(94, 0x41)
        self.assertEqual(sync.accept(next_frame), next_frame.h264)

    def test_missing_pps(self):
        sync = H264Sync()
        self.assertIsNone(sync.accept(make_frame(93, 0x67, 0x65)))
        self.assertFalse(sync.synchronized)

    def test_wrong_order(self):
        sync = H264Sync()
        self.assertIsNone(sync.accept(make_frame(93, 0x65, 0x67, 0x68)))
        self.assertFalse(sync.synchronized)

    def test_reset(self):
        sync = H264Sync()
        sync.accept(make_frame(93, 0x67, 0x68, 0x65))
        self.assertTrue(sync.synchronized)

        sync.reset()
        self.assertFalse(sync.synchronized)
        self.assertIsNone(sync.accept(make_frame(94, 0x41)))


if __name__ == "__main__":
    unittest.main()
