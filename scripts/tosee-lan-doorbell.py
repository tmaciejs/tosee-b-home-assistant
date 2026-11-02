#!/usr/bin/env python3
"""ToSee-B LAN doorbell detector, SSH PTY and MQTT."""

import datetime
import errno
import os
import pty
import re
import select
import signal
import subprocess
import threading
import time
from pathlib import Path

import paho.mqtt.client as mqtt

COOLDOWN = 90.0
ENV_FILE = Path("/home/tosee/.tosee.env")
TOPIC = "tosee_b/event/doorbell"

PATTERN = re.compile(
    r"\bIP 192\.168\.1\.138\.\d+ > "
    r"\d+\.\d+\.\d+\.\d+\.32700: UDP, length 16\b"
)

stop_event = threading.Event()


def log(message):
    timestamp = datetime.datetime.now().astimezone().isoformat(
        timespec="seconds"
    )
    print(f"{timestamp} {message}", flush=True)


def handle_stop(signum, frame):
    stop_event.set()


signal.signal(signal.SIGTERM, handle_stop)
signal.signal(signal.SIGINT, handle_stop)


def load_settings():
    settings = {}

    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()

        if not line or line.startswith("#"):
            continue

        key, sep, value = line.partition("=")

        if sep:
            settings[key.strip()] = value.strip()

    return settings


def publish_doorbell(settings):
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="tosee_b_lan_doorbell",
    )

    client.username_pw_set(
        settings["TOSEE_MQTT_USERNAME"],
        settings["TOSEE_MQTT_PASSWORD"],
    )

    connected = threading.Event()
    connection_error = []

    def on_connect(
        client, userdata, flags, reason_code, properties
    ):
        if reason_code.is_failure:
            connection_error.append(str(reason_code))
        connected.set()

    client.on_connect = on_connect

    try:
        client.connect(
            settings["TOSEE_MQTT_HOST"],
            int(settings.get("TOSEE_MQTT_PORT", "1883")),
            keepalive=30,
        )

        client.loop_start()

        if not connected.wait(timeout=5):
            raise TimeoutError("MQTT connection timed out")

        if connection_error:
            raise RuntimeError(connection_error[0])

        info = client.publish(
            TOPIC,
            payload="ON",
            qos=1,
            retain=False,
        )

        info.wait_for_publish(timeout=5)

        if not info.is_published():
            raise TimeoutError("MQTT publish timed out")

        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(
                f"MQTT publish error: {info.rc}"
            )

        log("MQTT_PUBLISHED doorbell")

    finally:
        client.disconnect()
        client.loop_stop()


def start_local_live():
    """Request LIVE using the existing production Unix socket."""
    import socket

    path = "/run/tosee-b/live.sock"

    with socket.socket(
        socket.AF_UNIX, socket.SOCK_STREAM
    ) as sock:
        sock.settimeout(1.5)
        sock.connect(path)
        sock.sendall(b"DOORBELL")
        response = sock.recv(128).decode(
            "ascii", errors="replace"
        ).strip()

    if response not in ("STARTED", "ALREADY_RUNNING"):
        raise RuntimeError(f"LIVE unexpected response: {response!r}")

    log(f"LAN_LIVE_REQUEST {response}")


def listen_once(settings, last_event):
    remote_command = (
        "/bin/timeout -s INT -k 5 3600 "
        "/usr/sbin/tcpdump -l -nn -tttt -i igc1 "
        "'src host 192.168.1.138 and udp "
        "and dst port 32700 and udp[4:2] = 24'"
    )

    command = [
        "ssh",
        "-tt",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=5",
        "-o", "ServerAliveInterval=15",
        "-o", "ServerAliveCountMax=2",
        "admin@192.168.1.1",
        remote_command,
    ]

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

    log("LISTENER_SSH_STARTED")

    pending = b""

    try:
        while not stop_event.is_set():
            readable, _, _ = select.select(
                [master], [], [], 0.5
            )

            if not readable:
                if process.poll() is not None:
                    break
                continue

            try:
                chunk = os.read(master, 4096)
            except OSError as exc:
                if exc.errno == errno.EIO:
                    break
                raise

            if not chunk:
                break

            pending += chunk

            while b"\n" in pending:
                raw, pending = pending.split(b"\n", 1)

                line = raw.decode(
                    "utf-8", errors="replace"
                ).rstrip("\r")

                if not PATTERN.search(line):
                    continue

                now = time.monotonic()

                if (
                    last_event is not None
                    and now - last_event < COOLDOWN
                ):
                    continue

                last_event = now
                log("LAN_DOORBELL_DETECTED")

                try:
                    start_local_live()
                except Exception as exc:
                    log(
                        "LAN_LIVE_ERROR "
                        f"{type(exc).__name__}: {exc}"
                    )

                try:
                    publish_doorbell(settings)
                except Exception as exc:
                    log(
                        "MQTT_ERROR "
                        f"{type(exc).__name__}: {exc}"
                    )

        if process.poll() is None and not stop_event.is_set():
            process.wait(timeout=3)

    finally:
        if process.poll() is None:
            try:
                # Ctrl+C inside the remote terminal.
                os.write(master, b"\x03")
                process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                if process.poll() is None:
                    os.killpg(
                        process.pid, signal.SIGTERM
                    )
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        os.killpg(
                            process.pid, signal.SIGKILL
                        )
                        process.wait()

        os.close(master)

    return last_event, process.returncode


def main():
    settings = load_settings()
    last_event = None

    log("LAN_DOORBELL_STARTED")

    while not stop_event.is_set():
        try:
            last_event, code = listen_once(
                settings, last_event
            )

            if stop_event.is_set():
                break

            log(f"LISTENER_EXIT code={code}")

            # Normal timeout: minimal restart delay.
            # SSH error: retry more slowly.
            delay = 0.2 if code in (0, 124) else 3.0

        except Exception as exc:
            if stop_event.is_set():
                break

            log(
                "LISTENER_ERROR "
                f"{type(exc).__name__}: {exc}"
            )
            delay = 3.0

        if not stop_event.is_set():
            log(f"LISTENER_RESTART_IN_{delay}S")
            stop_event.wait(delay)

    log("LAN_DOORBELL_STOPPED")


if __name__ == "__main__":
    main()
