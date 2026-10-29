# SPDX-License-Identifier: GPL-3.0-or-later
"""Experimental ToSee-B LIVE session lifecycle."""

import time

from .av_publisher_v14 import SafeToSeeBLive
from .session_control import ControlSequence, close_session


class ExperimentalToSeeBLive(SafeToSeeBLive):
    """LIVE session with the observed 04 -> 06 -> F0 shutdown."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.control_sequence = ControlSequence(start=4)
        from .talk_controller import TalkController
        from .talkback import AudioFrameSender, AudioFrameQueue
        self.talk_controller = TalkController(self.sock, self.address, self.control_sequence)
        self.audio_sender = AudioFrameSender(self.sock, self.address)
        self.audio_queue = AudioFrameQueue(max_frames=10)
        self.talk_started_at = None
        self.talk_session = None

    def bind_talk_session(self, session):
        """Attach shared talk state; UDP remains owned by LIVE thread."""
        self.talk_session = session
        session.attach_live(self)

    def _sync_talk_request(self):
        """Apply shared talk requests in the LIVE receiver thread."""
        session = self.talk_session
        if session is None:
            return

        requested = session.should_talk(self)
        state = self.talk_controller.state

        if not requested:
            if state in ("starting", "active"):
                self.audio_sender.stop()
                self.audio_queue.clear()
                self.talk_controller.stop()
        elif state == "idle":
            self.talk_controller.start()

    def run(self, duration=10.0):
        """Always detach talk state, including on PUNCH failure."""
        try:
            return super().run(duration=duration)
        finally:
            if self.talk_session is not None:
                self.talk_session.detach_live(self)

    def _exchange(self, sequence, packet, timeout=4.0, retries=3):
        """Mark LIVE ready only after the final control exchange."""
        result = super()._exchange(
            sequence, packet, timeout=timeout, retries=retries
        )
        if sequence == 3 and self.talk_session is not None:
            self.talk_session.set_live_ready(self)
        return result

    def _close_session(self, timeout=0.5):
        """Close with 04, 06 and F0 using the existing UDP socket."""
        if self.talk_session is not None:
            self.talk_session.detach_live(self)
        try:
            return self._close_talkback_and_live(timeout)
        finally:
            self.audio_sender.stop()
            self.audio_queue.clear()

    def _close_talkback_and_live(self, timeout=0.5):
        """Perform the existing experimental shutdown sequence."""
        self.audio_sender.stop()
        self.audio_queue.clear()
        self.talk_started_at = None
        if self.talk_controller.state in ("starting", "active"):
            self.talk_controller.stop()
        if self.talk_controller.state == "stopping":
            deadline = time.monotonic() + 0.5
            while self.talk_controller.state == "stopping" and time.monotonic() < deadline:
                try:
                    self._receive(min(0.02, max(0.001, deadline - time.monotonic())))
                except (OSError, TimeoutError, ValueError):
                    break
        start_sequence = self.control_sequence.next()
        self.control_sequence.next()

        return close_session(
            self.sock,
            self.address,
            start_sequence,
            timeout=timeout,
        )

    def _handle_talkback_packet(self, packet):
        """Forward control and audio acknowledgements to talkback."""
        from .session import parse_drw_ack
        from .drw import parse_drw_packet

        ack = parse_drw_ack(packet)
        if ack is not None:
            channel, sequences = ack

            if hasattr(self, "talk_controller"):
                self.talk_controller.accept_ack(channel, sequences)

            if hasattr(self, "audio_sender"):
                self.audio_sender.acks.accept_ack(channel, sequences)

        drw = parse_drw_packet(packet)
        if drw is not None and hasattr(self, "talk_controller"):
            channel, sequence, payload = drw
            self.talk_controller.accept_response(
                channel, sequence, payload
            )

    def _receive(self, timeout):
        """Receive UDP and service talkback on the same session."""
        controller = getattr(self, "talk_controller", None)

        if controller is not None and controller.state in (
            "starting", "active", "stopping"
        ):
            timeout = min(timeout, 0.02)

        packet = super()._receive(timeout)

        if packet is not None:
            self._handle_talkback_packet(packet)

        if controller is not None:
            self._sync_talk_request()
            self._talkback_tick(time.monotonic())

        return packet

    def _talkback_tick(self, now):
        """Advance talkback without blocking the video receiver."""
        if not hasattr(self, "talk_controller"):
            return False

        self.talk_controller.check_timeout(now)

        if self.talk_controller.state != "active":
            if hasattr(self, "audio_sender"):
                self.audio_sender.stop()
            self.talk_started_at = None
            if self.talk_controller.state in ("idle", "stopping", "error"):
                self.audio_queue.clear()
            return False

        if not hasattr(self, "audio_sender") or not hasattr(self, "audio_queue"):
            return False

        if self.talk_started_at is None:
            self.talk_started_at = now

        if now - self.talk_started_at >= 15.0:
            if self.talk_session is not None:
                self.talk_session.stop_talk()
            self.audio_sender.stop()
            self.audio_queue.clear()
            self.talk_started_at = None
            self.talk_controller.stop()
            return False

        if self.audio_sender.next_send_time is None:
            self.audio_sender.acks.sent.clear()
            self.audio_sender.acks.acknowledged.clear()
            self.audio_sender.start(now)

        if now + 0.000001 < self.audio_sender.next_send_time:
            return False

        frame = self.audio_queue.get_nowait()
        if frame is None:
            return False

        sent = self.audio_sender.send_if_due(frame, now)
        if sent:
            count = getattr(self, "_tosee_sent_count", 0) + 1
            self._tosee_sent_count = count
            if count == 1 or count % 50 == 0:
                print(f"TALK_DOORBELL_FRAMES={count}", flush=True)
        return sent
