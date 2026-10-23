#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Recover ToSee-B H.264 video from a captured PPCS UDP session."""

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from tosee_b.crypto import decrypt_packet, is_valid_ppcs_packet


def main():
    parser = argparse.ArgumentParser(
        description="Extract H.264 video from a ToSee-B PCAP capture"
    )
    parser.add_argument("pcap", type=Path, help="Input PCAP file")
    parser.add_argument("-o", "--output", type=Path, required=True,
                        help="Output .h264 file")
    parser.add_argument("--device-ip", required=True,
                        help="Doorbell IPv4 address")
    parser.add_argument(
        "--mp4", action="store_true",
        help="Also create an MP4 file using FFmpeg"
    )
    parser.add_argument(
        "--fps", type=float, default=15.0,
        help="Output frame rate (default: 15, experimental)"
    )
    args = parser.parse_args()
    if args.fps <= 0:
        parser.error("--fps must be greater than zero")

    if not args.pcap.is_file():
        parser.error(f"File not found: {args.pcap}")

    command = [
        "tshark", "-r", str(args.pcap),
        "-Y", f"ip.src=={args.device_ip} && udp.length>100",
        "-T", "fields", "-e", "udp.payload",
    ]

    packets = {}
    valid = 0
    duplicates = 0

    result = subprocess.run(
        command, capture_output=True, text=True, check=True
    )

    for line in result.stdout.splitlines():
        if not line.strip():
            continue

        decoded = decrypt_packet(bytes.fromhex(line.strip()))

        if not is_valid_ppcs_packet(decoded):
            continue

        valid += 1

        if len(decoded) < 8 or decoded[4:6] != b"\xd1\x01":
            continue

        number = int.from_bytes(decoded[6:8], "big")
        content = bytes(decoded[8:])

        if number in packets:
            if packets[number] != content:
                raise ValueError(
                    f"Conflicting data for video packet {number}"
                )
            duplicates += 1
            continue

        packets[number] = content

    if not packets:
        raise SystemExit("No valid ToSee-B video packets found.")

    frames = []
    buffer = bytearray()
    previous_number = None
    incomplete = False
    gaps = 0

    for number in sorted(packets):
        if previous_number is not None and number != previous_number + 1:
            gaps += number - previous_number - 1
            buffer.clear()
            incomplete = True

        previous_number = number
        buffer.extend(packets[number])

        while True:
            if len(buffer) < 16:
                break

            if incomplete:
                marker = buffer.find(b"\x00\x00\x00\x01")

                if marker < 16:
                    buffer.clear()
                    break

                candidate = marker - 16
                size = int.from_bytes(
                    buffer[candidate + 4:candidate + 8], "little"
                )

                if not 5 <= size <= 200000:
                    buffer.clear()
                    break

                del buffer[:candidate]
                incomplete = False

            size = int.from_bytes(buffer[4:8], "little")

            if not 5 <= size <= 200000:
                buffer.clear()
                incomplete = True
                break

            if len(buffer) < 16 + size:
                break

            video = bytes(buffer[16:16 + size])

            if video.startswith(b"\x00\x00\x00\x01"):
                frames.append(video)

            del buffer[:16 + size]

    args.output.parent.mkdir(parents=True, exist_ok=True)

    with args.output.open("wb") as output:
        for frame in frames:
            output.write(frame)

    print(f"Output: {args.output}")
    print(f"Valid PPCS packets: {valid}")
    print(f"Unique video packets: {len(packets)}")
    print(f"Retransmissions: {duplicates}")
    print(f"Missing packet numbers: {gaps}")
    print(f"Recovered H.264 units: {len(frames)}")
    print(f"Written bytes: {args.output.stat().st_size}")

    if args.mp4:
        mp4_path = args.output.with_suffix(".mp4")
        if mp4_path == args.pcap:
            raise SystemExit("MP4 output would overwrite the input PCAP")

        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "warning",
            "-framerate", str(args.fps),
            "-i", str(args.output),
            "-an", "-c:v", "libx264",
            "-preset", "ultrafast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-y", str(mp4_path),
        ], check=True)
        print(f"MP4: {mp4_path}")


if __name__ == "__main__":
    main()
