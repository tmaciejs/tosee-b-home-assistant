"""Local Unix socket controller for ToSee-B manual LIVE."""

import os
import socket
import threading

SOCKET_PATH = "/run/tosee-b/live.sock"


def start_manual_live_server(start_video, talk_session=None):
    """Start a local-only LIVE controller."""

    def serve():
        server = socket.socket(
            socket.AF_UNIX,
            socket.SOCK_STREAM,
        )

        try:
            if os.path.lexists(SOCKET_PATH):
                os.unlink(SOCKET_PATH)

            server.bind(SOCKET_PATH)
            os.chmod(SOCKET_PATH, 0o600)
            server.listen(4)

            print("MANUAL_LIVE_READY", flush=True)

            while True:
                connection, _ = server.accept()

                with connection:
                    connection.settimeout(5.0)

                    try:
                        command = connection.recv(64).strip()

                        if command == b"DOORBELL":
                            if talk_session is None:
                                response = b"TALK_SESSION_UNAVAILABLE\n"
                            else:
                                talk_session.doorbell_pressed()
                                print("TALK_GATE_RING_RECORDED", flush=True)
                                started = start_video()
                                response = (
                                    b"STARTED\n"
                                    if started
                                    else b"ALREADY_RUNNING\n"
                                )
                        elif command == b"START":
                            started = start_video()
                            response = (
                                b"STARTED\n"
                                if started
                                else b"ALREADY_RUNNING\n"
                            )
                        else:
                            response = b"INVALID_COMMAND\n"

                        connection.sendall(response)

                    except OSError as exc:
                        print(
                            f"MANUAL_LIVE_CLIENT_ERROR: {exc}",
                            flush=True,
                        )
        except Exception as exc:
            print(
                f"MANUAL_LIVE_SERVER_ERROR: {exc}",
                flush=True,
            )
        finally:
            server.close()

    thread = threading.Thread(
        target=serve,
        daemon=True,
        name="tosee-manual-live",
    )
    thread.start()

    return thread
