# ToSee-B Home Assistant

Open-source project for ToSee-B battery-powered video doorbells.

## Current status

### Working
- Decryption of captured PPCS UDP packets.
- H.264 video reconstruction.
- Automatic MP4 conversion using FFmpeg.
- Tested on three independent PCAP recordings.
- Confirmed video playback at 1280x720.

### Planned
- Direct PPCS connection without Android.
- Battery doorbell wake-up support.
- Live video streaming.
- Home Assistant integration.

**Currently an offline PCAP decoder, not a live camera integration.**

## Requirements

- Linux
- Python 3
- TShark
- FFmpeg (for MP4 output)

On Debian:

    sudo apt install python3 tshark ffmpeg

## Usage

Extract H.264:

    python3 tosee_decode.py capture.pcap -o recovered.h264 --device-ip 192.0.2.10

Extract H.264 and create MP4:

    python3 tosee_decode.py capture.pcap -o recovered.h264 --mp4 --fps 15 --device-ip 192.0.2.10

Replace the example IP with your doorbell's IP address.

The default 15 FPS is experimental.

## Limitations

Tested on one ToSee-B device using three separate captures.
Other devices and firmware versions have not yet been tested.
Some frames may be damaged by packet loss.
Live connection support is not implemented yet.

## Privacy

Never publish private PCAP captures, camera recordings,
device credentials, or unique device identifiers.

## License

GNU General Public License v3.

Uses a PPCS lookup table originating from the GPLv3-licensed
cloudedge-client project. Attribution will be verified before release.

## Disclaimer

Unofficial community project. Not affiliated with the manufacturer.
Use only with devices and networks you own or are authorized to access.
