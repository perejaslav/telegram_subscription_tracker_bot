"""Run production job entry points against isolated SQLite and fake Telegram."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramNetworkError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.engine import Base
from app.services import reminder_service
from app.services.backup_service import BackupService
from app.services.subscription_service import SubscriptionInput, SubscriptionService


@pytest.mark.asyncio
async def test_real_jobs_share_isolated_database_and_restore(tmp_path: Path, monkeypatch) -> None:
    """Exercise production reminder job and backup with an actual persistent DB."""
    db_path = tmp_path / "isolated.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(reminder_service, "SessionLocal", factory)
    today = date(2026, 6, 26)
    with factory() as session:
        SubscriptionService(session).create(
            reminder_service.settings.admin_telegram_id,
            SubscriptionInput(
                name="Integration reminder",
                category="ИИ",
                price=10,
                currency="USD",
                billing_period="monthly",
                next_billing_date=today + timedelta(days=1),
            ),
        )

    class Bot:
        sent: list[str] = []

        async def send_message(self, _chat_id: int, message: str) -> None:
            self.sent.append(message)

    bot = Bot()
    first = await reminder_service.run_reminder_check(bot, today=today)
    second = await reminder_service.run_reminder_check(bot, today=today)
    assert first.sent == 1 and second.sent == 0
    assert len(bot.sent) == 1

    service = BackupService(backups_dir=tmp_path / "backups", database_url=f"sqlite:///{db_path}")
    artifact = service.create_backup()
    service.verify_restore(artifact.path)
    with sqlite3.connect(artifact.path) as restored:
        assert restored.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert (
            restored.execute("SELECT COUNT(*) FROM reminder_logs WHERE status='sent'").fetchone()[0]
            == 1
        )
    engine.dispose()


@pytest.mark.asyncio
async def test_transient_telegram_outage_then_backup_contains_only_confirmed_sent(
    tmp_path: Path, monkeypatch
) -> None:
    """Real reminder entry point recovers on next run without false delivery."""
    db_path = tmp_path / "outage.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(reminder_service, "SessionLocal", factory)
    monkeypatch.setattr(reminder_service.asyncio, "sleep", AsyncMock())
    today = date(2026, 6, 26)
    with factory() as session:
        SubscriptionService(session).create(
            reminder_service.settings.admin_telegram_id,
            SubscriptionInput(
                name="Outage recovery",
                category="ИИ",
                price=10,
                currency="USD",
                billing_period="monthly",
                next_billing_date=today + timedelta(days=1),
            ),
        )

    bot = type("Bot", (), {})()
    bot.send_message = AsyncMock(side_effect=TelegramNetworkError(method=None, message="offline"))
    failed = await reminder_service.run_reminder_check(bot, today=today)
    assert failed.sent == 0 and failed.failed == 1
    assert bot.send_message.await_count == 3

    backup = BackupService(backups_dir=tmp_path / "backups", database_url=f"sqlite:///{db_path}")
    before = backup.create_backup()
    backup.verify_restore(before.path)
    with sqlite3.connect(before.path) as connection:
        assert (
            connection.execute("SELECT count(*) FROM reminder_logs WHERE status='sent'").fetchone()[
                0
            ]
            == 0
        )

    bot.send_message.side_effect = None
    recovered = await reminder_service.run_reminder_check(bot, today=today)
    duplicate = await reminder_service.run_reminder_check(bot, today=today)
    assert recovered.sent == 1 and duplicate.sent == 0
    after = backup.create_backup()
    backup.verify_restore(after.path)
    with sqlite3.connect(after.path) as connection:
        assert (
            connection.execute("SELECT count(*) FROM reminder_logs WHERE status='sent'").fetchone()[
                0
            ]
            == 1
        )
    engine.dispose()
