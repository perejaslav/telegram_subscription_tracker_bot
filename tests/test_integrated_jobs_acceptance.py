"""Run production job entry points against isolated SQLite and fake Telegram."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest
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
