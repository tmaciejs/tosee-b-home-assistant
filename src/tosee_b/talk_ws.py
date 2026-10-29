"""Experimental, localhost-only WebSocket talkback receiver."""

import asyncio
import threading
from websockets.asyncio.server import serve

from .talk_identity import identify_ha_user
from .talk_permissions import can_use_talkback

HOST = "127.0.0.1"
PORT = 19002


class TalkWebSocket:
    def __init__(self, session):
        self.session = session
        self.owner = None
        self.owner_lock = asyncio.Lock()

    async def handle(self, ws):
        try:
            supplied = await asyncio.wait_for(ws.recv(), timeout=5)
            user = await identify_ha_user(supplied)

            if not can_use_talkback(user):
                await ws.close(code=1008, reason="Unauthorized")
                return

            async with self.owner_lock:
                if self.owner is not None:
                    await ws.close(code=1008, reason="Talkback busy")
                    return
                self.owner = ws

            print("WS_AUTH_OK", flush=True)

            async for message in ws:
                if message == "START":
                    accepted = self.session.request_talk()
                    await ws.send("START_OK" if accepted else "START_BLOCKED")

                elif message == "STOP":
                    self.session.stop_talk()
                    await ws.send("STOP_OK")

                elif message == "STATUS":
                    await ws.send(
                        "STATUS:" + self.session.talk_status()
                    )

                elif isinstance(message, bytes) and len(message) == 320:
                    accepted = self.session.accept_audio_from_browser(message)
                    if not accepted:
                        await ws.send("AUDIO_BLOCKED")

                else:
                    await ws.close(code=1003, reason="Invalid message")
                    return

        except asyncio.TimeoutError:
            await ws.close(code=1008, reason="Authentication timeout")
        finally:
            async with self.owner_lock:
                if self.owner is ws:
                    self.session.stop_talk()
                    self.owner = None
                    print("WS_TALK_STOPPED", flush=True)


async def main(session):
    receiver = TalkWebSocket(session)

    async with serve(
        receiver.handle,
        HOST,
        PORT,
        max_size=1024,
        max_queue=4,
    ):
        print(f"WS_READY={HOST}:{PORT}", flush=True)
        await asyncio.Future()


def start_talk_websocket_thread(session):
    """Start localhost WebSocket in a separate daemon thread."""
    def worker():
        asyncio.run(main(session))

    thread = threading.Thread(
        target=worker,
        name="tosee-talk-websocket",
        daemon=True,
    )
    thread.start()
    return thread
