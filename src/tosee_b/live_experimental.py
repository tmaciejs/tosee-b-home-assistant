# SPDX-License-Identifier: GPL-3.0-or-later
"""Experimental ToSee-B LIVE session lifecycle."""

from .av_publisher_v14 import SafeToSeeBLive
from .session_control import ControlSequence, close_session


class ExperimentalToSeeBLive(SafeToSeeBLive):
    """LIVE session with the observed 04 -> 06 -> F0 shutdown."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.control_sequence = ControlSequence(start=4)

    def _close_session(self, timeout=0.5):
        """Close with 04, 06 and F0 using the existing UDP socket."""
        start_sequence = self.control_sequence.next()
        self.control_sequence.next()

        return close_session(
            self.sock,
            self.address,
            start_sequence,
            timeout=timeout,
        )
