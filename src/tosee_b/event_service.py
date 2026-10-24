"""Run ToSee-B detection and MQTT publishing together."""

import argparse
from pathlib import Path

from .event_listener import listen_events
from .mqtt_events import publish_event


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

    print("ToSee-B: nasluch i MQTT aktywne", flush=True)

    try:
        for event in listen_events():
            print(f"WYKRYTO: {event.kind}", flush=True)
            publish_event(event.kind, environ=settings)
            print(f"MQTT_WYSLANO: {event.kind}", flush=True)
    except KeyboardInterrupt:
        print("ToSee-B: zatrzymano", flush=True)


if __name__ == "__main__":
    main()
