"""Thread-safe state shared between doorbell events and LIVE talkback."""

import threading

from .talk_gate import TalkGate


class TalkSession:
    def __init__(self, delay=7.0, clock=None):
        self._lock = threading.Lock()
        self.gate = TalkGate(delay=delay, clock=clock)
        self._client = None
        self._talk_requested = False
        self._talk_deadline = None

    def _expire_talk_locked(self):
        if (
            self._talk_requested
            and self._talk_deadline is not None
            and self.gate.clock() >= self._talk_deadline
        ):
            self._talk_requested = False
            self._talk_deadline = None

    def doorbell_pressed(self):
        with self._lock:
            was_live_ready = self._client is not None and self.gate.live_ready
            self.gate.doorbell_pressed()
            self._talk_requested = False
            self._talk_deadline = None
            if was_live_ready:
                self.gate.set_live_ready(True)

    def attach_live(self, client):
        with self._lock:
            self._client = client
            self.gate.set_live_ready(False)
            self._talk_requested = False

    def set_live_ready(self, client):
        with self._lock:
            if self._client is client:
                self.gate.set_live_ready(True)

    def detach_live(self, client):
        with self._lock:
            if self._client is client:
                self._client = None
                self._talk_requested = False
                self._talk_deadline = None
                self.gate.reset()

    def accept_audio_from_browser(self, frame):
        """Accept browser audio only for the current authorized talk."""
        with self._lock:
            self._expire_talk_locked()
            client = self._client

            if (
                client is None
                or not self._talk_requested
                or not self.gate.can_talk()
                or getattr(
                    getattr(client, "talk_controller", None),
                    "state", None
                ) != "active"
                or not isinstance(frame, bytes)
                or len(frame) != 320
            ):
                return False

            client.audio_queue.put(frame)
            return True

    def talk_status(self):
        """Return the observed talk state, not just the START request."""
        with self._lock:
            self._expire_talk_locked()

            client = self._client

            if client is None or not self.gate.can_talk():
                return "blocked"

            if not self._talk_requested:
                return "idle"

            controller = getattr(client, "talk_controller", None)
            state = getattr(controller, "state", "idle")

            if state == "active":
                return "active"
            if state == "starting":
                return "starting"
            if state in ("error", "stopping"):
                return "unavailable"

            return "pending"

    def request_talk(self):
        with self._lock:
            if self._client is None or not self.gate.can_talk():
                return False
            self._expire_talk_locked()
            if self._talk_requested:
                return False
            self._talk_requested = True
            self._talk_deadline = self.gate.clock() + 15.0
            return True

    def stop_talk(self):
        with self._lock:
            self._talk_requested = False
            self._talk_deadline = None

    def should_talk(self, client):
        with self._lock:
            self._expire_talk_locked()
            return (
                self._client is client
                and self._talk_requested
                and self.gate.can_talk()
            )

    def accept_audio(self, client, frame):
        with self._lock:
            if not (
                self._client is client
                and self._talk_requested
                and self.gate.can_talk()
            ):
                return False

            if not isinstance(frame, bytes) or len(frame) != 320:
                return False

            client.audio_queue.put(frame)
            return True
