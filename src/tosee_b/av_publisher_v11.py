"""Publish ToSee-B H.264 video and G.711 A-law audio to RTSP."""

import os
import fcntl
import queue
import socket
import subprocess
import threading
import time

from .live import ToSeeBLive



class SafeToSeeBLive(ToSeeBLive):
    """Ignore only malformed ToSee-B audio packets during AV tests."""

    def _receive(self, timeout):
        try:
            return super()._receive(timeout)
        except ValueError as exc:
            if str(exc) in (
                "Invalid ToSee-B audio payload size",
                "Invalid ToSee-B audio frame header",
            ):
                print("AUDIO_INVALID_PACKET_SKIPPED:", exc, flush=True)
                return None
            raise


def publish_av_session(
    address,
    did,
    client_uuid,
    rtsp_url="rtsp://127.0.0.1:8554/tosee-av-test",
    duration=60.0,
    bind_address="0.0.0.0",
):
    """Run one bounded audio/video session without changing the video publisher."""
    if duration <= 0:
        raise ValueError("duration must be positive")

    audio_read, audio_write = os.pipe()
    fcntl.fcntl(audio_write, fcntl.F_SETPIPE_SZ, 1048576)
    os.set_blocking(audio_write, False)

    video_queue = queue.Queue(maxsize=128)
    audio_queue = queue.Queue(maxsize=256)
    writer_errors = queue.Queue()
    stop_writers = threading.Event()

    ffmpeg = None

    try:
        ffmpeg = subprocess.Popen(
            [
                "ffmpeg",
                "-hide_banner",
                "-nostdin",
                "-loglevel", "info",
                "-thread_queue_size", "512",
                "-probesize", "32768",
                "-analyzeduration", "100000",
                "-f", "h264",
                "-r", "20",
                "-i", "pipe:0",
                "-thread_queue_size", "512",
                "-probesize", "32768",
                "-analyzeduration", "100000",
                "-f", "alaw",
                "-ar", "8000",
                "-ac", "1",
                "-i", f"pipe:{audio_read}",
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-c:v", "copy",
                "-c:a", "copy",
                "-max_interleave_delta", "100000",
                "-flush_packets", "1",
                "-f", "rtsp",
                "-rtsp_transport", "tcp",
                rtsp_url,
            ],
            stdin=subprocess.PIPE,
            pass_fds=(audio_read,),
            stdout=subprocess.DEVNULL,
            stderr=None,
        )

        os.close(audio_read)
        audio_read = -1
        os.set_blocking(ffmpeg.stdin.fileno(), False)

        def video_writer():
            try:
                while True:
                    try:
                        data = video_queue.get(timeout=0.1)
                    except queue.Empty:
                        if stop_writers.is_set():
                            return
                        continue
                    try:
                        if data is None:
                            return
                        pending = memoryview(data)
                        deadline = time.monotonic() + 3.0

                        while pending:
                            try:
                                written = os.write(
                                    ffmpeg.stdin.fileno(), pending
                                )
                                if written == 0:
                                    raise BrokenPipeError(
                                        "FFmpeg video pipe closed"
                                    )
                                pending = pending[written:]
                            except BlockingIOError:
                                if ffmpeg.poll() is not None:
                                    raise RuntimeError(
                                        "FFmpeg exited during video write"
                                    )
                                if time.monotonic() >= deadline:
                                    raise TimeoutError(
                                        "FFmpeg video pipe blocked"
                                    )
                                time.sleep(0.01)
                    finally:
                        video_queue.task_done()
            except Exception as exc:
                writer_errors.put(exc)

        video_thread = threading.Thread(
            target=video_writer,
            name="tosee-av-video-writer",
            daemon=True,
        )
        video_thread.start()

        def on_h264(data):
            if not writer_errors.empty():
                raise RuntimeError("FFmpeg video writer failed") from writer_errors.get_nowait()
            if ffmpeg.poll() is not None:
                raise RuntimeError("FFmpeg AV publisher exited")
            try:
                video_queue.put_nowait(data)
            except queue.Full:
                raise RuntimeError("FFmpeg video queue full")

        def audio_writer():
            try:
                while True:
                    try:
                        data = audio_queue.get(timeout=0.1)
                    except queue.Empty:
                        if stop_writers.is_set():
                            return
                        continue
                    try:
                        if data is None:
                            return
                        pending = memoryview(data)
                        deadline = time.monotonic() + 3.0

                        while pending:
                            try:
                                written = os.write(audio_write, pending)
                                if written == 0:
                                    raise BrokenPipeError(
                                        "FFmpeg audio pipe closed"
                                    )
                                pending = pending[written:]
                            except BlockingIOError:
                                if ffmpeg.poll() is not None:
                                    raise RuntimeError(
                                        "FFmpeg exited during audio write"
                                    )
                                if time.monotonic() >= deadline:
                                    raise TimeoutError(
                                        "FFmpeg audio pipe blocked"
                                    )
                                time.sleep(0.01)
                    finally:
                        audio_queue.task_done()
            except Exception as exc:
                writer_errors.put(exc)

        audio_thread = threading.Thread(
            target=audio_writer,
            name="tosee-av-audio-writer",
            daemon=True,
        )
        audio_thread.start()

        def on_audio(data):
            if not writer_errors.empty():
                raise RuntimeError("FFmpeg AV writer failed") from writer_errors.get_nowait()
            if ffmpeg.poll() is not None:
                raise RuntimeError("FFmpeg AV publisher exited")
            try:
                audio_queue.put_nowait(data)
            except queue.Full:
                return  # Kolejka pełna — nie blokujemy odbioru UDP

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind((bind_address, 0))

            client = SafeToSeeBLive(
                sock=sock,
                address=address,
                did=did,
                client_uuid=client_uuid,
                on_h264=on_h264,
                on_audio=on_audio,
            )

            stats = client.run(duration=duration)

        if not writer_errors.empty():
            raise RuntimeError(
                "FFmpeg AV writer failed"
            ) from writer_errors.get_nowait()

        if ffmpeg.poll() is not None:
            raise RuntimeError("FFmpeg AV publisher exited unexpectedly")

    finally:
        stop_writers.set()

        for thread in (
            locals().get("video_thread"),
            locals().get("audio_thread"),
        ):
            if thread is not None:
                thread.join(timeout=5)

        threads_alive = [
            thread.name
            for thread in (
                locals().get("video_thread"),
                locals().get("audio_thread"),
            )
            if thread is not None and thread.is_alive()
        ]

        if threads_alive and ffmpeg is not None:
            if ffmpeg.poll() is None:
                ffmpeg.kill()
            for thread in (video_thread, audio_thread):
                thread.join(timeout=2)

            if video_thread.is_alive() or audio_thread.is_alive():
                writer_errors.put(
                    RuntimeError("FFmpeg AV writer threads did not stop")
                )

        if ffmpeg is not None:
            if ffmpeg.stdin is not None:
                try:
                    ffmpeg.stdin.close()
                except BrokenPipeError:
                    pass

        os.close(audio_write)

        if audio_read >= 0:
            os.close(audio_read)

        if ffmpeg is not None:
            try:
                ffmpeg.wait(timeout=10)
            except subprocess.TimeoutExpired:
                ffmpeg.kill()
                ffmpeg.wait()

    if not writer_errors.empty():
        raise RuntimeError(
            "FFmpeg AV writer failed during shutdown"
        ) from writer_errors.get_nowait()

    return stats
