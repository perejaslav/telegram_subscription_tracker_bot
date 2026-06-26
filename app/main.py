"""Application entry point.

Wires the aiogram dispatcher, starts long polling and shuts down gracefully.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from contextlib import suppress

from aiogram import Bot, Dispatcher

from app.bot.handlers import start as start_handler
from app.config.settings import settings
from app.logging.setup import setup_logging
from app.database.engine import engine  # noqa: F401  (import to ensure init)
from app.scheduler.jobs import build_scheduler

logger = logging.getLogger(__name__)


async def main() -> None:
    """Configure services and start polling."""
    setup_logging()
    logger.info("Bot starting up")

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()
    start_handler.register_handlers(dp)

    # Graceful shutdown on SIGINT / SIGTERM (Windows: only SIGINT works).
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _request_stop() -> None:
        logger.info("Shutdown signal received")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError, ValueError):
            loop.add_signal_handler(sig, _request_stop)

    polling_task = asyncio.create_task(dp.start_polling(bot))

    scheduler = build_scheduler(bot)
    scheduler.start()
    logger.info("Scheduler started: daily reminder check at 09:00")

    await stop_event.wait()

    logger.info("Stopping polling and scheduler…")
    scheduler.shutdown(wait=False)
    await dp.stop_polling()
    polling_task.cancel()
    with suppress(asyncio.CancelledError):
        await polling_task

    await bot.session.close()
    logger.info("Bot stopped cleanly")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
