# SPDX-License-Identifier: GPL-3.0-or-later
"""Minimal UDP transport for the ToSee-B PPCS PUNCH handshake."""

import socket
import time

from .punch import build_punch_packet, validate_punch_ack


def perform_punch(sock, address: tuple[str, int], did: bytes,
                  timeout: float = 2.0, retries: int = 3) -> bool:
    """Send PUNCH and verify PUNCH_ACK within a bounded time per attempt."""
    if not isinstance(address, tuple) or len(address) != 2:
        raise ValueError("Address must be an (IPv4, port) tuple")
    if not isinstance(address[1], int) or not 1 <= address[1] <= 65535:
        raise ValueError("Invalid destination UDP port")
    if timeout <= 0:
        raise ValueError("Timeout must be positive")
    if not isinstance(retries, int) or not 1 <= retries <= 10:
        raise ValueError("Retries must be between 1 and 10")

    packet = build_punch_packet(did)

    for _ in range(retries):
        deadline = time.monotonic() + timeout
        sock.sendto(packet, address)

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break

            sock.settimeout(remaining)

            try:
                response, sender = sock.recvfrom(65535)
            except socket.timeout:
                break

            if sender == address and validate_punch_ack(response, did):
                return True

    return False
