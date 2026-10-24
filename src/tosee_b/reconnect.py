"""Retry controller for independent ToSee-B LIVE sessions."""

import time


def run_with_reconnect(session_factory, should_stop, retry_delay=3.0):
    """Run fresh sessions until stopped.

    session_factory creates a new session for each attempt.
    should_stop returns True when the service should exit.
    """
    if retry_delay < 0:
        raise ValueError("retry_delay must not be negative")

    attempts = 0

    while not should_stop():
        attempts += 1

        try:
            session = session_factory()
            session.run()
        except (OSError, TimeoutError, ValueError, RuntimeError):
            if should_stop():
                break

        if not should_stop():
            time.sleep(retry_delay)

    return attempts
