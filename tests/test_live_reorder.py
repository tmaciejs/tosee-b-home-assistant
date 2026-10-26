"""Tests for packet reordering inside ToSeeBLive."""

import struct
import unittest
from unittest.mock import Mock

from tosee_b.ack import build_drw_ack
from tosee_b.crypto import encrypt_packet
from tosee_b.live import ToSeeBLive


ADDRESS = ("192.0.2.10", 10000)


def make_packet(sequence, payload):
    plain = (
        b"\xf1\xd0"
        + struct.pack(">H", 4 + len(payload))
        + b"\xd1\x01"
        + struct.pack(">H", sequence)
        + payload
    )
    return encrypt_packet(plain)


class LiveReorderTests(unittest.TestCase):

    def test_out_of_order_video_and_ack(self):
        sock = Mock()
        output = []

        client = ToSeeBLive(
            sock=sock,
            address=ADDRESS,
            did=b"A" * 20,
            client_uuid="12345678-1234-4234-8234-123456789abc",
            on_h264=output.append,
        )

        h264 = (
            bytes((0, 0, 0, 1, 0x67))
            + bytes((0, 0, 0, 1, 0x68))
            + bytes((0, 0, 0, 1, 0x65))
            + b"A" * 100
        )

        frame = struct.pack("<IIII", 300, len(h264), 0, 0) + h264

        fragments = (
            frame[:30],
            frame[30:70],
            frame[70:],
        )

        sock.recvfrom.side_effect = [
            (make_packet(100, fragments[0]), ADDRESS),
            (make_packet(102, fragments[2]), ADDRESS),
            (make_packet(101, fragments[1]), ADDRESS),
            (make_packet(102, fragments[2]), ADDRESS),
        ]

        for _ in range(4):
            client._receive(0.1)

        self.assertEqual(output, [h264])
        self.assertEqual(client.stats.output_blocks, 1)
        self.assertEqual(client.stats.video_packets, 4)

        expected_acks = [
            (build_drw_ack(1, [seq]), ADDRESS)
            for seq in (100, 102, 101, 102)
        ]

        self.assertEqual(
            [call.args for call in sock.sendto.call_args_list],
            expected_acks,
        )


if __name__ == "__main__":
    unittest.main()


class LivePermanentGapTests(unittest.TestCase):

    def test_missing_packet_blocks_reorder_buffer(self):
        sock = Mock()

        client = ToSeeBLive(
            sock=sock,
            address=ADDRESS,
            did=b"A" * 20,
            client_uuid="12345678-1234-4234-8234-123456789abc",
            on_h264=Mock(),
        )

        sock.recvfrom.side_effect = [
            (make_packet(100, b"A"), ADDRESS),
            (make_packet(102, b"C"), ADDRESS),
            (make_packet(103, b"D"), ADDRESS),
        ]

        for _ in range(3):
            client._receive(0.1)

        self.assertTrue(client.reorder.has_gap)
        self.assertEqual(client.reorder.expected_sequence, 101)
        self.assertEqual(len(client.reorder._pending), 2)


class LiveGapTimerTests(unittest.TestCase):

    def test_gap_timeout_is_checked_on_socket_timeout(self):
        import socket
        from unittest.mock import patch

        sock = Mock()
        client = ToSeeBLive(
            sock=sock,
            address=ADDRESS,
            did=b"A" * 20,
            client_uuid="12345678-1234-4234-8234-123456789abc",
            on_h264=Mock(),
        )

        partial_frame = (
            struct.pack("<IIII", 500, 105, 0, 0)
            + bytes((0, 0, 0, 1, 0x41))
            + b"A" * 10
        )

        sock.recvfrom.side_effect = [
            (make_packet(100, partial_frame), ADDRESS),
            (make_packet(102, b"C"), ADDRESS),
            socket.timeout,
        ]

        with patch("tosee_b.live.time.monotonic") as clock:
            clock.return_value = 1.0
            client._receive(0.1)
            self.assertGreater(client.parser.buffered_bytes, 0)

            clock.return_value = 1.01
            client._receive(0.1)

            clock.return_value = 1.30
            client._receive(0.1)

        # A timed-out gap should be reported, not silently retained.
        self.assertFalse(client.reorder.has_gap)
        self.assertEqual(client.parser.buffered_bytes, 0)
        self.assertFalse(client.sync.synchronized)
        self.assertTrue(client._video_resync_needed)
        self.assertEqual(client.parser.buffered_bytes, 0)
        self.assertFalse(client.sync.synchronized)
        self.assertTrue(client._video_resync_needed)


class LiveResyncSafetyTests(unittest.TestCase):

    def test_resync_state_does_not_emit_partial_video(self):
        sock = Mock()
        output = Mock()

        client = ToSeeBLive(
            sock=sock,
            address=ADDRESS,
            did=b"A" * 20,
            client_uuid="12345678-1234-4234-8234-123456789abc",
            on_h264=output,
        )

        # Simulate the state after a permanent UDP gap.
        client.reorder.discard_gap()
        client.parser.reset()
        client.sync.reset()
        client._video_resync_needed = True

        # Bytes from the middle of an H.264 frame, without framing.
        sock.recvfrom.return_value = (
            make_packet(200, b"\xff" * 40),
            ADDRESS,
        )

        client._receive(0.1)

        output.assert_not_called()
        self.assertTrue(client._video_resync_needed)


class LiveResyncResumeTests(unittest.TestCase):

    def test_resync_can_resume_on_keyframe(self):
        sock = Mock()
        output = Mock()

        client = ToSeeBLive(
            sock=sock,
            address=ADDRESS,
            did=b"A" * 20,
            client_uuid="12345678-1234-4234-8234-123456789abc",
            on_h264=output,
        )

        client.reorder.discard_gap()
        client.parser.reset()
        client.sync.reset()
        client._video_resync_needed = True

        h264 = (
            bytes((0, 0, 0, 1, 0x67))
            + bytes((0, 0, 0, 1, 0x68))
            + bytes((0, 0, 0, 1, 0x65))
        )
        frame = struct.pack("<IIII", 501, len(h264), 1, 0) + h264

        sock.recvfrom.side_effect = [
            (make_packet(200, b"\xff" * 25), ADDRESS),
            (make_packet(201, frame), ADDRESS),
        ]

        client._receive(0.1)
        client._receive(0.1)

        output.assert_called_once_with(h264)
        self.assertFalse(client._video_resync_needed)


class LiveGapContinuousTrafficTests(unittest.TestCase):

    def test_gap_expires_while_udp_packets_keep_arriving(self):
        from unittest.mock import patch

        sock = Mock()
        output = Mock()

        client = ToSeeBLive(
            sock=sock,
            address=ADDRESS,
            did=b"A" * 20,
            client_uuid="12345678-1234-4234-8234-123456789abc",
            on_h264=output,
        )

        sock.recvfrom.side_effect = [
            (make_packet(100, b"A"), ADDRESS),
            (make_packet(102, b"B"), ADDRESS),
            (make_packet(103, b"C"), ADDRESS),
        ]

        with patch("tosee_b.live.time.monotonic") as clock:
            clock.return_value = 1.00
            client._receive(0.1)

            clock.return_value = 1.01
            client._receive(0.1)
            self.assertTrue(client.reorder.has_gap)

            clock.return_value = 1.30
            client._receive(0.1)

        self.assertFalse(client.reorder.has_gap)
        self.assertEqual(client.parser.buffered_bytes, 1)
        self.assertFalse(client.sync.synchronized)
        self.assertTrue(client._video_resync_needed)
        output.assert_not_called()


class LiveLatePacketTests(unittest.TestCase):

    def test_late_packet_does_not_restore_damaged_video(self):
        import socket
        from unittest.mock import patch

        sock = Mock()
        output = Mock()

        client = ToSeeBLive(
            sock=sock,
            address=ADDRESS,
            did=b"A" * 20,
            client_uuid="12345678-1234-4234-8234-123456789abc",
            on_h264=output,
        )

        sock.recvfrom.side_effect = [
            (make_packet(100, b"A"), ADDRESS),
            (make_packet(102, b"B"), ADDRESS),
            socket.timeout,
            (make_packet(101, b"C"), ADDRESS),
        ]

        with patch("tosee_b.live.time.monotonic") as clock:
            clock.return_value = 1.00
            client._receive(0.1)

            clock.return_value = 1.01
            client._receive(0.1)

            clock.return_value = 1.30
            client._receive(0.1)

            self.assertTrue(client._video_resync_needed)

            clock.return_value = 1.31
            client._receive(0.1)

        output.assert_not_called()
        self.assertTrue(client._video_resync_needed)
        self.assertFalse(client.sync.synchronized)


class LiveLatePacketSequenceTests(unittest.TestCase):

    def test_late_packet_does_not_create_new_gap(self):
        import socket
        from unittest.mock import patch

        sock = Mock()
        client = ToSeeBLive(
            sock=sock,
            address=ADDRESS,
            did=b"A" * 20,
            client_uuid="12345678-1234-4234-8234-123456789abc",
            on_h264=Mock(),
        )

        sock.recvfrom.side_effect = [
            (make_packet(100, b"A"), ADDRESS),
            (make_packet(102, b"B"), ADDRESS),
            socket.timeout,
            (make_packet(101, b"C"), ADDRESS),
            (make_packet(103, b"D"), ADDRESS),
        ]

        with patch("tosee_b.live.time.monotonic") as clock:
            for now in (1.00, 1.01, 1.30, 1.31, 1.32):
                clock.return_value = now
                client._receive(0.1)

        # Spóźniony pakiet 101 nie powinien zablokować 103.
        self.assertFalse(client.reorder.has_gap)
        self.assertTrue(client._video_resync_needed)


class LiveGapWraparoundTests(unittest.TestCase):

    def test_gap_recovery_across_sequence_wraparound(self):
        import socket
        from unittest.mock import patch

        sock = Mock()
        client = ToSeeBLive(
            sock=sock,
            address=ADDRESS,
            did=b"A" * 20,
            client_uuid="12345678-1234-4234-8234-123456789abc",
            on_h264=Mock(),
        )

        sock.recvfrom.side_effect = [
            (make_packet(65533, b"A"), ADDRESS),
            (make_packet(65535, b"B"), ADDRESS),
            socket.timeout,
            (make_packet(65534, b"OLD"), ADDRESS),
            (make_packet(0, b"NEW"), ADDRESS),
        ]

        with patch("tosee_b.live.time.monotonic") as clock:
            for now in (1.00, 1.01, 1.30, 1.31, 1.32):
                clock.return_value = now
                client._receive(0.1)

        self.assertFalse(client.reorder.has_gap)
        self.assertEqual(client.reorder.expected_sequence, 1)
        self.assertTrue(client._video_resync_needed)


class LiveGapClosedBeforeTimeoutTests(unittest.TestCase):

    def test_missing_packet_arrives_before_timeout(self):
        from unittest.mock import patch

        sock = Mock()
        output = Mock()

        client = ToSeeBLive(
            sock=sock,
            address=ADDRESS,
            did=b"A" * 20,
            client_uuid="12345678-1234-4234-8234-123456789abc",
            on_h264=output,
        )

        sock.recvfrom.side_effect = [
            (make_packet(100, b"A"), ADDRESS),
            (make_packet(102, b"C"), ADDRESS),
            (make_packet(101, b"B"), ADDRESS),
        ]

        with patch("tosee_b.live.time.monotonic") as clock:
            for now in (1.00, 1.01, 1.24):
                clock.return_value = now
                client._receive(0.1)

        self.assertFalse(client.reorder.has_gap)
        self.assertIsNone(client._video_gap_started_at)
        self.assertFalse(client._video_resync_needed)
        self.assertEqual(client.reorder.expected_sequence, 103)


class LiveGapClosedAfterTimeoutTests(unittest.TestCase):

    def test_missing_packet_arrives_after_timeout(self):
        from unittest.mock import patch

        sock = Mock()
        client = ToSeeBLive(
            sock=sock,
            address=ADDRESS,
            did=b"A" * 20,
            client_uuid="12345678-1234-4234-8234-123456789abc",
            on_h264=Mock(),
        )

        sock.recvfrom.side_effect = [
            (make_packet(100, b"A"), ADDRESS),
            (make_packet(102, b"C"), ADDRESS),
            (make_packet(101, b"B"), ADDRESS),
        ]

        with patch("tosee_b.live.time.monotonic") as clock:
            clock.return_value = 1.00
            client._receive(0.1)

            clock.return_value = 1.01
            client._receive(0.1)

            clock.return_value = 1.30
            client._receive(0.1)

        self.assertTrue(client._video_resync_needed)
        self.assertFalse(client.sync.synchronized)
        self.assertEqual(client.parser.buffered_bytes, 0)
