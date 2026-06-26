"""Reminder logic — sends Telegram messages for upcoming / overdue billings."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.database.engine import SessionLocal
from app.database.models import ReminderLog, Subscription, SubscriptionStatus
from app.database.repositories.reminder_log_repository import ReminderLogRepository
from app.database.repositories.subscription_repository import SubscriptionRepository
from app.utils.dates import days_until, format_date
from app.utils.formatters import format_money

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ReminderOutcome:
    """Per-run statistics, useful for tests and logs."""

    sent: int = 0
    skipped: int = 0
    failed: int = 0
    overdue: int = 0


class ReminderService:
    """Check upcoming billings and dispatch Telegram notifications."""

    OVERDUE_DAYS_BEFORE = -1  # sentinel row in ReminderLog for overdue alerts.

    def __init__(self, session: Session, bot: Bot) -> None:
        self.session = session
        self.bot = bot
        self.sub_repo = SubscriptionRepository(session)
        self.log_repo = ReminderLogRepository(session)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run_daily_check(
        self,
        *,
        today: date | None = None,
        reminder_days: Iterable[int] | None = None,
    ) -> ReminderOutcome:
        """Scan active subscriptions and dispatch reminders."""
        outcome = ReminderOutcome()
        today = today or date.today()
        reminder_days_set = set(
            reminder_days if reminder_days is not None else settings.reminder_days
        )

        active_subs = self.sub_repo.list_by_status(
            settings.admin_telegram_id, SubscriptionStatus.ACTIVE
        )
        for sub in active_subs:
            delta = days_until(sub.next_billing_date, today)
            if delta < 0:
                outcome.overdue += self._maybe_send_overdue(sub, today)
                continue
            if delta in reminder_days_set:
                outcome.sent += self._maybe_send(sub, today, days_before=delta)
            else:
                outcome.skipped += 1
        self.session.commit()
        logger.info(
            "Daily reminder check: sent=%s skipped=%s overdue=%s failed=%s",
            outcome.sent,
            outcome.skipped,
            outcome.overdue,
            outcome.failed,
        )
        return outcome

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _maybe_send(self, sub: Subscription, today: date, *, days_before: int) -> int:
        if self.log_repo.exists(sub.id, today, days_before):
            return 0
        text = (
            f"⏰ Через <b>{_plural_days(days_before)}</b> будет списание:\n\n"
            f"📦 <b>{sub.name}</b>\n"
            f"{format_money(sub.price, sub.currency)}\n"
            f"Дата: {format_date(sub.next_billing_date)}"
        )
        return int(self._dispatch(sub, today, days_before, text))

    def _maybe_send_overdue(self, sub: Subscription, today: date) -> int:
        if self.log_repo.exists(sub.id, today, self.OVERDUE_DAYS_BEFORE):
            return 0
        delta = days_until(sub.next_billing_date, today)
        text = (
            f"⚠ <b>Просрочено</b> на {-delta} дн.:\n\n"
            f"📦 <b>{sub.name}</b>\n"
            f"{format_money(sub.price, sub.currency)}\n"
            f"Дата: {format_date(sub.next_billing_date)}"
        )
        return int(self._dispatch(sub, today, self.OVERDUE_DAYS_BEFORE, text))

    def _dispatch(
        self,
        sub: Subscription,
        today: date,
        days_before: int,
        text: str,
    ) -> bool:
        try:
            self.bot.send_message(settings.admin_telegram_id, text)
        except TelegramAPIError as exc:
            logger.warning("Reminder send failed for sub %s: %s", sub.id, exc)
            self.log_repo.add(sub.id, today, days_before, status="failed")
            return False
        self.log_repo.add(sub.id, today, days_before, status="sent")
        logger.info(
            "Reminder sent: sub=%s days_before=%s admin=%s",
            sub.id,
            days_before,
            settings.admin_telegram_id,
        )
        return True


def _plural_days(n: int) -> str:
    """Russian pluralisation: 1 день, 2 дня, 5 дней."""
    n = abs(n)
    if 11 <= n % 100 <= 14:
        return f"{n} дней"
    last = n % 10
    if last == 1:
        return f"{n} день"
    if 2 <= last <= 4:
        return f"{n} дня"
    return f"{n} дней"


def run_reminder_check(bot: Bot, *, today: date | None = None) -> ReminderOutcome:
    """Helper for the scheduler job — opens its own DB session."""
    with SessionLocal() as session:
        return ReminderService(session, bot).run_daily_check(today=today)


__all__ = ["ReminderOutcome", "ReminderService", "run_reminder_check"]


# Touch imports for typing/linters.
_ = (ReminderLog, timedelta)
