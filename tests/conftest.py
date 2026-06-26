"""Pytest configuration and shared fixtures."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Set required env vars BEFORE any app import so pydantic-settings is happy.
os.environ.setdefault("BOT_TOKEN", "1234567890:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
os.environ.setdefault("ADMIN_TELEGRAM_ID", "123456789")
os.environ.setdefault("TIMEZONE", "UTC")
os.environ.setdefault("REMINDER_DAYS", "1,3,7")


@pytest.fixture()
def temp_db() -> Iterator[str]:
    """Yield a fresh SQLite path inside a temp directory; cleanup after."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "test.db")
        yield f"sqlite:///{path}"


@pytest.fixture()
def session(temp_db: str) -> Iterator[Session]:
    """Build an in-memory schema and yield a fresh Session for each test."""
    from app.database import models  # noqa: F401  (registers metadata)
    from app.database.engine import Base

    engine = create_engine(temp_db, future=True)
    Base.metadata.create_all(engine)
    SessionTesting = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    sess = SessionTesting()
    try:
        yield sess
    finally:
        sess.close()
        engine.dispose()


class FakeBot:
    """In-memory replacement for ``aiogram.Bot.send_message``."""

    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    def send_message(self, chat_id: int, text: str, **_kwargs) -> None:
        self.sent.append((chat_id, text))


@pytest.fixture()
def fake_bot() -> FakeBot:
    return FakeBot()


@pytest.fixture()
def admin_id() -> int:
    return int(os.environ["ADMIN_TELEGRAM_ID"])
