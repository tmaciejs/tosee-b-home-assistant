import asyncio
import importlib.util
from importlib.machinery import SourceFileLoader
from unittest.mock import patch

from tosee_b.talk_session import TalkSession


def load_candidate(name, path):
    loader = SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


session_module = load_candidate(
    "tosee_b.talk_session_candidate_handover",
    "src/tosee_b/talk_session.py.candidate",
)
ws_module = load_candidate(
    "tosee_b.talk_ws_candidate_handover",
    "src/tosee_b/talk_ws.py.new",
)


class FakeController:
    def __init__(self):
        self.state = "idle"


class FakeLive:
    def __init__(self):
        self.talk_controller = FakeController()


class FakeWS:
    def __init__(self):
        self.messages = asyncio.Queue()
        self.sent = []

    async def recv(self):
        return await self.messages.get()

    async def send(self, message):
        self.sent.append(message)

    async def close(self, code=1000, reason=""):
        pass

    async def push(self, message):
        await self.messages.put(message)


async def wait_for(condition):
    for _ in range(100):
        if condition():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("Timeout oczekiwania na odpowiedz WS")


async def main():
    now = [100.0]
    session = session_module.TalkSession(
        delay=4.0, clock=lambda: now[0]
    )
    live = FakeLive()

    session.doorbell_pressed()
    session.attach_live(live)
    session.set_live_ready(live)
    now[0] = 105.0

    server = ws_module.TalkWebSocket(session)
    a, b = FakeWS(), FakeWS()

    async def fake_auth(token):
        return {"id": "test", "is_owner": True}

    with patch.object(ws_module, "identify_ha_user", fake_auth), \
         patch.object(ws_module, "can_use_talkback", return_value=True):

        tasks = [
            asyncio.create_task(server.handle(a)),
            asyncio.create_task(server.handle(b)),
        ]
        try:
            await a.push("token-A")
            await b.push("token-B")

            await a.push("START")
            await wait_for(lambda: "START_OK" in a.sent)
            assert server.owner is a
            live.talk_controller.state = "active"
            print("1. Tablet A: START OK")

            await a.push("STOP")
            await wait_for(lambda: "STOP_OK" in a.sent)

            # STOP zaakceptowany, ale jeszcze niepotwierdzony.
            live.talk_controller.state = "stopping"
            assert server.owner is a, (
                "BLAD: wlasciciel zwolniony przed ACK STOP"
            )
            print("2. STOPPING: wlasciciel zachowany")

            await b.push("START")
            await wait_for(lambda: "START_BLOCKED" in b.sent)
            print("3. Tablet B: START zablokowany")

            # Symulujemy poprawny ACK + RESPONSE STOP 08.
            live.talk_controller.state = "idle"
            await b.push("STATUS")
            await wait_for(
                lambda: any(
                    msg.startswith("STATUS:") for msg in b.sent
                )
            )

            await wait_for(lambda: server.owner is None)
            print("4. IDLE: wlasciciel zwolniony")

            await b.push("START")
            await wait_for(lambda: "START_OK" in b.sent)
            assert server.owner is b
            print("5. Tablet B: przejecie OK")

            print("HANDOVER TEST PASSED")
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


asyncio.run(main())
