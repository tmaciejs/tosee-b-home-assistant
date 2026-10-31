import unittest
from unittest.mock import MagicMock, patch

from tosee_b.av_publisher_v14 import publish_av_session


class PublisherV14CleanupTests(unittest.TestCase):

    def test_live_error_closes_resources(self):
        process = MagicMock()
        process.stdin.fileno.return_value = 123
        process.poll.return_value = None

        socket_context = MagicMock()
        sock = socket_context.__enter__.return_value

        class FailingLive:
            def __init__(self, **kwargs):
                pass

            def run(self, duration):
                raise TimeoutError("SIMULATED_LIVE_ERROR")

        with patch(
            "tosee_b.av_publisher_v14.subprocess.Popen",
            return_value=process,
        ), patch(
            "tosee_b.av_publisher_v14.socket.socket",
            return_value=socket_context,
        ), patch(
            "tosee_b.av_publisher_v14.os.set_blocking",
        ), patch(
            "tosee_b.av_publisher_v14.av.open",
        ) if False else patch(
            "av.open"
        ) as av_open:

            output = av_open.return_value.__enter__.return_value
            output.add_stream.return_value = MagicMock()

            with self.assertRaisesRegex(
                TimeoutError, "SIMULATED_LIVE_ERROR"
            ):
                publish_av_session(
                    address=("127.0.0.1", 9999),
                    did="test",
                    client_uuid="test",
                    duration=1.0,
                    client_class=FailingLive,
                )

        sock.bind.assert_called_once()
        socket_context.__exit__.assert_called_once()
        process.stdin.close.assert_called_once()
        process.wait.assert_called()

        print("SOCKET_CLOSED: True")
        print("FFMPEG_CLEANED: True")


if __name__ == "__main__":
    unittest.main()
