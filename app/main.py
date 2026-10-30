"""Application entry point.

Wires the aiogram dispatcher, creates database tables, starts long polling
and the reminder scheduler, and shuts down gracefully.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# Ensure ORM models are imported so Base.metadata is fully populated.
import app.database.models  # noqa: F401
from app.bot.handlers import start as start_handler
from app.config.settings import settings
from app.database.engine import Base, engine
from app.logging.setup import setup_logging
from app.scheduler.jobs import build_scheduler

logger = logging.getLogger(__name__)


async def main() -> None:
    """Configure services and start polling."""
    setup_logging()
    logger.info("Bot starting up")

    # Create database tables if they don't exist yet (idempotent).
    Base.metadata.create_all(engine)
    logger.info("Database tables verified")

    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
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

    try:
        stop_task = asyncio.create_task(stop_event.wait())
        done, _ = await asyncio.wait({polling_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
        if polling_task in done:
            stop_task.cancel()
            try:
                await polling_task
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Telegram polling crashed; systemd will restart the service")
                raise
            else:
                raise RuntimeError("Telegram polling stopped unexpectedly")
        stop_task.cancel()

    finally:
        logger.info("Stopping polling and scheduler…")
        with suppress(Exception):
            scheduler.shutdown(wait=False)
        if not polling_task.done():
            with suppress(Exception):
                await dp.stop_polling()
        if not polling_task.done():
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
