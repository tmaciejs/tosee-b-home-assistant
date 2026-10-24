import unittest
from unittest.mock import patch

from tosee_b.runner import load_config, run_forever


ENV = {
    "TOSEE_HOST": "192.0.2.10",
    "TOSEE_DID_HEX": "41" * 20,
    "TOSEE_CLIENT_UUID": "12345678-1234-4234-8234-123456789abc",
}


class RunnerTests(unittest.TestCase):

    def test_load_config(self):
        config = load_config(ENV)
        self.assertEqual(config.address, ("192.0.2.10", 10000))
        self.assertEqual(config.did, b"A" * 20)

    def test_invalid_did(self):
        with self.assertRaises(ValueError):
            load_config({**ENV, "TOSEE_DID_HEX": "00"})

    def test_missing_config(self):
        with self.assertRaises(ValueError):
            load_config({})

    def test_invalid_port(self):
        with self.assertRaises(ValueError):
            load_config({**ENV, "TOSEE_PORT": "70000"})

    def test_runner_calls_publisher(self):
        config = load_config(ENV)
        state = {"stop": False}

        def fake_publish(**kwargs):
            self.assertEqual(kwargs["did"], b"A" * 20)
            self.assertEqual(kwargs["duration"], 5)
            state["stop"] = True

        with patch("tosee_b.runner.publish_session",
                   side_effect=fake_publish) as publisher:
            attempts = run_forever(
                config,
                lambda: state["stop"],
                retry_delay=0,
                session_duration=5,
            )

        self.assertEqual(attempts, 1)
        publisher.assert_called_once()


if __name__ == "__main__":
    unittest.main()
