"""Validated per-user reminder preferences stored in SQLite."""

from __future__ import annotations

from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.config.settings import settings
from app.database.models import UserSettings


@dataclass(frozen=True)
class ReminderPreferences:
    timezone: str
    days: tuple[int, ...]


def parse_reminder_days(raw: str) -> tuple[int, ...]:
    try:
        values = tuple(sorted({int(part.strip()) for part in raw.split(",")}))
    except ValueError as exc:
        raise ValueError("Укажите дни через запятую, например 1,3,7.") from exc
    if not values or any(day < 0 or day > 365 for day in values) or len(values) > 20:
        raise ValueError("Допускается от 1 до 20 значений в диапазоне 0–365.")
    return values


def validate_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("Неизвестный часовой пояс. Например: Europe/Istanbul.") from exc
    return value


def get_preferences(session: Session, user_id: int) -> ReminderPreferences:
    record = session.query(UserSettings).filter_by(user_id=user_id).one_or_none()
    if record is None:
        return ReminderPreferences(settings.timezone, tuple(settings.reminder_days))
    return ReminderPreferences(record.timezone, parse_reminder_days(record.reminder_days))


def update_preferences(
    session: Session, user_id: int, *, timezone: str | None = None, days: str | None = None
) -> ReminderPreferences:
    if timezone is not None:
        timezone = validate_timezone(timezone)
    parsed_days = parse_reminder_days(days) if days is not None else None
    record = session.query(UserSettings).filter_by(user_id=user_id).one_or_none()
    if record is None:
        record = UserSettings(
            user_id=user_id,
            timezone=settings.timezone,
            reminder_days=",".join(map(str, settings.reminder_days)),
        )
        session.add(record)
    if timezone is not None:
        record.timezone = timezone
    if parsed_days is not None:
        record.reminder_days = ",".join(map(str, parsed_days))
    session.commit()
    return get_preferences(session, user_id)
