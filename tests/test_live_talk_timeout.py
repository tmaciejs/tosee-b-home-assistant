import unittest
from unittest.mock import Mock

from tosee_b.live_experimental import ExperimentalToSeeBLive


class LiveTalkTimeoutTests(unittest.TestCase):

    def test_talk_timeout_does_not_escape_tick(self):
        live = ExperimentalToSeeBLive.__new__(
            ExperimentalToSeeBLive
        )

        live.talk_controller = Mock()
        live.talk_controller.state = "error"
        live.talk_session = Mock()
        live.talk_controller.check_timeout.side_effect = (
            TimeoutError("ToSee-B talkback control timeout")
        )

        # Docelowo timeout rozmowy powinien być obsłużony
        # przez warstwę LIVE bez niekontrolowanego wyjątku.
        live._talkback_tick(100.0)

        live.talk_controller.check_timeout.assert_called_once_with(
            100.0
        )


if __name__ == "__main__":
    unittest.main()
