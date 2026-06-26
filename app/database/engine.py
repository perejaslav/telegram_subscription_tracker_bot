"""Database engine, session factory and base class."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config.settings import PROJECT_ROOT, settings


def _resolve_sqlite_path(url: str) -> str:
    """Ensure the SQLite parent directory exists; return unchanged URL."""
    if not url.startswith("sqlite"):
        return url
    # sqlite:///data/subscriptions.db → data/subscriptions.db
    db_path = url.replace("sqlite:///", "", 1)
    if not db_path or db_path == ":memory:":
        return url
    full = Path(db_path)
    if not full.is_absolute():
        full = PROJECT_ROOT / full
    full.parent.mkdir(parents=True, exist_ok=True)
    return url


class Base(DeclarativeBase):
    """Declarative base for ORM models."""


def build_engine() -> Engine:
    """Create the SQLAlchemy engine from settings."""
    resolved = _resolve_sqlite_path(settings.database_url)
    connect_args: dict[str, object] = {}
    if resolved.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(resolved, echo=False, future=True, connect_args=connect_args)


engine: Engine = build_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


def get_session() -> Iterator[Session]:
    """Yield a transactional session (used outside of FastAPI-style DI)."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


__all__ = ["Base", "SessionLocal", "engine", "get_session"]