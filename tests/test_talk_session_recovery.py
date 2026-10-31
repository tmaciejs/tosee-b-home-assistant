import unittest

from tosee_b.talk_session import TalkSession


class FakeController:
    def __init__(self):
        self.state = "idle"


class FakeLive:
    def __init__(self):
        self.talk_controller = FakeController()


class TalkSessionRecoveryTests(unittest.TestCase):
    def test_expired_talk_must_not_restart_active_controller(self):
        now = [100.0]
        session = TalkSession(delay=4.0, clock=lambda: now[0])
        live = FakeLive()

        session.doorbell_pressed()
        session.attach_live(live)
        session.set_live_ready(live)

        now[0] = 105.0
        self.assertTrue(session.request_talk())

        live.talk_controller.state = "active"
        now[0] = 121.0

        self.assertNotEqual(session.talk_status(), "idle")
        self.assertFalse(session.request_talk())


if __name__ == "__main__":
    unittest.main()
