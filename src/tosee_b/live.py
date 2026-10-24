"""Direct LAN video session for ToSee-B.

The caller supplies a connected-network UDP socket, the device address,
DID, client UUID and a callback receiving synchronized Annex B H.264.
No credentials, device identifiers or video are stored by this module.
"""

import json
import socket
import struct
import time
from dataclasses import dataclass

from .ack import build_drw_ack
from .commands import build_drw_packet
from .crypto import encrypt_packet
from .drw import parse_drw_packet
from .session import build_init_drw_packet, parse_drw_ack
from .transport import perform_punch
from .video import H264Sync, VideoFrameParser


@dataclass
class LiveStats:
    video_packets: int = 0
    audio_packets: int = 0
    video_blocks: int = 0
    output_blocks: int = 0
    output_bytes: int = 0


class ToSeeBLive:
    """Run one bounded ToSee-B LAN video session."""

    def __init__(self, sock, address, did, client_uuid, on_h264):
        self.sock = sock
        self.address = address
        self.did = did
        self.client_uuid = client_uuid
        self.on_h264 = on_h264

        self.parser = VideoFrameParser()
        self.sync = H264Sync()
        self.stats = LiveStats()

    def _receive(self, timeout):
        self.sock.settimeout(max(0.01, timeout))

        try:
            packet, sender = self.sock.recvfrom(65535)
        except socket.timeout:
            return None

        if sender != self.address:
            return None

        drw = parse_drw_packet(packet)

        if drw is not None:
            channel, sequence, payload = drw

            if channel in (0, 1, 2):
                self.sock.sendto(
                    build_drw_ack(channel, [sequence]),
                    self.address,
                )

            if channel == 1:
                self.stats.video_packets += 1
                for frame in self.parser.feed(payload):
                    self.stats.video_blocks += 1
                    h264 = self.sync.accept(frame)

                    if h264 is not None:
                        self.on_h264(h264)
                        self.stats.output_blocks += 1
                        self.stats.output_bytes += len(h264)

            elif channel == 2:
                self.stats.audio_packets += 1

        return packet

    @staticmethod
    def _valid_response(sequence, payload):
        if payload is None:
            return False

        if sequence == 0:
            return payload == bytes(12)

        if sequence == 1:
            for offset in (0, 4, 8, 12):
                try:
                    obj = json.loads(payload[offset:].rstrip(b"\x00"))
                    if isinstance(obj, dict) and "sw_ver" in obj:
                        return True
                except (ValueError, UnicodeDecodeError):
                    continue
            return False

        if sequence in (2, 3):
            command = 5 if sequence == 2 else 3
            return payload == struct.pack("<III", 0, 0, command)

        return False

    def _exchange(self, sequence, packet, timeout=4.0, retries=3):
        acknowledged = False
        response = None
        attempts = 0
        next_send = 0.0
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            now = time.monotonic()

            if not acknowledged and attempts < retries and now >= next_send:
                self.sock.sendto(packet, self.address)
                attempts += 1
                next_send = now + 0.8

            if acknowledged and response is not None:
                break

            remaining = deadline - time.monotonic()
            incoming = self._receive(min(0.2, max(0.01, remaining)))

            if incoming is None:
                continue

            ack = parse_drw_ack(incoming)
            if ack is not None and ack[0] == 0 and sequence in ack[1]:
                acknowledged = True

            drw = parse_drw_packet(incoming)
            if drw is not None and drw[0] == 0 and drw[1] == sequence:
                response = drw[2]

        if not acknowledged or not self._valid_response(sequence, response):
            raise TimeoutError(
                f"ToSee-B control exchange failed at seq={sequence}"
            )

    def run(self, duration=10.0):
        """Start LAN video, deliver synchronized H.264 and close session.

        duration measures the streaming phase after control setup.
        """
        if duration <= 0:
            raise ValueError("duration must be positive")

        connected = False
        try:
            if not perform_punch(self.sock, self.address, self.did):
                raise TimeoutError("ToSee-B PUNCH failed")
            connected = True

            commands = (
                (0, build_init_drw_packet(self.client_uuid)),
                (1, build_drw_packet(1, 1)),
                (2, build_drw_packet(2, 5)),
                (3, build_drw_packet(3, 3)),
            )

            for sequence, packet in commands:
                self._exchange(sequence, packet)

            deadline = time.monotonic() + duration
            while time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                self._receive(min(0.2, max(0.01, remaining)))

            return self.stats

        finally:
            if connected:
                self._close_session()

    def _close_session(self, timeout=0.5):
        """Send PPCS F0 and briefly wait for the device's F0."""
        from .crypto import decrypt_packet

        closing = bytes.fromhex("f1f00000")

        try:
            self.sock.sendto(encrypt_packet(closing), self.address)

            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                self.sock.settimeout(
                    max(0.001, deadline - time.monotonic())
                )

                try:
                    packet, sender = self.sock.recvfrom(65535)
                except socket.timeout:
                    break

                if sender != self.address:
                    continue

                if decrypt_packet(packet) == closing:
                    return True

        except OSError:
            pass

        return False
