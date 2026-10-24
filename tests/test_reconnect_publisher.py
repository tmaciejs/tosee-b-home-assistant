import unittest
from unittest.mock import Mock, patch

from tosee_b.publisher import publish_session
from tosee_b.reconnect import run_with_reconnect


class ReconnectPublisherTests(unittest.TestCase):

    def test_new_session_after_failure(self):
        attempts = []
        state = {"stop": False}

        def session_factory():
            session = Mock()

            def run():
                attempts.append(len(attempts) + 1)

                if len(attempts) == 1:
                    raise TimeoutError("Temporary connection failure")

                state["stop"] = True

            session.run.side_effect = run
            return session

        with patch("tosee_b.reconnect.time.sleep") as sleep:
            count = run_with_reconnect(
                session_factory,
                lambda: state["stop"],
                retry_delay=0.1,
            )

        self.assertEqual(count, 2)
        self.assertEqual(attempts, [1, 2])
        sleep.assert_called_once_with(0.1)

    def test_publisher_created_for_each_attempt(self):
        calls = []
        state = {"stop": False}

        def session_factory():
            session = Mock()

            def run():
                calls.append("publish")

                if len(calls) == 1:
                    raise TimeoutError("Connection lost")

                state["stop"] = True

            session.run.side_effect = run
            return session

        with patch("tosee_b.reconnect.time.sleep"):
            count = run_with_reconnect(
                session_factory,
                lambda: state["stop"],
                retry_delay=0,
            )

        self.assertEqual(count, 2)
        self.assertEqual(calls, ["publish", "publish"])


if __name__ == "__main__":
    unittest.main()
