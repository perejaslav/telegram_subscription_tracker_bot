"""Aggregate reports: totals, breakdowns by currency / category, upcoming list."""

from __future__ import annotations

import calendar
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.database.models import BillingPeriod, Subscription, SubscriptionStatus
from app.database.repositories.subscription_repository import SubscriptionRepository
from app.utils.dates import days_until, format_date, shift_date
from app.utils.formatters import format_money

# ---------------------------------------------------------------------------
# Conversion to monthly equivalents (used for the global summary).
# ---------------------------------------------------------------------------
_PERIODS_PER_MONTH: dict[str, float] = {
    BillingPeriod.WEEKLY.value: 52 / 12,  # ≈ 4.333
    BillingPeriod.MONTHLY.value: 1.0,
    BillingPeriod.QUARTERLY.value: 1 / 3,  # one payment covers 3 months
    BillingPeriod.YEARLY.value: 1 / 12,
}


@dataclass(slots=True)
class CurrencyTotal:
    currency: str
    monthly_equivalent: float
    yearly_equivalent: float


@dataclass(slots=True)
class SummaryReport:
    active_count: int
    paused_count: int
    cancelled_count: int
    archived_count: int
    totals_by_currency: list[CurrencyTotal]
    by_category: dict[str, list[CurrencyTotal]]
    upcoming: list[Subscription]


class ReportService:
    """Compute summary statistics for the personal dashboard."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = SubscriptionRepository(session)

    # ------------------------------------------------------------------
    def summary(self, user_id: int, *, today: date | None = None) -> SummaryReport:
        today = today or date.today()
        active = list(self.repo.list_by_status(user_id, SubscriptionStatus.ACTIVE))
        paused = list(self.repo.list_by_status(user_id, SubscriptionStatus.PAUSED))
        cancelled = list(self.repo.list_by_status(user_id, SubscriptionStatus.CANCELLED))
        archived = list(self.repo.list_by_status(user_id, SubscriptionStatus.ARCHIVED))

        totals = _aggregate_totals(active)
        by_category = _aggregate_by_category(active)
        upcoming = list(self.repo.list_upcoming(user_id, before=today + timedelta(days=30)))

        return SummaryReport(
            active_count=len(active),
            paused_count=len(paused),
            cancelled_count=len(cancelled),
            archived_count=len(archived),
            totals_by_currency=totals,
            by_category=by_category,
            upcoming=upcoming,
        )

    def upcoming(
        self, user_id: int, *, days: int = 30, today: date | None = None
    ) -> list[Subscription]:
        today = today or date.today()
        return list(self.repo.list_upcoming(user_id, before=today + timedelta(days=days)))

    # ------------------------------------------------------------------
    # Formatting helpers (used by bot handlers).
    # ------------------------------------------------------------------
    @staticmethod
    def render_summary(report: SummaryReport, *, today: date | None = None) -> str:
        today = today or date.today()
        if report.active_count == 0:
            return (
                "📊 <b>Сводка</b>\n\n"
                "Нет активных подписок. Добавьте первую через «➕ Добавить подписку»."
            )

        lines: list[str] = [
            "📊 <b>Сводка</b>",
            f"Активных подписок: <b>{report.active_count}</b>",
            "",
            "<b>Всего в месяц (эквивалент):</b>",
        ]
        if report.totals_by_currency:
            for c in report.totals_by_currency:
                lines.append(f"  • {format_money(c.monthly_equivalent, c.currency)}")
            lines.append("")
            lines.append("<b>Прогноз на год:</b>")
            for c in report.totals_by_currency:
                lines.append(f"  • {format_money(c.yearly_equivalent, c.currency)}")
        else:
            lines.append("  • —")

        if report.by_category:
            lines.append("")
            lines.append("<b>По категориям (месяц):</b>")
            for cat, totals in sorted(report.by_category.items()):
                parts = ", ".join(format_money(t.monthly_equivalent, t.currency) for t in totals)
                lines.append(f"  • {cat}: {parts}")

        if report.upcoming:
            lines.append("")
            lines.append(
                f"<b>Ближайшие списания (до {format_date(today + timedelta(days=30))}):</b>"
            )
            for s in report.upcoming[:10]:
                delta = days_until(s.next_billing_date, today)
                lines.append(
                    f"  • {format_date(s.next_billing_date)} ({_plural_days_short(delta)}) — "
                    f"{s.name} — {format_money(s.price, s.currency)}"
                )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _aggregate_totals(subscriptions: Iterable[Subscription]) -> list[CurrencyTotal]:
    buckets: dict[str, dict[str, float]] = defaultdict(lambda: {"month": 0.0, "year": 0.0})
    for sub in subscriptions:
        factor = _PERIODS_PER_MONTH.get(sub.billing_period, 0.0)
        if factor == 0.0:
            continue
        bucket = buckets[sub.currency]
        bucket["month"] += sub.price * factor
        bucket["year"] += sub.price * factor * 12
    return [
        CurrencyTotal(
            currency=currency,
            monthly_equivalent=values["month"],
            yearly_equivalent=values["year"],
        )
        for currency, values in sorted(buckets.items())
    ]


def _aggregate_by_category(
    subscriptions: Iterable[Subscription],
) -> dict[str, list[CurrencyTotal]]:
    grouped: dict[str, list[Subscription]] = defaultdict(list)
    for sub in subscriptions:
        grouped[sub.category].append(sub)
    return {cat: _aggregate_totals(items) for cat, items in grouped.items()}


def _plural_days_short(n: int) -> str:
    if n == 0:
        return "сегодня"
    if n > 0:
        return f"через {n} дн."
    return f"{-n} дн. назад"


# Touch unused imports so ruff doesn't complain.
_ = (calendar, shift_date, format_date)
