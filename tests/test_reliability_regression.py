"""Regression tests for real delivery semantics and recoverable backups."""

from __future__ import annotations

import asyncio
import os
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramNetworkError
from sqlalchemy.orm import Session

from app.database.models import ReminderLog
from app.main import wait_for_stop_or_failure
from app.services.backup_service import BackupService
from app.services.health_service import probe_health
from app.services.reminder_service import ReminderService
from app.services.subscription_service import SubscriptionInput, SubscriptionService


def create_subscription(session: Session, user: int, due: date) -> None:
    SubscriptionService(session).create(
        user,
        SubscriptionInput(
            name="Sample & <tag>",
            category="ИИ",
            price=12.5,
            currency="USD",
            billing_period="monthly",
            next_billing_date=due,
        ),
    )


@pytest.mark.asyncio
async def test_retry_then_success_no_duplicate(session: Session, admin_id: int) -> None:
    today = date(2026, 6, 26)
    create_subscription(session, admin_id, today + timedelta(days=3))
    bot = AsyncMock()
    bot.send_message.side_effect = [TelegramNetworkError(method=None, message="offline"), None]
    service = ReminderService(session, bot)
    assert (await service.run_daily_check(today=today)).sent == 1
    assert bot.send_message.await_count == 2
    assert "&amp;" in bot.send_message.await_args.args[1]
    assert (await service.run_daily_check(today=today)).sent == 0
    assert bot.send_message.await_count == 2


@pytest.mark.asyncio
async def test_failed_delivery_not_marked_sent(session: Session, admin_id: int) -> None:
    today = date(2026, 6, 26)
    create_subscription(session, admin_id, today + timedelta(days=1))
    bot = AsyncMock()
    bot.send_message.side_effect = TelegramNetworkError(method=None, message="offline")
    outcome = await ReminderService(session, bot).run_daily_check(today=today)
    assert outcome.failed == 1 and outcome.sent == 0
    assert bot.send_message.await_count == 3
    assert session.query(ReminderLog).count() == 0
    bot.send_message.side_effect = None
    assert (await ReminderService(session, bot).run_daily_check(today=today)).sent == 1


@pytest.mark.asyncio
async def test_catchup_and_no_repeat_after_prior_day(session: Session, admin_id: int) -> None:
    today = date(2026, 6, 26)
    create_subscription(session, admin_id, today + timedelta(days=6))
    bot = AsyncMock()
    assert (await ReminderService(session, bot).run_daily_check(today=today)).sent == 1
    assert (await ReminderService(session, bot).run_daily_check(today=today)).sent == 0
    assert (
        await ReminderService(session, bot).run_daily_check(today=today + timedelta(days=1))
    ).sent == 0


def test_sqlite_backup_restore_and_retention(tmp_path: Path) -> None:
    original = tmp_path / "db.sqlite"
    connection = sqlite3.connect(original)
    connection.execute("CREATE TABLE item (name TEXT)")
    connection.execute("INSERT INTO item VALUES ('present')")
    connection.commit()
    connection.close()
    backups = tmp_path / "backups"
    backup_service = BackupService(backups_dir=backups, database_url=f"sqlite:///{original}")
    output = backup_service.create_backup()
    backup_service.verify_restore(output.path)
    with sqlite3.connect(output.path) as restored:
        assert restored.execute("SELECT name FROM item").fetchone()[0] == "present"
    stale = backups / "subscriptions_stale.db"
    stale.write_bytes(b"old")
    old_time = __import__("time").time() - 32 * 86400
    os.utime(stale, (old_time, old_time))
    backup_service.cleanup_old_backups()
    assert not stale.exists()
    assert output.path.exists()


def test_health_probe_detects_stopped_scheduler(session: Session) -> None:
    scheduler = AsyncMock()
    scheduler.running = False
    with pytest.raises(RuntimeError, match="stopped"):
        probe_health(scheduler, session.bind)


def test_health_probe_detects_missing_jobs(session: Session) -> None:
    scheduler = AsyncMock()
    scheduler.running = True
    scheduler.get_jobs = lambda: []
    with pytest.raises(RuntimeError, match="missing jobs"):
        probe_health(scheduler, session.bind)


def test_health_probe_accepts_live_db_and_jobs(session: Session) -> None:
    scheduler = AsyncMock()
    scheduler.running = True
    scheduler.get_jobs = lambda: [
        type("Job", (), {"id": name})()
        for name in ("daily_reminder_check", "hourly_reminder_recovery", "daily_sqlite_backup")
    ]
    probe_health(scheduler, session.bind)


@pytest.mark.asyncio
async def test_polling_crash_is_reported() -> None:
    async def crash() -> None:
        raise RuntimeError("polling offline")

    polling = asyncio.create_task(crash())
    health = asyncio.create_task(asyncio.sleep(100))
    scheduler_failure = asyncio.create_task(asyncio.sleep(100))
    try:
        with pytest.raises(RuntimeError, match="polling offline"):
            await wait_for_stop_or_failure(polling, asyncio.Event(), health, scheduler_failure)
    finally:
        health.cancel()
        scheduler_failure.cancel()


@pytest.mark.asyncio
async def test_scheduler_error_requests_restart() -> None:
    polling = asyncio.create_task(asyncio.sleep(100))
    health = asyncio.create_task(asyncio.sleep(100))
    scheduler_failure = asyncio.create_task(asyncio.sleep(0))
    try:
        with pytest.raises(RuntimeError, match="Scheduler job failed"):
            await wait_for_stop_or_failure(polling, asyncio.Event(), health, scheduler_failure)
    finally:
        polling.cancel()
        health.cancel()


@pytest.mark.asyncio
async def test_clean_stop_does_not_request_restart() -> None:
    polling = asyncio.create_task(asyncio.sleep(100))
    health = asyncio.create_task(asyncio.sleep(100))
    scheduler_failure = asyncio.create_task(asyncio.sleep(100))
    stop = asyncio.Event()
    stop.set()
    try:
        await wait_for_stop_or_failure(polling, stop, health, scheduler_failure)
    finally:
        polling.cancel()
        health.cancel()
        scheduler_failure.cancel()


@pytest.mark.asyncio
async def test_polling_exits_after_sigterm_without_false_crash() -> None:
    polling = asyncio.create_task(asyncio.sleep(0))
    health = asyncio.create_task(asyncio.sleep(100))
    scheduler_failure = asyncio.create_task(asyncio.sleep(100))
    stop = asyncio.Event()
    stop.set()
    try:
        await wait_for_stop_or_failure(polling, stop, health, scheduler_failure)
    finally:
        health.cancel()
        scheduler_failure.cancel()
