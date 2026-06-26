"""Date helpers (spec §11, §12)."""

from __future__ import annotations

from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

USER_DATE_FORMAT = "%d.%m.%Y"


def parse_user_date(value: str) -> date:
    """Parse ``ДД.ММ.ГГГГ`` into a :class:`datetime.date`.

    Raises:
        ValueError: if the value does not match the expected format
            or refers to an impossible date (e.g. 31.02).
    """
    return datetime.strptime(value.strip(), USER_DATE_FORMAT).date()  # type: ignore[name-defined]


def format_date(value: date) -> str:
    """Format a date as ``ДД.ММ.ГГГГ`` for user-facing messages."""
    return value.strftime(USER_DATE_FORMAT)


def shift_date(value: date, period: str) -> date:
    """Shift ``value`` forward by one billing period.

    ``31.01`` + ``monthly`` → ``28.02`` (or ``29.02`` in a leap year) thanks to
    :class:`relativedelta`'s "last-day-of-month" semantics when the day is the
    last day of the source month. Otherwise the day is preserved when possible
    and clamped to the last valid day of the target month.
    """
    p = period.lower()
    if p == "weekly":
        return value + timedelta(weeks=1)
    if p == "monthly":
        return value + relativedelta(months=1)
    if p == "quarterly":
        return value + relativedelta(months=3)
    if p == "yearly":
        return value + relativedelta(years=1)
    raise ValueError(f"Unsupported billing period: {period}")


def days_until(target: date, today: date | None = None) -> int:
    """Whole-day delta from ``today`` to ``target``."""
    base = today or date.today()
    return (target - base).days


__all__ = [
    "USER_DATE_FORMAT",
    "days_until",
    "format_date",
    "parse_user_date",
    "shift_date",
]


# ``datetime`` is imported lazily so the public surface stays tidy.
from datetime import datetime  # noqa: E402
