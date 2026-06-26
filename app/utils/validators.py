"""Input validators used by services and bot FSM steps (spec §11, §12)."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from app.utils.dates import parse_user_date


class ValidationError(ValueError):
    """Raised when a user-supplied value fails validation."""


def validate_name(value: str) -> str:
    trimmed = value.strip()
    if not trimmed:
        raise ValidationError("Название не может быть пустым.")
    if len(trimmed) > 100:
        raise ValidationError("Название не должно превышать 100 символов.")
    return trimmed


def validate_category(value: str) -> str:
    trimmed = value.strip()
    if not trimmed:
        raise ValidationError("Категория не может быть пустой.")
    if len(trimmed) > 50:
        raise ValidationError("Категория не должна превышать 50 символов.")
    return trimmed


def validate_price(value: str) -> float:
    cleaned = value.strip().replace(",", ".")
    if not cleaned:
        raise ValidationError("Введите стоимость числом, например: 9.99")
    try:
        amount = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValidationError("Введите стоимость числом, например: 9.99") from exc
    if amount <= 0:
        raise ValidationError("Стоимость должна быть больше нуля.")
    return float(amount)


def validate_currency(value: str) -> str:
    trimmed = value.strip().upper()
    if not trimmed:
        raise ValidationError("Валюта не может быть пустой.")
    if len(trimmed) > 10:
        raise ValidationError("Код валюты не должен превышать 10 символов.")
    if not re.fullmatch(r"[A-Z0-9]+", trimmed):
        raise ValidationError(
            "Валюта должна состоять из латинских букв и цифр (например, RUB, USD, EUR, TRY)."
        )
    return trimmed


def validate_billing_period(value: str) -> str:
    allowed = {"weekly", "monthly", "quarterly", "yearly", "manual"}
    normalized = value.strip().lower()
    if normalized not in allowed:
        raise ValidationError(
            "Период должен быть одним из: еженедельно, ежемесячно, ежеквартально, "
            "ежегодно, вручную."
        )
    return normalized


_BILLING_PERIOD_LABELS: dict[str, str] = {
    "weekly": "Еженедельно",
    "monthly": "Ежемесячно",
    "quarterly": "Ежеквартально",
    "yearly": "Ежегодно",
    "manual": "Вручную",
}


def billing_period_label(period: str) -> str:
    return _BILLING_PERIOD_LABELS.get(period, period)


def validate_billing_date(value: str) -> str:
    try:
        parse_user_date(value)
    except ValueError as exc:
        raise ValidationError("Дата должна быть в формате ДД.ММ.ГГГГ.") from exc
    return value.strip()


def validate_optional_text(value: str, *, max_length: int, field: str) -> str | None:
    trimmed = value.strip()
    if not trimmed:
        return None
    if len(trimmed) > max_length:
        raise ValidationError(f"{field} не должно превышать {max_length} символов.")
    return trimmed


def validate_optional_url(value: str) -> str | None:
    trimmed = value.strip()
    if not trimmed or trimmed == "-":
        return None
    parsed = urlparse(trimmed)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValidationError("Введите корректную ссылку, начинающуюся с http:// или https://.")
    if len(trimmed) > 500:
        raise ValidationError("Ссылка не должна превышать 500 символов.")
    return trimmed


__all__ = [
    "ValidationError",
    "billing_period_label",
    "validate_billing_date",
    "validate_billing_period",
    "validate_category",
    "validate_currency",
    "validate_name",
    "validate_optional_text",
    "validate_optional_url",
    "validate_price",
]
