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
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from apscheduler.events import EVENT_JOB_ERROR

# Ensure ORM models are imported so Base.metadata is fully populated.
import app.database.models  # noqa: F401
from app.bot.handlers import start as start_handler
from app.config.settings import PROJECT_ROOT, settings
from app.database.engine import Base, engine
from app.logging.setup import setup_logging
from app.scheduler.jobs import build_scheduler
from app.services.health_service import monitor_health, probe_health

logger = logging.getLogger(__name__)


async def wait_for_stop_or_failure(
    polling_task: asyncio.Task,
    stop_event: asyncio.Event,
    health_task: asyncio.Task,
    scheduler_failure_task: asyncio.Task,
) -> None:
    """Return for requested shutdown; raise if polling or health stops unexpectedly."""
    stop_task = asyncio.create_task(stop_event.wait())
    try:
        done, _ = await asyncio.wait(
            {polling_task, stop_task, health_task, scheduler_failure_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        # aiogram handles SIGTERM internally and may finish polling before our
        # stop task wakes. Treat either completion as a requested shutdown.
        if stop_event.is_set():
            return
        if scheduler_failure_task in done:
            raise RuntimeError("Scheduler job failed; restarting bot for recovery")
        if health_task in done:
            await health_task
            raise RuntimeError("Health monitor stopped unexpectedly")
        if polling_task in done:
            try:
                await polling_task
            except Exception:
                logger.exception("Telegram polling crashed; systemd will restart the service")
                raise
            raise RuntimeError("Telegram polling stopped unexpectedly")
    finally:
        stop_task.cancel()
        with suppress(asyncio.CancelledError):
            await stop_task


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

    # Keep signal ownership in this entry point. aiogram's default signal
    # handlers otherwise replace _request_stop and cause false crash reports.
    polling_task = asyncio.create_task(dp.start_polling(bot, handle_signals=False))

    scheduler = build_scheduler(bot)
    scheduler_failed = asyncio.Event()

    def _on_scheduler_error(event: object) -> None:
        logger.error("Scheduled job failed: %s", getattr(event, "job_id", "unknown"))
        scheduler_failed.set()

    scheduler.add_listener(_on_scheduler_error, EVENT_JOB_ERROR)
    scheduler.start()
    probe_health(scheduler, engine)
    logger.info("Scheduler started: daily reminder check at 09:00")

    marker = Path(PROJECT_ROOT) / "data" / ".bot-active"
    recovered = marker.exists()
    marker.touch()
    health_task = asyncio.create_task(monitor_health(scheduler, engine))
    scheduler_failure_task = asyncio.create_task(scheduler_failed.wait())

    try:
        if recovered:
            try:
                await bot.send_message(
                    settings.admin_telegram_id,
                    "Бот восстановил работу после неожиданного завершения.",
                )
            except Exception:
                logger.exception("Could not deliver recovery notice")
        await wait_for_stop_or_failure(
            polling_task, stop_event, health_task, scheduler_failure_task
        )
        marker.unlink(missing_ok=True)

    finally:
        logger.info("Stopping polling and scheduler…")
        health_task.cancel()
        scheduler_failure_task.cancel()
        with suppress(asyncio.CancelledError):
            await health_task
        with suppress(asyncio.CancelledError):
            await scheduler_failure_task
        with suppress(Exception):
            scheduler.shutdown(wait=False)
        if not polling_task.done():
            with suppress(Exception):
                await dp.stop_polling()
        if not polling_task.done():
            try:
                await asyncio.wait_for(asyncio.shield(polling_task), timeout=5)
            except Exception:
                polling_task.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await polling_task
        await bot.session.close()
        logger.info("Bot stopped cleanly")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
