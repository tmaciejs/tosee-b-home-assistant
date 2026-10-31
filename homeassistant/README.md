# ToSee-B TALK V2 — Home Assistant

Custom Lovelace card for two-way audio with a ToSee-B doorbell.

## Installation

1. Copy `www/tosee-talk-card.v2.js` to Home Assistant's `/config/www/` directory.
2. Register `/local/tosee-talk-card.v2.js?v=1` as a JavaScript module resource.
3. Add the following Lovelace card:

```yaml
type: custom:tosee-talk-card-v2
talk_ws_url: wss://YOUR-SERVER/tosee-talk/
```

Replace YOUR-SERVER with your own HTTPS reverse proxy address.

## Browser Mod popup example

```yaml
action: browser_mod.popup
data:
  title: "Doorbell"
  content:
    type: vertical-stack
    cards:
      - type: iframe
        url: "https://YOUR-SERVER/tosee-video/stream.html?src=tosee_live&mode=webrtc,mse,hls,mjpeg"
        aspect_ratio: "16:9"
      - type: custom:tosee-talk-card-v2
        talk_ws_url: wss://YOUR-SERVER/tosee-talk/
  timeout: 45000
```

The video URL is an example. Adapt it to your streaming setup.
Configure the popup trigger and target browsers separately.

## Requirements

- Running ToSee-B TALK WebSocket server.
- Active doorbell LIVE session.
- Browser microphone permission.
- HTTPS and WSS access.
- Only one browser can own the talkback session at a time.

Do not publish access tokens, passwords or device credentials.
