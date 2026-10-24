import unittest
from unittest.mock import MagicMock, patch

from tosee_b.publisher import publish_session


ADDRESS = ("192.0.2.10", 10000)
DID = b"A" * 20
UUID = "12345678-1234-4234-8234-123456789abc"


class PublisherTests(unittest.TestCase):

    def setUp(self):
        self.process = MagicMock()
        self.process.poll.return_value = None

        self.socket = MagicMock()
        self.socket_context = MagicMock()
        self.socket_context.__enter__.return_value = self.socket

        self.popen_patch = patch(
            "tosee_b.publisher.subprocess.Popen",
            return_value=self.process,
        )
        self.socket_patch = patch(
            "tosee_b.publisher.socket.socket",
            return_value=self.socket_context,
        )
        self.live_patch = patch("tosee_b.publisher.ToSeeBLive")

        self.popen = self.popen_patch.start()
        self.socket_factory = self.socket_patch.start()
        self.live = self.live_patch.start()

        self.addCleanup(self.popen_patch.stop)
        self.addCleanup(self.socket_patch.stop)
        self.addCleanup(self.live_patch.stop)

    def test_successful_session(self):
        self.live.return_value.run.return_value = "stats"

        result = publish_session(ADDRESS, DID, UUID, duration=5)

        self.assertEqual(result, "stats")
        self.live.return_value.run.assert_called_once_with(duration=5)
        self.socket.bind.assert_called_once_with(("0.0.0.0", 0))
        self.process.stdin.close.assert_called_once()
        self.process.wait.assert_called_once_with(timeout=10)

    def test_h264_written_to_ffmpeg(self):
        self.live.return_value.run.return_value = None

        publish_session(ADDRESS, DID, UUID)
        callback = self.live.call_args.kwargs["on_h264"]
        callback(b"\x00\x00\x00\x01\x65")

        self.process.stdin.write.assert_called_once_with(
            b"\x00\x00\x00\x01\x65"
        )

    def test_session_error_closes_ffmpeg(self):
        self.live.return_value.run.side_effect = TimeoutError("no response")

        with self.assertRaises(TimeoutError):
            publish_session(ADDRESS, DID, UUID)

        self.process.stdin.close.assert_called_once()
        self.process.wait.assert_called_once_with(timeout=10)

    def test_ffmpeg_timeout_kills_process(self):
        import subprocess

        self.process.wait.side_effect = [
            subprocess.TimeoutExpired(cmd="ffmpeg", timeout=10),
            0,
        ]

        publish_session(ADDRESS, DID, UUID)

        self.process.kill.assert_called_once()
        self.assertEqual(self.process.wait.call_count, 2)

    def test_invalid_duration_does_not_start_ffmpeg(self):
        with self.assertRaises(ValueError):
            publish_session(ADDRESS, DID, UUID, duration=0)

        self.popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
