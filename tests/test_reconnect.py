import unittest
from unittest.mock import Mock, patch

from tosee_b.reconnect import run_with_reconnect


class ReconnectTests(unittest.TestCase):

    def test_one_session_then_stop(self):
        state = {"checks": 0}
        factory = Mock()

        def should_stop():
            state["checks"] += 1
            return state["checks"] >= 2

        attempts = run_with_reconnect(factory, should_stop)
        self.assertEqual(attempts, 1)
        factory.return_value.run.assert_called_once()

    def test_reconnect_after_failure(self):
        factory = Mock()
        factory.return_value.run.side_effect = [
            TimeoutError("temporary failure"),
            None,
        ]
        state = {"checks": 0}

        def should_stop():
            state["checks"] += 1
            return state["checks"] >= 5

        with patch("tosee_b.reconnect.time.sleep"):
            attempts = run_with_reconnect(
                factory, should_stop, retry_delay=0.1
            )

        self.assertEqual(attempts, 2)
        self.assertEqual(factory.call_count, 2)

    def test_negative_delay(self):
        with self.assertRaises(ValueError):
            run_with_reconnect(Mock(), lambda: True, -1)


if __name__ == "__main__":
    unittest.main()
