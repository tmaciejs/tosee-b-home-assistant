"""Run ToSee-B detection and MQTT publishing together."""

import argparse
import threading
from pathlib import Path

from .event_listener import listen_events
from .mqtt_events import publish_event
from .av_publisher_v14 import publish_av_session
from .runner import load_config


DEFAULT_ENV_FILE = Path(
    "/home/matt/Desktop/Lumina_Project/Kamera/.tosee.env"
)


def load_env_file(path):
    """Read configuration without executing it as shell code."""
    settings = {}

    for line in Path(path).read_text().splitlines():
        line = line.strip()

        if not line or line.startswith("#"):
            continue

        key, separator, value = line.partition("=")
        if separator:
            settings[key.strip()] = value

    return settings


def main():
    parser = argparse.ArgumentParser(
        description="ToSee-B passive event service"
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV_FILE,
    )
    args = parser.parse_args()

    settings = load_env_file(args.env_file)

    video_lock = threading.Lock()

    def run_video():
        try:
            config = load_config(settings)
            print("TOSEE_VIDEO_START", flush=True)
            stats = publish_av_session(
                address=config.address,
                did=config.did,
                client_uuid=config.client_uuid,
                rtsp_url="rtsp://127.0.0.1:8554/tosee-av-test",
                duration=120.0,
            )
            print(f"TOSEE_VIDEO_OK: {stats}", flush=True)
        except Exception as exc:
            print(
                f"TOSEE_VIDEO_ERROR: {type(exc).__name__}: {exc}",
                flush=True,
            )
        finally:
            video_lock.release()

    print("ToSee-B: nasluch i MQTT aktywne", flush=True)

    try:
        for event in listen_events():
            print(f"WYKRYTO: {event.kind}", flush=True)
            publish_event(event.kind, environ=settings)
            print(f"MQTT_WYSLANO: {event.kind}", flush=True)

            if event.kind in ("motion", "doorbell"):
                if video_lock.acquire(blocking=False):
                    try:
                        threading.Thread(
                            target=run_video,
                            daemon=True,
                            name="tosee-video",
                        ).start()
                    except Exception:
                        video_lock.release()
                        raise
                else:
                    print("TOSEE_VIDEO_ALREADY_RUNNING", flush=True)
    except KeyboardInterrupt:
        print("ToSee-B: zatrzymano", flush=True)


if __name__ == "__main__":
    main()
