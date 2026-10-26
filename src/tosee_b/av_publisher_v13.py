"""Publish ToSee-B H.264 video and G.711 A-law audio to RTSP."""

import os
import fcntl
import array
import termios
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
    """Experimental single-pipe NUT AV publisher."""
    import av
    from fractions import Fraction
    from .video import h264_nal_types

    if duration <= 0:
        raise ValueError("duration must be positive")

    packets = queue.Queue(maxsize=512)
    errors = queue.Queue()
    stop = threading.Event()
    started = time.monotonic()
    counts = {"video": 0, "audio": 0}

    ffmpeg = subprocess.Popen(
        [
            "ffmpeg", "-hide_banner", "-nostdin",
            "-loglevel", "info",
            "-probesize", "1048576",
            "-analyzeduration", "2000000",
            "-f", "nut", "-i", "pipe:0",
            "-map", "0:v:0",
            "-map", "0:a:0",
            "-c:v", "copy",
            "-c:a", "copy",
            "-max_interleave_delta", "100000",
            "-flush_packets", "1",
            "-f", "rtsp",
            "-rtsp_transport", "tcp",
            rtsp_url,
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=None,
    )

    os.set_blocking(ffmpeg.stdin.fileno(), False)

    class Sink:
        def write(self, data):
            pending = memoryview(data)
            deadline = time.monotonic() + 3.0

            while pending:
                try:
                    n = os.write(ffmpeg.stdin.fileno(), pending)
                    if n <= 0:
                        raise BrokenPipeError("NUT pipe closed")
                    pending = pending[n:]
                except BlockingIOError:
                    if ffmpeg.poll() is not None:
                        raise RuntimeError("FFmpeg exited")
                    if time.monotonic() >= deadline:
                        raise TimeoutError("NUT pipe blocked")
                    time.sleep(0.01)
            return len(data)

        def flush(self):
            pass

    def mux_worker():
        try:
            with av.open(
                Sink(), mode="w", format="nut", buffer_size=188
            ) as output:
                video = output.add_stream("h264", rate=20)
                video.width = 1280
                video.height = 720
                video.pix_fmt = "yuv420p"
                video.time_base = Fraction(1, 90000)
                video.codec_context.time_base = Fraction(1, 20)

                audio = output.add_stream("pcm_alaw", rate=8000)
                audio.layout = "mono"

                last_video_pts = -1
                audio_pts = None

                while True:
                    try:
                        item = packets.get(timeout=0.1)
                    except queue.Empty:
                        if stop.is_set():
                            break
                        continue

                    kind, data, timestamp = item

                    if kind == "video":
                        pts = round((timestamp - started) * 90000)
                        pts = max(pts, last_video_pts + 1)
                        last_video_pts = pts

                        pkt = av.Packet(data)
                        pkt.stream = video
                        pkt.time_base = Fraction(1, 90000)
                        pkt.pts = pkt.dts = pts

                        if 5 in h264_nal_types(data):
                            pkt.is_keyframe = True
                    else:
                        if audio_pts is None:
                            audio_pts = round(
                                (timestamp - started) * 8000
                            )

                        pkt = av.Packet(data)
                        pkt.stream = audio
                        pkt.time_base = Fraction(1, 8000)
                        pkt.pts = pkt.dts = audio_pts
                        audio_pts += len(data)

                    output.mux(pkt)
                    counts[kind] += 1

                    if counts[kind] == 1:
                        print(
                            f"V13_FIRST_MUX {kind} "
                            f"t={time.monotonic()-started:.3f}s",
                            flush=True,
                        )

        except Exception as exc:
            errors.put(exc)

    worker = threading.Thread(
        target=mux_worker,
        name="tosee-nut-mux",
        daemon=True,
    )
    worker.start()

    def submit(kind, data):
        if not errors.empty():
            raise RuntimeError("NUT mux failed") from errors.get_nowait()
        if ffmpeg.poll() is not None:
            raise RuntimeError("FFmpeg exited unexpectedly")

        try:
            packets.put_nowait(
                (kind, bytes(data), time.monotonic())
            )
        except queue.Full:
            raise RuntimeError("NUT packet queue full")

    def on_h264(data):
        submit("video", data)

    def on_audio(data):
        submit("audio", data)

    try:
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

    finally:
        stop.set()
        worker.join(timeout=10)

        if worker.is_alive():
            ffmpeg.kill()
            worker.join(timeout=3)
            errors.put(RuntimeError("NUT mux worker blocked"))

        try:
            ffmpeg.stdin.close()
        except (BrokenPipeError, OSError):
            pass

        try:
            ffmpeg.wait(timeout=10)
        except subprocess.TimeoutExpired:
            ffmpeg.kill()
            ffmpeg.wait()

    if not errors.empty():
        raise RuntimeError("NUT mux failed") from errors.get_nowait()

    if ffmpeg.returncode != 0:
        raise RuntimeError(
            f"FFmpeg returned {ffmpeg.returncode}"
        )

    print("V13_MUX_COUNTS:", counts, flush=True)
    return stats
