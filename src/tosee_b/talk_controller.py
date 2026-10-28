# SPDX-License-Identifier: GPL-3.0-or-later
"""Experimental ToSee-B talkback control state machine."""

import time

from .commands import build_drw_packet
from .talkback import validate_talk_response


class TalkController:
    """Manage START 07 and STOP 08 on an existing session."""

    def __init__(self, sock, address, control_sequence):
        self.sock = sock
        self.address = address
        self.control_sequence = control_sequence
        self.state = "idle"
        self.pending_sequence = None
        self.pending_command = None
        self.ack_received = False
        self.response_received = False
        self.pending_packet = None
        self.command_started_at = None
        self.last_sent_at = None
        self.send_attempts = 0

    def _send_command(self, command):
        sequence = self.control_sequence.next()
        packet = build_drw_packet(sequence, command)

        self.sock.sendto(packet, self.address)
        now = time.monotonic()
        self.pending_packet = packet
        self.command_started_at = now
        self.last_sent_at = now
        self.send_attempts = 1

        self.pending_sequence = sequence
        self.pending_command = command
        self.ack_received = False
        self.response_received = False

    def start(self):
        if self.state != "idle":
            raise RuntimeError("Talkback is not idle")

        self.state = "starting"
        self._send_command(7)

    def stop(self):
        if self.state not in ("starting", "active"):
            return

        self.state = "stopping"
        self._send_command(8)

    def accept_ack(self, channel, sequences):
        if channel != 0 or self.pending_sequence is None:
            return

        if self.pending_sequence in sequences:
            self.ack_received = True
            self._update_state()

    def accept_response(self, channel, sequence, payload):
        if (
            channel != 0
            or sequence != self.pending_sequence
            or self.pending_command is None
        ):
            return

        if validate_talk_response(self.pending_command, payload):
            self.response_received = True
            self._update_state()

    def _update_state(self):
        if not (self.ack_received and self.response_received):
            return

        if self.pending_command == 7:
            self.state = "active"
        elif self.pending_command == 8:
            self.state = "idle"

        self.pending_sequence = None
        self.pending_command = None
        self.pending_packet = None

    def check_timeout(self, now):
        """Retry a pending command or fail after four seconds."""
        if self.pending_sequence is None:
            return False

        if now - self.command_started_at >= 4.0:
            self.state = "error"
            self.pending_sequence = None
            self.pending_command = None
            self.pending_packet = None
            raise TimeoutError("ToSee-B talkback control timeout")

        if (
            not self.ack_received
            and self.send_attempts < 3
            and now - self.last_sent_at + 0.000001 >= 0.8
        ):
            self.sock.sendto(self.pending_packet, self.address)
            self.last_sent_at = now
            self.send_attempts += 1
            return True

        return False
