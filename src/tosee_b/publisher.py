"""Publish a single ToSee-B LAN session to a local RTSP server."""

import socket
import subprocess

from .live import ToSeeBLive


def publish_session(
    address,
    did,
    client_uuid,
    rtsp_url="rtsp://127.0.0.1:8554/tosee",
    duration=3600.0,
    bind_address="0.0.0.0",
    sock=None,
):
    """Run one LIVE session and publish synchronized H.264 through FFmpeg.

    Returns LiveStats. Caller handles reconnecting after session completion.
    """
    if duration <= 0:
        raise ValueError("duration must be positive")

    ffmpeg = None

    try:
        ffmpeg = subprocess.Popen(
            [
                "ffmpeg",
                "-hide_banner",
                "-nostdin",
                "-loglevel", "error",
                "-f", "h264",
                "-r", "25",
                "-i", "pipe:0",
                "-an",
                "-c:v", "copy",
                "-f", "rtsp",
                "-rtsp_transport", "tcp",
                rtsp_url,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        def on_h264(data):
            if ffmpeg.poll() is not None:
                raise RuntimeError("FFmpeg publisher exited")
            ffmpeg.stdin.write(data)

        if sock is None:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as owned_sock:
                owned_sock.bind((bind_address, 0))
                client = ToSeeBLive(
                    sock=owned_sock,
                    address=address,
                    did=did,
                    client_uuid=client_uuid,
                    on_h264=on_h264,
                )
                stats = client.run(duration=duration)
        else:
            client = ToSeeBLive(
                sock=sock,
                address=address,
                did=did,
                client_uuid=client_uuid,
                on_h264=on_h264,
            )
            stats = client.run(duration=duration)

        if ffmpeg.poll() is not None:
            raise RuntimeError("FFmpeg publisher exited unexpectedly")

        return stats

    finally:
        if ffmpeg is not None:
            if ffmpeg.stdin is not None:
                try:
                    ffmpeg.stdin.close()
                except BrokenPipeError:
                    pass

            try:
                ffmpeg.wait(timeout=10)
            except subprocess.TimeoutExpired:
                ffmpeg.kill()
                ffmpeg.wait()
