# SPDX-License-Identifier: GPL-3.0-or-later
"""ToSee-B PPCS channel-zero initialization helpers."""

import struct

from .crypto import encrypt_packet, decrypt_packet, is_valid_ppcs_packet
from .commands import build_init_command


def build_init_drw_packet(client_uuid: str) -> bytes:
    """Build encrypted channel-zero initialization DRW with seq=0."""
    data = build_init_command(client_uuid)
    payload = struct.pack(">BBH", 0xD1, 0, 0) + data
    return encrypt_packet(struct.pack(">BBH", 0xF1, 0xD0, len(payload)) + payload)


def parse_drw_ack(packet: bytes):
    """Return (channel, sequences) for a valid encrypted DRW_ACK, else None."""
    if not isinstance(packet, bytes):
        return None

    plain = decrypt_packet(packet)
    if (
        not is_valid_ppcs_packet(plain)
        or len(plain) < 8
        or plain[1] != 0xD1
        or plain[4] != 0xD1
    ):
        return None

    channel = plain[5]
    count = int.from_bytes(plain[6:8], "big")

    if len(plain) != 8 + 2 * count:
        return None

    sequences = [
        int.from_bytes(plain[8 + i*2:10 + i*2], "big")
        for i in range(count)
    ]
    return channel, sequences


class InitResponseTracker:
    """Track ACK and DRW response independently, in either arrival order."""

    def __init__(self):
        self.ack_received = False
        self.response_received = False

    def accept(self, packet: bytes) -> bool:
        """Record a matching seq=0 message. Return True when recognized."""
        from .drw import parse_drw_packet

        ack = parse_drw_ack(packet)
        if ack is not None:
            channel, sequences = ack
            if channel == 0 and 0 in sequences:
                self.ack_received = True
                return True
            return False

        drw = parse_drw_packet(packet)
        if drw is not None:
            channel, sequence, _data = drw
            if channel == 0 and sequence == 0:
                self.response_received = True
                return True

        return False

    @property
    def complete(self):
        return self.ack_received and self.response_received
