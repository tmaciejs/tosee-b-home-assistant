"""Time gate for ToSee-B doorbell talkback."""

import time


class TalkGate:
    """Allow talkback no earlier than 7 seconds after a ring."""

    def __init__(self, delay=7.0, clock=None):
        if delay < 0:
            raise ValueError("delay must be nonnegative")
        self.delay = delay
        self.clock = clock or time.monotonic
        self.ring_at = None
        self.live_ready = False

    def doorbell_pressed(self):
        self.ring_at = self.clock()
        self.live_ready = False

    def set_live_ready(self, ready=True):
        self.live_ready = bool(ready)

    def can_talk(self):
        return (
            self.ring_at is not None
            and self.live_ready
            and self.clock() - self.ring_at >= self.delay
        )

    def reset(self):
        self.ring_at = None
        self.live_ready = False
