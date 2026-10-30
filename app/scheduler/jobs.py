"""APScheduler wiring — runs the daily reminder check."""

from __future__ import annotations

import logging
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config.settings import settings
from app.services.backup_service import BackupService
from app.services.reminder_service import run_reminder_check

logger = logging.getLogger(__name__)


def _resolve_timezone() -> ZoneInfo:
    try:
        return ZoneInfo(settings.timezone)
    except ZoneInfoNotFoundError:
        logger.warning("Unknown timezone %s — falling back to UTC", settings.timezone)
        return ZoneInfo("UTC")


def build_scheduler(bot: Bot) -> AsyncIOScheduler:
    """Build the AsyncIOScheduler configured to run daily at 09:00 local time."""
    scheduler = AsyncIOScheduler(timezone=_resolve_timezone())
    scheduler.add_job(
        run_reminder_check,
        trigger=CronTrigger(hour=9, minute=0, timezone=_resolve_timezone()),
        misfire_grace_time=86400,
        kwargs={"bot": bot},
        id="daily_reminder_check",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    # Catch up after missed daily runs and retry transient delivery failures.
    # Sent-only idempotency in ReminderLogRepository prevents same-day duplicates.
    scheduler.add_job(
        run_reminder_check,
        trigger=IntervalTrigger(hours=1, timezone=_resolve_timezone()),
        kwargs={"bot": bot},
        id="hourly_reminder_recovery",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        BackupService().create_backup,
        trigger=CronTrigger(hour=3, minute=0, timezone=_resolve_timezone()),
        id="daily_sqlite_backup",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=86400,
    )
    return scheduler


__all__ = ["build_scheduler"]
