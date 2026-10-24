"""Regression tests for sequential ToSee-B UDP ports."""

import unittest
from unittest.mock import patch

from tosee_b.runner import load_config, run_forever


ENV = {
    "TOSEE_HOST": "192.0.2.10",
    "TOSEE_DID_HEX": "41" * 20,
    "TOSEE_CLIENT_UUID": "12345678-1234-4234-8234-123456789abc",
}


class RunnerPortTests(unittest.TestCase):
    def test_sequential_ports_and_shared_socket(self):
        config = load_config(ENV)
        calls = []
        sockets = []

        def fake_publish(**kwargs):
            calls.append(kwargs["address"][1])
            sockets.append(kwargs["sock"])

        with patch(
            "tosee_b.runner.publish_session",
            side_effect=fake_publish,
        ):
            attempts = run_forever(
                config,
                should_stop=lambda: len(calls) >= 3,
                retry_delay=0,
                session_duration=1,
            )

        self.assertEqual(attempts, 3)
        self.assertEqual(calls, [10000, 10001, 10002])
        self.assertIs(sockets[0], sockets[1])
        self.assertIs(sockets[1], sockets[2])
        self.assertEqual(sockets[0].fileno(), -1)

    def test_failure_stops_without_advancing_port(self):
        config = load_config(ENV)
        calls = []

        def fake_publish(**kwargs):
            calls.append(kwargs["address"][1])
            if len(calls) == 2:
                raise TimeoutError("PUNCH failed")

        with patch(
            "tosee_b.runner.publish_session",
            side_effect=fake_publish,
        ):
            attempts = run_forever(
                config,
                should_stop=lambda: False,
                retry_delay=0,
                session_duration=1,
            )

        self.assertEqual(attempts, 2)
        self.assertEqual(calls, [10000, 10001])

    def test_invalid_session_duration(self):
        config = load_config(ENV)
        with self.assertRaises(ValueError):
            run_forever(
                config,
                should_stop=lambda: True,
                session_duration=0,
            )


if __name__ == "__main__":
    unittest.main()
