"""Standalone POSIX SIGTERM acceptance probe. Never connects to Telegram."""

import asyncio
import os
import signal
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import app.main as entry

events = []


class FakeBot:
    def __init__(self, *args, **kwargs):
        async def close(_self):
            events.append("session_closed")

        self.session = type("Session", (), {"close": close})()
        self.send_message = AsyncMock(side_effect=AssertionError("Telegram call forbidden"))


class FakeDispatcher:
    def __init__(self):
        self.stop = asyncio.Event()

    async def start_polling(self, bot, **kwargs):
        assert kwargs.get("handle_signals") is False
        events.append("polling_started")
        await self.stop.wait()
        events.append("polling_stopped")

    async def stop_polling(self):
        self.stop.set()


class FakeScheduler:
    def add_listener(self, *args):
        pass

    def start(self):
        events.append("scheduler_started")

    def shutdown(self, wait=False):
        events.append("scheduler_stopped")


async def fake_monitor(*args):
    await asyncio.sleep(300)


async def run():
    entry.Bot = FakeBot
    entry.Dispatcher = FakeDispatcher
    entry.start_handler.register_handlers = lambda dp: None
    entry.Base.metadata.create_all = lambda engine: None
    entry.build_scheduler = lambda bot: FakeScheduler()
    entry.probe_health = lambda *args: None
    entry.monitor_health = fake_monitor
    with tempfile.TemporaryDirectory() as folder:
        entry.PROJECT_ROOT = Path(folder)
        (Path(folder) / "data").mkdir()
        task = asyncio.create_task(entry.main())
        await asyncio.sleep(0.3)
        os.kill(os.getpid(), signal.SIGTERM)
        await asyncio.wait_for(task, 4)
    expected = {
        "polling_started",
        "polling_stopped",
        "scheduler_started",
        "scheduler_stopped",
        "session_closed",
    }
    assert expected.issubset(events), events
    print("SIGTERM_SUCCESS", ",".join(events))


if __name__ == "__main__":
    asyncio.run(run())
