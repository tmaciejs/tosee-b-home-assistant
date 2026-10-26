"""Incremental parser for ToSee-B channel-1 video framing."""

import struct
from dataclasses import dataclass


@dataclass(frozen=True)
class VideoFrame:
    number: int
    h264: bytes
    field2: int
    field3: int


class VideoFrameParser:
    """Reassemble 16-byte framed H.264 blocks from DRW payloads."""

    HEADER_SIZE = 16

    def __init__(self, max_frame_size=2 * 1024 * 1024):
        if max_frame_size <= 0:
            raise ValueError("max_frame_size must be positive")
        self.max_frame_size = max_frame_size
        self._buffer = bytearray()

    @property
    def buffered_bytes(self):
        return len(self._buffer)

    def reset(self):
        """Discard incomplete video framing data."""
        self._buffer.clear()

    def feed_resync(self, data):
        """Find a complete framed H.264 block after damaged bytes.

        Experimental recovery; not yet used by live streaming.
        """
        self._buffer.extend(data)

        for offset in range(max(0, len(self._buffer) - self.HEADER_SIZE - 2)):
            number, size, field2, field3 = struct.unpack_from(
                "<IIII", self._buffer, offset
            )

            if not 4 <= size <= self.max_frame_size:
                continue

            start = offset + self.HEADER_SIZE
            if self._buffer[start:start + 4] != bytes((0, 0, 0, 1)):
                continue

            # Validate the first H.264 NAL header.
            if start + 4 >= len(self._buffer):
                continue

            nal_header = self._buffer[start + 4]
            nal_type = nal_header & 0x1F

            if (nal_header & 0x80) or not 1 <= nal_type <= 23:
                continue

            end = start + size
            if end > len(self._buffer):
                continue

            h264 = bytes(self._buffer[start:end])
            frame = VideoFrame(number, h264, field2, field3)
            del self._buffer[:end]
            return [frame]

        # Bound memory while retaining a possible partial frame.
        limit = self.max_frame_size + self.HEADER_SIZE
        if len(self._buffer) > limit:
            del self._buffer[:-limit]

        return []

    def feed_keyframe_resync(self, data):
        """Find a complete ToSee-B SPS/PPS/IDR block after data loss."""
        self._buffer.extend(data)

        for offset in range(
            max(0, len(self._buffer) - self.HEADER_SIZE - 4)
        ):
            number, size, field2, field3 = struct.unpack_from(
                "<IIII", self._buffer, offset
            )

            if field2 != 1 or field3 != 0:
                continue

            if not 5 <= size <= self.max_frame_size:
                continue

            start = offset + self.HEADER_SIZE

            if self._buffer[start:start + 5] != bytes((0, 0, 0, 1, 0x67)):
                continue

            end = start + size
            if end > len(self._buffer):
                continue

            h264 = bytes(self._buffer[start:end])
            types = h264_nal_types(h264)

            try:
                pps = types.index(8, 1)
                types.index(5, pps + 1)
            except ValueError:
                continue

            frame = VideoFrame(number, h264, field2, field3)
            del self._buffer[:end]
            return [frame]

        limit = self.max_frame_size + self.HEADER_SIZE

        if len(self._buffer) > limit:
            del self._buffer[:-limit]

        return []

    def feed(self, data):
        self._buffer.extend(data)
        frames = []

        while len(self._buffer) >= self.HEADER_SIZE:
            number, size, field2, field3 = struct.unpack_from(
                "<IIII", self._buffer
            )

            if size == 0 or size > self.max_frame_size:
                raise ValueError("Invalid ToSee-B video frame size")

            total = self.HEADER_SIZE + size

            if len(self._buffer) < total:
                break

            h264 = bytes(self._buffer[self.HEADER_SIZE:total])

            if not h264.startswith(
                (b"\x00\x00\x00\x01", b"\x00\x00\x01")
            ):
                raise ValueError("Missing H.264 Annex B start code")

            frames.append(VideoFrame(number, h264, field2, field3))
            del self._buffer[:total]

        return frames


def h264_nal_types(data):
    """Return Annex B NAL types in their original order."""
    result = []
    i = 0

    while i < len(data) - 3:
        if data[i:i + 4] == b"\x00\x00\x00\x01":
            header = i + 4
            step = 4
        elif data[i:i + 3] == b"\x00\x00\x01":
            header = i + 3
            step = 3
        else:
            i += 1
            continue

        if header < len(data):
            result.append(data[header] & 0x1F)

        i += step

    return result


class H264Sync:
    """Suppress incomplete GOP data until SPS, PPS and IDR appear."""

    def __init__(self):
        self.synchronized = False

    def reset(self):
        self.synchronized = False

    def accept(self, frame):
        """Return H.264 bytes when ready, otherwise None."""
        if self.synchronized:
            return frame.h264

        types = h264_nal_types(frame.h264)

        try:
            sps = types.index(7)
            pps = types.index(8, sps + 1)
            types.index(5, pps + 1)
        except ValueError:
            return None

        # Safe for the observed ToSee-B layout where a keyframe block
        # begins with SPS followed by PPS, SEI and IDR.
        if sps != 0:
            return None

        self.synchronized = True
        return frame.h264
