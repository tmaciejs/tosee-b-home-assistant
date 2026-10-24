# SPDX-License-Identifier: GPL-3.0-or-later
"""ToSee-B PPCS direct connection handshake."""

import struct

from .crypto import encrypt_packet, decrypt_packet, is_valid_ppcs_packet


def build_punch_packet(did: bytes) -> bytes:
    """Build the encrypted PUNCH packet with a 20-byte encoded DID."""
    if not isinstance(did, bytes) or len(did) != 20:
        raise ValueError("DID must be exactly 20 bytes")

    plain = struct.pack(">BBH", 0xF1, 0x41, 20) + did
    return encrypt_packet(plain)


def validate_punch_ack(packet: bytes, expected_did: bytes) -> bool:
    """Verify an encrypted PUNCH_ACK and its echoed DID."""
    if not isinstance(expected_did, bytes) or len(expected_did) != 20:
        raise ValueError("DID must be exactly 20 bytes")

    try:
        plain = decrypt_packet(packet)
    except (ValueError, TypeError, IndexError):
        return False

    return (
        len(plain) == 24
        and is_valid_ppcs_packet(plain)
        and plain[1] == 0x42
        and plain[4:] == expected_did
    )
