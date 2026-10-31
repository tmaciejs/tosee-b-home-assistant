"""Authenticated, multi-client WebSocket talkback receiver."""

import asyncio
import threading

from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

from .talk_identity import identify_ha_user
from .talk_permissions import can_use_talkback

import os

HOST = os.environ.get("TOSEE_TALK_HOST", "127.0.0.1")
PORT = int(os.environ.get("TOSEE_TALK_PORT", "19002"))


class TalkWebSocket:
    def __init__(self, session):
        self.session = session
        self.owner = None
        self.owner_lock = asyncio.Lock()

    def _release_finished_owner(self):
        """Release ownership only when talk control is idle."""
        if self.owner is None:
            return

        if self.session.talk_status() == "idle":
            self.owner = None
            print("WS_OWNER_RELEASED_IDLE", flush=True)

    async def handle(self, ws):
        try:
            supplied = await asyncio.wait_for(ws.recv(), timeout=5)
            user = await identify_ha_user(supplied)

            if not can_use_talkback(user):
                await ws.close(code=1008, reason="Unauthorized")
                return

            print("WS_AUTH_OK", flush=True)

            while True:
                try:
                    message = await asyncio.wait_for(
                        ws.recv(), timeout=30
                    )
                except asyncio.TimeoutError:
                    await ws.close(
                        code=1000, reason="Idle timeout"
                    )
                    break
                except ConnectionClosed:
                    break

                if message == "START":
                    async with self.owner_lock:
                        self._release_finished_owner()
                        if self.owner is not None:
                            accepted = False
                            reason = "busy"
                        else:
                            accepted = self.session.request_talk()
                            reason = (
                                "accepted" if accepted else "blocked"
                            )
                            if accepted:
                                self.owner = ws

                    print(
                        "WS_START_" + reason.upper(),
                        flush=True,
                    )
                    await ws.send(
                        "START_OK" if accepted else "START_BLOCKED"
                    )

                elif message == "STOP":
                    async with self.owner_lock:
                        if self.owner is ws:
                            self.session.stop_talk()
                            print("WS_TALK_STOP_REQUESTED", flush=True)
                            self._release_finished_owner()

                    await ws.send("STOP_OK")

                elif message == "STATUS":
                    async with self.owner_lock:
                        self._release_finished_owner()
                        state = self.session.talk_status()

                        if self.owner is not None and self.owner is not ws:
                            state = "blocked"

                    await ws.send("STATUS:" + state)

                elif isinstance(message, bytes) and len(message) == 320:
                    async with self.owner_lock:
                        if self.owner is ws:
                            accepted = (
                                self.session.accept_audio_from_browser(
                                    message
                                )
                            )
                        else:
                            accepted = False

                    if accepted:
                        count = getattr(
                            ws, "_tosee_audio_count", 0
                        ) + 1
                        ws._tosee_audio_count = count
                        if count == 1 or count % 50 == 0:
                            print(
                                f"TALK_BROWSER_FRAMES={count}",
                                flush=True,
                            )
                    else:
                        await ws.send("AUDIO_BLOCKED")

                else:
                    await ws.close(
                        code=1003, reason="Invalid message"
                    )
                    return

        except asyncio.TimeoutError:
            await ws.close(
                code=1008, reason="Authentication timeout"
            )
        except ConnectionClosed:
            pass
        finally:
            async with self.owner_lock:
                if self.owner is ws:
                    self.session.stop_talk()
                    print("WS_TALK_DISCONNECTED", flush=True)
                    self._release_finished_owner()


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
    """Start the WebSocket server in a daemon thread."""

    def worker():
        asyncio.run(main(session))

    thread = threading.Thread(
        target=worker,
        name="tosee-talk-websocket",
        daemon=True,
    )
    thread.start()
    return thread
