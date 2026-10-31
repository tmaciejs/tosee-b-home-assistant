import asyncio
import importlib.util
from importlib.machinery import SourceFileLoader
from unittest.mock import patch

PATH = "src/tosee_b/talk_ws.py.new"
NAME = "tosee_b.talk_ws_candidate"

loader = SourceFileLoader(NAME, PATH)
spec = importlib.util.spec_from_loader(NAME, loader)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FakeSession:
    def __init__(self):
        self.talking = False
        self.stops = 0

    def request_talk(self):
        if self.talking:
            return False
        self.talking = True
        return True

    def stop_talk(self):
        self.talking = False
        self.stops += 1

    def talk_status(self):
        return "active" if self.talking else "idle"

    def accept_audio_from_browser(self, frame):
        return self.talking and len(frame) == 320


class FakeWS:
    def __init__(self):
        self.messages = asyncio.Queue()
        self.sent = []
        self.closed = False

    async def recv(self):
        return await self.messages.get()

    async def send(self, message):
        self.sent.append(message)

    async def close(self, code=1000, reason=""):
        self.closed = True

    async def push(self, message):
        await self.messages.put(message)


async def wait_for(condition):
    for _ in range(100):
        if condition():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("Przekroczono czas oczekiwania")


async def main():
    session = FakeSession()
    server = module.TalkWebSocket(session)

    async def fake_auth(token):
        return {"id": "test-user", "is_owner": True}

    tablet_a = FakeWS()
    tablet_b = FakeWS()

    with patch.object(module, "identify_ha_user", fake_auth), \
         patch.object(module, "can_use_talkback", return_value=True):

        tasks = [
            asyncio.create_task(server.handle(tablet_a)),
            asyncio.create_task(server.handle(tablet_b)),
        ]

        try:
            await tablet_a.push("token-A")
            await tablet_b.push("token-B")
            await wait_for(
                lambda: sum(
                    1 for t in tasks if not t.done()
                ) == 2
            )

            await tablet_a.push("STATUS")
            await tablet_b.push("STATUS")
            await wait_for(
                lambda: len(tablet_a.sent) >= 1
                and len(tablet_b.sent) >= 1
            )

            assert tablet_a.sent[-1] == "STATUS:idle"
            assert tablet_b.sent[-1] == "STATUS:idle"
            print("TEST 1: Oba tablety monitoruja STATUS — OK")

            await tablet_a.push("START")
            await wait_for(
                lambda: "START_OK" in tablet_a.sent
            )

            assert server.owner is tablet_a
            print("TEST 2: Tablet A rezerwuje rozmowe — OK")

            await tablet_b.push("START")
            await wait_for(
                lambda: "START_BLOCKED" in tablet_b.sent
            )

            await tablet_b.push("STOP")
            await wait_for(
                lambda: "STOP_OK" in tablet_b.sent
            )

            assert session.talking
            assert session.stops == 0
            assert server.owner is tablet_a
            print("TEST 3: Tablet B nie zatrzymuje rozmowy A — OK")

            await tablet_a.push("STOP")
            await wait_for(
                lambda: "STOP_OK" in tablet_a.sent
            )

            assert not session.talking
            assert server.owner is None
            print("TEST 4: STOP zwalnia rozmowe — OK")

            await tablet_b.push("START")
            await wait_for(
                lambda: "START_OK" in tablet_b.sent
            )

            assert server.owner is tablet_b
            print("TEST 5: Tablet B przejmuje rozmowe — OK")

        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(
                *tasks, return_exceptions=True
            )


asyncio.run(main())
