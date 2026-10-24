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


def build_init_command(client_uuid: str) -> bytes:
    """Build the observed 184-byte ToSee-B initialization payload.

    The UUID identifies the captured client; its exact role is unconfirmed.
    """
    import uuid

    parsed = uuid.UUID(client_uuid)
    if str(parsed) != client_uuid.lower():
        raise ValueError("UUID must use the canonical 36-character format")

    payload = bytearray(184)
    struct.pack_into("<II", payload, 0, 0, 176)

    payload[0x0C:0x0E] = b"11"
    payload[0x12:0x17] = b"1.0.0"
    payload[0x32:0x56] = client_uuid.lower().encode("ascii")

    return bytes(payload)
