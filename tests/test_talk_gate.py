import unittest

from tosee_b.talk_gate import TalkGate


class TalkGateTests(unittest.TestCase):

    def setUp(self):
        self.now = 100.0
        self.gate = TalkGate(
            delay=7.0,
            clock=lambda: self.now,
        )

    def test_no_doorbell(self):
        self.gate.set_live_ready()
        self.assertFalse(self.gate.can_talk())

    def test_before_seven_seconds(self):
        self.gate.doorbell_pressed()
        self.gate.set_live_ready()
        self.now += 6.99
        self.assertFalse(self.gate.can_talk())

    def test_at_seven_seconds(self):
        self.gate.doorbell_pressed()
        self.gate.set_live_ready()
        self.now += 7.0
        self.assertTrue(self.gate.can_talk())

    def test_requires_live_ready(self):
        self.gate.doorbell_pressed()
        self.now += 10.0
        self.assertFalse(self.gate.can_talk())

    def test_second_ring_resets_timer(self):
        self.gate.doorbell_pressed()
        self.gate.set_live_ready()
        self.now += 8.0
        self.assertTrue(self.gate.can_talk())

        self.gate.doorbell_pressed()
        self.assertFalse(self.gate.can_talk())

        self.gate.set_live_ready()
        self.now += 7.0
        self.assertTrue(self.gate.can_talk())

    def test_live_ends(self):
        self.gate.doorbell_pressed()
        self.gate.set_live_ready()
        self.now += 7.0
        self.assertTrue(self.gate.can_talk())

        self.gate.set_live_ready(False)
        self.assertFalse(self.gate.can_talk())

    def test_reset(self):
        self.gate.doorbell_pressed()
        self.gate.set_live_ready()
        self.now += 10.0
        self.gate.reset()
        self.assertFalse(self.gate.can_talk())


if __name__ == "__main__":
    unittest.main()
