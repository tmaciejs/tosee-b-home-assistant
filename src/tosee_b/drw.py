# SPDX-License-Identifier: GPL-3.0-or-later
"""Parse encrypted ToSee-B PPCS DRW messages."""

from .crypto import decrypt_packet, is_valid_ppcs_packet


def parse_drw_packet(packet: bytes):
    """Return (channel, sequence, data), or None for invalid/non-DRW packets."""
    if not isinstance(packet, bytes):
        return None

    plain = decrypt_packet(packet)

    if (
        not is_valid_ppcs_packet(plain)
        or len(plain) < 8
        or plain[1] != 0xD0
        or plain[4] != 0xD1
    ):
        return None

    channel = plain[5]
    sequence = int.from_bytes(plain[6:8], "big")
    data = plain[8:]

    return channel, sequence, data
