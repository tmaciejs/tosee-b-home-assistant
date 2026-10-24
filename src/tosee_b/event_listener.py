"""Passive ToSee-B event detection through pfSense SSH and tcpdump."""

import os
import pty
import re
import signal
import subprocess
import time
from dataclasses import dataclass


PACKET_RE = re.compile(
    r"\bIP 192\.168\.1\.138\.\d+ > "
    r"\d+\.\d+\.\d+\.\d+\.(15000|25000): "
    r"UDP, length (1052|1104)\b"
)

EVENT_BY_LENGTH = {
    1052: "motion",
    1104: "doorbell",
}


@dataclass(frozen=True)
class Event:
    kind: str
    timestamp: float


def parse_packet(line):
    """Classify one tcpdump line, or return None."""
    match = PACKET_RE.search(line)
    if match is None:
        return None
    return EVENT_BY_LENGTH[int(match.group(2))]


class EventDeduplicator:
    """Suppress repeated packets from the same activation."""

    def __init__(self, interval=3.0):
        if interval < 0:
            raise ValueError("interval must not be negative")
        self.interval = interval
        self.last_event = {}

    def accept(self, kind, now=None):
        if now is None:
            now = time.monotonic()

        previous = self.last_event.get(kind)
        if previous is not None and now - previous < self.interval:
            return False

        self.last_event[kind] = now
        return True


def listen_events(
    ssh_host="admin@192.168.1.1",
    interface="igc1",
    on_event=None,
):
    """Observe ToSee-B events through SSH with a managed PTY."""
    remote_command = (
        "/bin/timeout 60 /usr/sbin/tcpdump -l -n -i " + interface
        + " 'src host 192.168.1.138 and udp "
        + "and (dst port 15000 or dst port 25000) "
        + "and (udp[4:2] = 1060 or udp[4:2] = 1112)'"
    )

    command = [
        "ssh", "-tt",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=5",
        ssh_host,
        remote_command,
    ]

    deduplicator = EventDeduplicator()

    try:
        while True:
            master, slave = pty.openpty()
            try:
                process = subprocess.Popen(
                    command,
                    stdin=slave,
                    stdout=slave,
                    stderr=slave,
                    start_new_session=True,
                )
            except BaseException:
                os.close(master)
                os.close(slave)
                raise

            os.close(slave)

            try:
                pending = b""

                while True:
                    try:
                        chunk = os.read(master, 4096)
                    except OSError as exc:
                        if exc.errno == 5:  # EIO: PTY closed
                            break
                        raise

                    if not chunk:
                        break

                    pending += chunk

                    while b"\n" in pending:
                        raw_line, pending = pending.split(b"\n", 1)
                        line = raw_line.decode(
                            "utf-8", errors="replace"
                        ).rstrip("\r")

                        kind = parse_packet(line)
                        if kind is None:
                            continue

                        now = time.monotonic()
                        if not deduplicator.accept(kind, now):
                            continue

                        event = Event(kind=kind, timestamp=now)

                        if on_event is not None:
                            on_event(event)

                        yield event

                returncode = process.wait()
                if returncode not in (0, 124):
                    raise RuntimeError(
                        "Remote tcpdump/SSH exited with status "
                        + str(returncode)
                    )

            finally:
                if process.poll() is None:
                    try:
                        os.write(master, b"\x03")
                        process.wait(timeout=5)
                    except (OSError, subprocess.TimeoutExpired):
                        if process.poll() is None:
                            os.killpg(process.pid, signal.SIGTERM)
                            try:
                                process.wait(timeout=2)
                            except subprocess.TimeoutExpired:
                                os.killpg(process.pid, signal.SIGKILL)
                                process.wait()

                os.close(master)

    except KeyboardInterrupt:
        return
