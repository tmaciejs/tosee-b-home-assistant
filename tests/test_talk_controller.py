import time
import unittest
from unittest.mock import patch

from tosee_b.talk_controller import TalkController
from tosee_b.session_control import ControlSequence


class FakeSocket:
    def __init__(self):
        self.packets = []

    def sendto(self, packet, address):
        self.packets.append((packet, address))


class ControllerTests(unittest.TestCase):

    def setUp(self):
        self.sock = FakeSocket()
        self.sequence = ControlSequence(start=100)
        self.controller = TalkController(
            self.sock,
            ("127.0.0.1", 9999),
            self.sequence,
        )

    def test_start_requires_ack_and_response(self):
        self.controller.start()
        sequence = self.controller.pending_sequence

        self.assertEqual(self.controller.state, "starting")

        self.controller.accept_ack(0, [sequence])
        self.assertEqual(self.controller.state, "starting")

        payload = (
            (0).to_bytes(4, "little") +
            (0).to_bytes(4, "little") +
            (7).to_bytes(4, "little")
        )

        self.controller.accept_response(0, sequence, payload)

        self.assertEqual(self.controller.state, "active")
        print("TEST 1: START + ACK + RESPONSE — OK")

    def test_stop_returns_to_idle(self):
        self.controller.start()
        sequence = self.controller.pending_sequence
        payload_start = (
            (0).to_bytes(4, "little") * 2 +
            (7).to_bytes(4, "little")
        )

        self.controller.accept_ack(0, [sequence])
        self.controller.accept_response(
            0, sequence, payload_start
        )

        self.controller.stop()
        stop_sequence = self.controller.pending_sequence

        payload_stop = (
            (0).to_bytes(4, "little") * 2 +
            (8).to_bytes(4, "little")
        )

        self.controller.accept_ack(0, [stop_sequence])
        self.controller.accept_response(
            0, stop_sequence, payload_stop
        )

        self.assertEqual(self.controller.state, "idle")
        print("TEST 2: STOP + ACK + RESPONSE — OK")

    def test_missing_ack_retries(self):
        self.controller.start()
        start_time = self.controller.last_sent_at

        with patch("tosee_b.talk_controller.time.monotonic",
                   return_value=start_time + 0.81):
            retried = self.controller.check_timeout(
                start_time + 0.81
            )

        self.assertTrue(retried)
        self.assertEqual(len(self.sock.packets), 2)
        print("TEST 3: Ponowienie bez ACK — OK")

    def test_timeout_enters_error(self):
        self.controller.start()
        start_time = self.controller.command_started_at

        with self.assertRaises(TimeoutError):
            self.controller.check_timeout(start_time + 4.01)

        self.assertEqual(self.controller.state, "error")
        print("TEST 4: Timeout START — ERROR wykryty")

    def test_error_cannot_restart(self):
        self.controller.start()
        start_time = self.controller.command_started_at

        with self.assertRaises(TimeoutError):
            self.controller.check_timeout(start_time + 4.01)

        with self.assertRaises(RuntimeError):
            self.controller.start()

        print("TEST 5: Brak odzyskiwania po ERROR — POTWIERDZONY")


if __name__ == "__main__":
    unittest.main(verbosity=2)
