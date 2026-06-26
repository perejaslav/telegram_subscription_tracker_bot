"""Tests for :class:`ReminderService`."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.services.reminder_service import ReminderService
from app.services.subscription_service import SubscriptionInput, SubscriptionService


def _make(session: Session, admin_id: int, days_offset: int) -> int:
    today = date(2026, 6, 26)
    sub = SubscriptionService(session).create(
        admin_id,
        SubscriptionInput(
            name=f"Sub-{days_offset}",
            category="ИИ",
            price=10.0,
            currency="USD",
            billing_period="monthly",
            next_billing_date=date.fromordinal(today.toordinal() + days_offset),
        ),
    )
    return sub.id


class TestReminderDispatch:
    def test_sends_when_in_window(self, session: Session, fake_bot, admin_id: int) -> None:
        today = date(2026, 6, 26)
        _make(session, admin_id, 1)
        _make(session, admin_id, 3)
        outcome = ReminderService(session, fake_bot).run_daily_check(
            today=today, reminder_days=[1, 3, 7]
        )
        assert outcome.sent == 2
        assert len(fake_bot.sent) == 2

    def test_skips_outside_window(self, session: Session, fake_bot, admin_id: int) -> None:
        today = date(2026, 6, 26)
        _make(session, admin_id, 10)
        outcome = ReminderService(session, fake_bot).run_daily_check(
            today=today, reminder_days=[1, 3, 7]
        )
        assert outcome.sent == 0
        assert outcome.skipped == 1

    def test_overdue_path(self, session: Session, fake_bot, admin_id: int) -> None:
        today = date(2026, 6, 26)
        _make(session, admin_id, -2)
        outcome = ReminderService(session, fake_bot).run_daily_check(
            today=today, reminder_days=[1, 3, 7]
        )
        assert outcome.overdue == 1
        assert any("Просрочено" in text for _chat, text in fake_bot.sent)

    def test_no_duplicates_same_day(self, session: Session, fake_bot, admin_id: int) -> None:
        today = date(2026, 6, 26)
        _make(session, admin_id, 1)
        svc = ReminderService(session, fake_bot)
        first = svc.run_daily_check(today=today, reminder_days=[1, 3, 7])
        second = svc.run_daily_check(today=today, reminder_days=[1, 3, 7])
        assert first.sent == 1
        assert second.sent == 0

    def test_ignores_paused(self, session: Session, fake_bot, admin_id: int) -> None:
        from app.database.models import SubscriptionStatus

        today = date(2026, 6, 26)
        sub_id = _make(session, admin_id, 1)
        SubscriptionService(session).change_status(sub_id, admin_id, SubscriptionStatus.PAUSED)
        outcome = ReminderService(session, fake_bot).run_daily_check(
            today=today, reminder_days=[1, 3, 7]
        )
        assert outcome.sent == 0
