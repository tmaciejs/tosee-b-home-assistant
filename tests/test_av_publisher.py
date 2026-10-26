"""Unit tests for the experimental audio/video RTSP publisher."""

import os
import subprocess
import unittest
from unittest.mock import MagicMock, patch

from tosee_b.av_publisher import publish_av_session


ADDRESS = ("192.0.2.10", 10000)
DID = b"A" * 20
UUID = "12345678-1234-4234-8234-123456789abc"


class AVPublisherTests(unittest.TestCase):

    def setUp(self):
        self.process = MagicMock()
        self.process.poll.return_value = None

        self.socket = MagicMock()
        self.socket_context = MagicMock()
        self.socket_context.__enter__.return_value = self.socket

        self.popen_patch = patch(
            "tosee_b.av_publisher.subprocess.Popen",
            return_value=self.process,
        )
        self.socket_patch = patch(
            "tosee_b.av_publisher.socket.socket",
            return_value=self.socket_context,
        )
        self.live_patch = patch(
            "tosee_b.av_publisher.ToSeeBLive"
        )

        self.popen = self.popen_patch.start()
        self.socket_factory = self.socket_patch.start()
        self.live = self.live_patch.start()

        self.addCleanup(self.popen_patch.stop)
        self.addCleanup(self.socket_patch.stop)
        self.addCleanup(self.live_patch.stop)

    def test_successful_session(self):
        self.live.return_value.run.return_value = "stats"

        result = publish_av_session(
            ADDRESS, DID, UUID, duration=5
        )

        self.assertEqual(result, "stats")
        self.live.return_value.run.assert_called_once_with(
            duration=5
        )
        self.socket.bind.assert_called_once_with(
            ("0.0.0.0", 0)
        )
        self.process.stdin.close.assert_called_once()
        self.process.wait.assert_called_once_with(
            timeout=10
        )

    def test_h264_written_to_ffmpeg(self):
        h264 = b"\\x00\\x00\\x00\\x01\\x65"
        received = []

        def write_mock(fd, data):
            received.append(bytes(data))
            return len(data)

        def run_session(duration):
            callback = self.live.call_args.kwargs["on_h264"]
            callback(h264)
            return "stats"

        self.live.return_value.run.side_effect = run_session

        with patch("tosee_b.av_publisher.os.write",
                   side_effect=write_mock):
            result = publish_av_session(ADDRESS, DID, UUID)

        self.assertEqual(result, "stats")
        self.assertEqual(b"".join(received), h264)

    def test_alaw_written_to_audio_pipe(self):
        samples = bytes([0xD5]) * 320
        received = []
        inherited_fd = None

        real_popen = self.popen

        def simulate_popen(*args, **kwargs):
            nonlocal inherited_fd
            inherited_fd = os.dup(kwargs["pass_fds"][0])
            return self.process

        real_popen.side_effect = simulate_popen

        def run_session(duration):
            callback = self.live.call_args.kwargs["on_audio"]
            callback(samples)
            received.append(os.read(inherited_fd, len(samples)))
            return "stats"

        self.live.return_value.run.side_effect = run_session

        try:
            publish_av_session(ADDRESS, DID, UUID)
        finally:
            if inherited_fd is not None:
                os.close(inherited_fd)

        self.assertEqual(received, [samples])

    def test_session_error_closes_ffmpeg(self):
        self.live.return_value.run.side_effect = TimeoutError(
            "no response"
        )

        with self.assertRaises(TimeoutError):
            publish_av_session(ADDRESS, DID, UUID)

        self.process.stdin.close.assert_called_once()
        self.process.wait.assert_called_once_with(
            timeout=10
        )

    def test_ffmpeg_timeout_kills_process(self):
        self.process.wait.side_effect = [
            subprocess.TimeoutExpired(
                cmd="ffmpeg", timeout=10
            ),
            0,
        ]

        publish_av_session(ADDRESS, DID, UUID)

        self.process.kill.assert_called_once()
        self.assertEqual(
            self.process.wait.call_count, 2
        )

    def test_invalid_duration_does_not_start_ffmpeg(self):
        with self.assertRaises(ValueError):
            publish_av_session(
                ADDRESS, DID, UUID, duration=0
            )

        self.popen.assert_not_called()

    def test_ffmpeg_start_failure(self):
        self.popen.side_effect = OSError(
            "FFmpeg unavailable"
        )

        with self.assertRaises(OSError):
            publish_av_session(ADDRESS, DID, UUID)


if __name__ == "__main__":
    unittest.main()


class AVAudioBackpressureTests(unittest.TestCase):
    def test_full_audio_pipe_does_not_interrupt_session(self):
        with patch("tosee_b.av_publisher.os.set_blocking"), \
             patch("tosee_b.av_publisher.os.write", side_effect=BlockingIOError), \
             patch("tosee_b.av_publisher.ToSeeBLive") as live, \
             patch("tosee_b.av_publisher.subprocess.Popen") as popen:

            popen.return_value.poll.return_value = None
            live.return_value.run.side_effect = lambda duration: (
                live.call_args.kwargs["on_audio"](bytes([0xD5]) * 320),
                "stats",
            )[1]

            with self.assertRaisesRegex(
                RuntimeError, "FFmpeg AV writer failed during shutdown"
            ):
                publish_av_session(
                    ADDRESS, DID, UUID, duration=5
                )


class AVVideoPartialWriteTests(unittest.TestCase):
    def test_partial_h264_write_preserves_all_bytes(self):
        data = b"\x00\x00\x00\x01\x65\x11\x22\x33"
        received = bytearray()

        def write_mock(fd, chunk):
            part = bytes(chunk[:3])
            received.extend(part)
            return len(part)

        with patch("tosee_b.av_publisher.ToSeeBLive") as live, \
             patch("tosee_b.av_publisher.subprocess.Popen") as popen, \
             patch("tosee_b.av_publisher.os.write",
                   side_effect=write_mock):

            popen.return_value.poll.return_value = None

            def run_session(duration):
                live.call_args.kwargs["on_h264"](data)
                return "stats"

            live.return_value.run.side_effect = run_session

            result = publish_av_session(
                ADDRESS, DID, UUID, duration=5
            )

        self.assertEqual(result, "stats")
        self.assertEqual(bytes(received), data)
