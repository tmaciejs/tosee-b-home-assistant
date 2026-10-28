# SPDX-License-Identifier: GPL-3.0-or-later
"""Experimental ToSee-B session lifecycle control."""

from .commands import build_drw_packet
from .crypto import encrypt_packet


def build_close_packets(start_sequence: int) -> tuple[bytes, bytes, bytes]:
    """Build the observed 04 -> 06 -> F0 shutdown sequence.

    The caller must supply the next unused channel-zero sequence number.
    This function does not transmit packets.
    """
    if not isinstance(start_sequence, int):
        raise TypeError("Sequence must be an integer")

    if not 0 <= start_sequence <= 0xFFFF:
        raise ValueError("Invalid DRW sequence")

    close_video = build_drw_packet(start_sequence, 4)
    close_control = build_drw_packet((start_sequence + 1) & 0xFFFF, 6)
    close_ppcs = encrypt_packet(bytes.fromhex("f1f00000"))

    return close_video, close_control, close_ppcs


def close_session(sock, address, start_sequence: int, timeout=0.5) -> bool:
    """Send observed shutdown commands and wait briefly for PPCS F0."""
    import socket
    import time

    from .crypto import decrypt_packet

    if timeout <= 0:
        raise ValueError("Timeout must be positive")

    packets = build_close_packets(start_sequence)

    deadline = time.monotonic() + timeout

    try:
        for packet in packets:
            sock.sendto(packet, address)

        while time.monotonic() < deadline:
            sock.settimeout(max(0.001, deadline - time.monotonic()))

            try:
                packet, sender = sock.recvfrom(65535)
            except socket.timeout:
                break

            if sender != address:
                continue

            if decrypt_packet(packet) == b"\xf1\xf0\x00\x00":
                return True

    except OSError:
        return False

    return False


class ControlSequence:
    """Allocate channel-zero DRW sequences within one session."""

    def __init__(self, start=4):
        if not isinstance(start, int) or not 0 <= start <= 0xFFFF:
            raise ValueError("Invalid initial sequence")
        self._next = start

    def next(self):
        sequence = self._next
        self._next = (self._next + 1) & 0xFFFF
        return sequence
