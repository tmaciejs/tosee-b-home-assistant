"""Extract G.711 A-law audio from ToSee-B DRW channel 2."""

FRAME_SIZE = 332
HEADER_SIZE = 12
AUDIO_SIZE = 320

AUDIO_HEADER = bytes.fromhex(
    "000000004001000000000000"
)


def extract_alaw(payload: bytes) -> bytes:
    """Extract raw G.711 A-law samples from a DRW audio payload."""
    if not isinstance(payload, bytes):
        raise TypeError("Audio payload must be bytes")

    if not payload or len(payload) % FRAME_SIZE:
        raise ValueError("Invalid ToSee-B audio payload size")

    result = bytearray()

    for offset in range(0, len(payload), FRAME_SIZE):
        frame = payload[offset:offset + FRAME_SIZE]

        if frame[:HEADER_SIZE] != AUDIO_HEADER:
            raise ValueError("Invalid ToSee-B audio frame header")

        result.extend(frame[HEADER_SIZE:])

    return bytes(result)
