import asyncio
import importlib.util
from importlib.machinery import SourceFileLoader
from unittest.mock import patch


def load(name, path):
    loader = SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


Session = load(
    "tosee_b.session_disconnect_candidate",
    "src/tosee_b/talk_session.py.candidate",
).TalkSession

ws_module = load(
    "tosee_b.ws_disconnect_candidate",
    "src/tosee_b/talk_ws.py.new",
)


class Controller:
    def __init__(self):
        self.state = "idle"


class Live:
    def __init__(self):
        self.talk_controller = Controller()


class FakeWS:
    def __init__(self):
        self.incoming = asyncio.Queue()
        self.sent = []

    async def recv(self):
        message = await self.incoming.get()
        if isinstance(message, Exception):
            raise message
        return message

    async def send(self, message):
        self.sent.append(message)

    async def close(self, code=1000, reason=""):
        pass

    async def push(self, message):
        await self.incoming.put(message)


async def wait_for(condition):
    for _ in range(100):
        if condition():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("Timeout testu")


async def main():
    now = [100.0]
    session = Session(delay=4.0, clock=lambda: now[0])
    live = Live()

    session.doorbell_pressed()
    session.attach_live(live)
    session.set_live_ready(live)
    now[0] = 105.0

    server = ws_module.TalkWebSocket(session)
    tablet = FakeWS()

    async def fake_auth(token):
        return {"id": "test-user"}

    with patch.object(ws_module, "identify_ha_user", fake_auth), \
         patch.object(ws_module, "can_use_talkback", return_value=True):

        task = asyncio.create_task(server.handle(tablet))

        try:
            await tablet.push("token")
            await tablet.push("START")
            await wait_for(lambda: "START_OK" in tablet.sent)

            live.talk_controller.state = "active"
            print("1. START: OK")

            # Symulujemy zerwanie połączenia przez anulowanie
            # zadania obsługującego WebSocket.
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

            assert server.owner is tablet
            assert session.should_talk(live) is False
            print("2. DISCONNECT: żądanie zatrzymane")
            print("3. ACTIVE: właściciel zachowany")

            live.talk_controller.state = "stopping"
            async with server.owner_lock:
                server._release_finished_owner()
            assert server.owner is tablet
            print("4. STOPPING: właściciel zachowany")

            live.talk_controller.state = "idle"
            async with server.owner_lock:
                server._release_finished_owner()
            assert server.owner is None
            print("5. IDLE: właściciel zwolniony")

            print("DISCONNECT TEST PASSED")
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)


asyncio.run(main())
