# SPDX-License-Identifier: GPL-3.0-or-later
"""Offline ToSee-B talkback packet construction."""

import struct

from .crypto import encrypt_packet

AUDIO_SAMPLES = 320
AUDIO_HEADER_SUFFIX = bytes.fromhex("4001000000000000")


def build_audio_packet(
    drw_sequence: int,
    audio_sequence: int,
    alaw_samples: bytes,
) -> bytes:
    """Build an encrypted PPCS channel-3 audio packet."""

    if not 0 <= drw_sequence <= 0xFFFF:
        raise ValueError("Invalid DRW sequence")

    if not 0 <= audio_sequence <= 0xFFFFFFFF:
        raise ValueError("Invalid audio sequence")

    if not isinstance(alaw_samples, bytes):
        raise TypeError("Audio samples must be bytes")

    if len(alaw_samples) != AUDIO_SAMPLES:
        raise ValueError("Audio frame must contain 320 bytes")

    audio_header = (
        struct.pack("<I", audio_sequence)
        + AUDIO_HEADER_SUFFIX
    )

    drw = struct.pack(">BBH", 0xD1, 3, drw_sequence)
    payload = drw + audio_header + alaw_samples
    header = struct.pack(">BBH", 0xF1, 0xD0, len(payload))

    return encrypt_packet(header + payload)


def validate_talk_response(command: int, payload: bytes) -> bool:
    """Validate a channel-zero response to talkback start/stop."""
    if command not in (7, 8):
        return False

    if not isinstance(payload, bytes):
        return False

    return payload == struct.pack("<III", 0, 0, command)


class AudioAckTracker:
    """Track acknowledged outgoing audio frames on DRW channel 3."""

    def __init__(self):
        self.sent = set()
        self.acknowledged = set()

    def mark_sent(self, sequence: int):
        if not 0 <= sequence <= 0xFFFF:
            raise ValueError("Invalid DRW sequence")
        self.sent.add(sequence)

    def accept_ack(self, channel: int, sequences):
        if channel != 3:
            return

        for sequence in sequences:
            if sequence in self.sent:
                self.acknowledged.add(sequence)

    @property
    def pending(self):
        return self.sent - self.acknowledged

    @property
    def complete(self):
        return bool(self.sent) and not self.pending
