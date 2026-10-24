"""Tests for caller-owned UDP sockets in RTSP publishing."""

import socket
import unittest
from unittest.mock import MagicMock, patch

from tosee_b.publisher import publish_session


class SharedSocketTests(unittest.TestCase):
    def test_shared_socket_is_reused_and_not_closed(self):
        address = ("192.0.2.10", 10001)
        shared_sock = MagicMock(spec=socket.socket)
        expected_stats = object()

        with (
            patch("tosee_b.publisher.subprocess.Popen") as popen,
            patch("tosee_b.publisher.ToSeeBLive") as live_class,
            patch("tosee_b.publisher.socket.socket") as socket_factory,
        ):
            process = popen.return_value
            process.poll.return_value = None
            process.stdin = MagicMock()

            live_class.return_value.run.return_value = expected_stats

            result = publish_session(
                address=address,
                did=b"\\x00" * 20,
                client_uuid="test-client",
                duration=1.0,
                sock=shared_sock,
            )

            self.assertIs(result, expected_stats)
            self.assertIs(
                live_class.call_args.kwargs["sock"],
                shared_sock,
            )
            self.assertEqual(
                live_class.call_args.kwargs["address"],
                address,
            )
            socket_factory.assert_not_called()
            shared_sock.close.assert_not_called()
            live_class.return_value.run.assert_called_once_with(
                duration=1.0
            )


if __name__ == "__main__":
    unittest.main()
