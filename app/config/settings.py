"""Application settings loaded from environment variables / .env file."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Project root (this file is app/config/settings.py → parents[2] == root).
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Typed application configuration."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    bot_token: str = Field(..., min_length=10, description="Telegram Bot API token")
    admin_telegram_id: int = Field(..., gt=0, description="Allowed Telegram user ID")
    timezone: str = Field(default="UTC", description="IANA timezone name")
    reminder_days: Annotated[list[int], NoDecode] = Field(
        default_factory=lambda: [1, 3, 7],
        description="Days before billing to send a reminder",
    )
    database_url: str = Field(
        default="sqlite:///data/subscriptions.db",
        description="SQLAlchemy database URL",
    )
    log_level: str = Field(default="INFO", description="Python logging level")

    @field_validator("reminder_days", mode="before")
    @classmethod
    def _parse_reminder_days(cls, value: object) -> object:
        """Allow comma-separated string in .env (e.g. ``REMINDER_DAYS=1,3,7``)."""
        if isinstance(value, str):
            parts = [p.strip() for p in value.split(",") if p.strip()]
            return [int(p) for p in parts]
        return value

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = value.upper()
        if upper not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(allowed)}")
        return upper

    @field_validator("reminder_days")
    @classmethod
    def _validate_reminder_days(cls, value: list[int]) -> list[int]:
        if not value:
            raise ValueError("REMINDER_DAYS must not be empty")
        if any(d < 0 for d in value):
            raise ValueError("REMINDER_DAYS must contain non-negative integers")
        # Deduplicate and sort ascending for stable behavior.
        return sorted(set(value))


def get_settings() -> Settings:
    """Build a fresh :class:`Settings` instance.

    Using a factory (instead of a module-level singleton) keeps the settings
    easy to override in tests and avoids import-time side effects.
    """
    return Settings()  # type: ignore[call-arg]


settings: Settings = get_settings()
