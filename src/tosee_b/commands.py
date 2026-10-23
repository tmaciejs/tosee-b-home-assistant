# SPDX-License-Identifier: GPL-3.0-or-later
"""ToSee-B PPCS channel-zero control message construction."""

import struct

from .crypto import encrypt_packet


def build_control_command(command: int) -> bytes:
    """Build the observed eight-byte control command."""
    if not 0 <= command <= 0xFFFFFFFF:
        raise ValueError("Command must be a 32-bit unsigned integer")
    return struct.pack("<II", command, 0)


def build_drw_packet(sequence: int, command: int) -> bytes:
    """Build and encrypt a PPCS DRW message on channel zero."""
    if not 0 <= sequence <= 0xFFFF:
        raise ValueError("Sequence must be a 16-bit unsigned integer")

    channel_data = struct.pack(">BBH", 0xD1, 0, sequence)
    payload = channel_data + build_control_command(command)
    header = struct.pack(">BBH", 0xF1, 0xD0, len(payload))
    return encrypt_packet(header + payload)
