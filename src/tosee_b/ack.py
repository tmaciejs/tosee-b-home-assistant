# SPDX-License-Identifier: GPL-3.0-or-later
"""ToSee-B PPCS DRW acknowledgement construction."""

import struct

from .crypto import encrypt_packet


def build_drw_ack(channel: int, sequences: list[int]) -> bytes:
    """Build an encrypted DRW_ACK, preserving duplicate sequence numbers."""
    if not isinstance(channel, int) or not 0 <= channel <= 255:
        raise ValueError("Channel must be between 0 and 255")

    if not sequences or len(sequences) > 32765:
        raise ValueError("Invalid number of acknowledgements")

    if any(
        not isinstance(seq, int) or not 0 <= seq <= 65535
        for seq in sequences
    ):
        raise ValueError("Sequence numbers must be 16-bit unsigned integers")

    payload = struct.pack(">BBH", 0xD1, channel, len(sequences))
    payload += b"".join(struct.pack(">H", seq) for seq in sequences)

    header = struct.pack(">BBH", 0xF1, 0xD1, len(payload))
    return encrypt_packet(header + payload)
