"""Run repeated ToSee-B LAN sessions with RTSP publishing."""

import os
from dataclasses import dataclass
from types import SimpleNamespace

from .publisher import publish_session
from .reconnect import run_with_reconnect


@dataclass(frozen=True)
class RunnerConfig:
    address: tuple[str, int]
    did: bytes
    client_uuid: str
    rtsp_url: str


def load_config(environ=None):
    """Read device settings without embedding them in source code."""
    env = os.environ if environ is None else environ

    required = (
        "TOSEE_HOST",
        "TOSEE_DID_HEX",
        "TOSEE_CLIENT_UUID",
    )

    missing = [key for key in required if not env.get(key)]
    if missing:
        raise ValueError(
            "Missing environment variables: " + ", ".join(missing)
        )

    did = bytes.fromhex(env["TOSEE_DID_HEX"])

    if len(did) != 20:
        raise ValueError("TOSEE_DID_HEX must contain exactly 20 bytes")

    port = int(env.get("TOSEE_PORT", "10000"))
    if not 1 <= port <= 65535:
        raise ValueError("Invalid TOSEE_PORT")

    return RunnerConfig(
        address=(env["TOSEE_HOST"], port),
        did=did,
        client_uuid=env["TOSEE_CLIENT_UUID"],
        rtsp_url=env.get(
            "TOSEE_RTSP_URL",
            "rtsp://127.0.0.1:8554/tosee",
        ),
    )


def run_forever(config, should_stop, retry_delay=3.0,
                session_duration=3600.0):
    """Run sequential LIVE sessions on one UDP socket.

    Advance the device port only after a successful session.
    Stop after a session error to avoid repeated PUNCH attempts
    against a battery-powered, possibly sleeping doorbell.
    """
    import socket

    if retry_delay < 0:
        raise ValueError("retry_delay must not be negative")
    if session_duration <= 0:
        raise ValueError("session_duration must be positive")

    state = {
        "next_port": config.address[1],
        "failed": False,
    }

    def guarded_stop():
        return state["failed"] or should_stop()

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("0.0.0.0", 0))

        def run_session():
            port = state["next_port"]
            if port > 65535:
                state["failed"] = True
                raise ValueError("ToSee-B UDP port limit reached")

            try:
                result = publish_session(
                    address=(config.address[0], port),
                    did=config.did,
                    client_uuid=config.client_uuid,
                    rtsp_url=config.rtsp_url,
                    duration=session_duration,
                    sock=sock,
                )
            except (OSError, TimeoutError, ValueError, RuntimeError):
                state["failed"] = True
                raise

            state["next_port"] += 1
            return result

        def session_factory():
            return SimpleNamespace(run=run_session)

        return run_with_reconnect(
            session_factory,
            guarded_stop,
            retry_delay=retry_delay,
        )
