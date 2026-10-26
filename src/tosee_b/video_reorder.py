# SPDX-License-Identifier: GPL-3.0-or-later
"""Reorder ToSee-B video packets by their 16-bit sequence numbers."""


class VideoReorderBuffer:
    """Buffer out-of-order packets until the missing sequence arrives."""

    SEQUENCE_MODULUS = 65536

    def __init__(self, window_size=16, initial_sequence=None):
        if not 1 <= window_size < 32768:
            raise ValueError("window_size must be between 1 and 32767")

        self.window_size = window_size
        self.expected_sequence = initial_sequence
        self._pending = {}

    @property
    def has_gap(self):
        """Whether pending packets are blocked by a missing sequence."""
        return bool(self._pending)

    def gap_expired(self, now, timeout, gap_started_at):
        """Check whether a pending sequence gap has timed out."""
        if timeout < 0:
            raise ValueError("timeout must not be negative")

        return (
            self.has_gap
            and now - gap_started_at >= timeout
        )

    def discard_gap(self):
        """Discard pending packets and restart sequence tracking."""
        self._pending.clear()
        self.expected_sequence = None

    def push(self, sequence, payload):
        """Return payloads available in their correct sequence order."""
        if not 0 <= sequence < self.SEQUENCE_MODULUS:
            raise ValueError("Invalid video packet sequence")

        if self.expected_sequence is None:
            self.expected_sequence = sequence

        distance = (
            sequence - self.expected_sequence
        ) % self.SEQUENCE_MODULUS

        # A packet behind the expected sequence is stale or duplicated.
        if distance >= 32768:
            return []

        # Keep memory bounded. A larger gap needs separate recovery logic.
        if distance >= self.window_size:
            return []

        if sequence not in self._pending:
            self._pending[sequence] = payload

        ready = []

        while self.expected_sequence in self._pending:
            ready.append(
                self._pending.pop(self.expected_sequence)
            )
            self.expected_sequence = (
                self.expected_sequence + 1
            ) % self.SEQUENCE_MODULUS

        return ready
