"""Read-only health probes for the scheduler and database."""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


def probe_health(scheduler: object, engine: Engine) -> None:
    """Raise if the scheduler, its required jobs, or the database is unavailable."""
    if not getattr(scheduler, "running", False):
        raise RuntimeError("Reminder scheduler is stopped")
    expected = {"daily_reminder_check", "hourly_reminder_recovery", "daily_sqlite_backup"}
    actual = {job.id for job in scheduler.get_jobs()}
    if not expected.issubset(actual):
        raise RuntimeError(f"Scheduler missing jobs: {sorted(expected - actual)}")
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


async def monitor_health(scheduler: object, engine: Engine, interval: float = 60) -> None:
    """Allow systemd to restart after sustained health failures."""
    failures = 0
    while True:
        await asyncio.sleep(interval)
        try:
            probe_health(scheduler, engine)
            failures = 0
        except Exception:
            failures += 1
            logger.exception("Application health check failed (%s/3)", failures)
            if failures >= 3:
                raise RuntimeError("Application health checks failed repeatedly") from None
