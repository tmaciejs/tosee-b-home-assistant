import asyncio
import importlib.util
import unittest
from importlib.machinery import SourceFileLoader

loader_session = SourceFileLoader(
    "tosee_b.talk_session_candidate",
    "src/tosee_b/talk_session.py.candidate",
)
spec_session = importlib.util.spec_from_loader(
    loader_session.name, loader_session
)
module_session = importlib.util.module_from_spec(spec_session)
spec_session.loader.exec_module(module_session)
TalkSession = module_session.TalkSession


def load_candidate():
    loader = SourceFileLoader(
        "tosee_b.talk_ws_candidate",
        "src/tosee_b/talk_ws.py.new",
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeController:
    state = "idle"


class FakeLive:
    def __init__(self):
        self.talk_controller = FakeController()


class OwnerRecoveryTests(unittest.TestCase):
    def test_owner_released_after_confirmed_stop(self):
        async def scenario():
            now = [100.0]
            session = TalkSession(
                delay=4.0,
                clock=lambda: now[0],
            )
            live = FakeLive()

            session.doorbell_pressed()
            session.attach_live(live)
            session.set_live_ready(live)
            now[0] = 105.0

            module = load_candidate()
            server = module.TalkWebSocket(session)

            tablet_a = object()
            server.owner = tablet_a

            self.assertTrue(session.request_talk())

            live.talk_controller.state = "active"
            session.stop_talk()
            live.talk_controller.state = "stopping"

            self.assertNotEqual(
                session.talk_status(), "idle"
            )

            # Symulacja potwierdzonego STOP 08.
            live.talk_controller.state = "idle"

            self.assertEqual(
                session.talk_status(), "idle"
            )

            # Zwalnianie rezerwacji podczas synchronizacji WS.
            async with server.owner_lock:
                server._release_finished_owner()

            self.assertIsNone(server.owner)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
