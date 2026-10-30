"""Stage-6 preferences, search and actual-expense accounting regressions."""

from contextlib import nullcontext
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.orm import Session

from app.services.payment_service import PaymentService
from app.services.reminder_service import ReminderService
from app.services.report_service import ReportService
from app.services.subscription_service import SubscriptionInput, SubscriptionService
from app.services.user_preferences import (
    get_preferences,
    parse_reminder_days,
    update_preferences,
    validate_timezone,
)


@pytest.mark.asyncio
async def test_fast_add_handler_creates_a_valid_subscription(
    session: Session, admin_id: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.bot.handlers import subscriptions as handlers

    monkeypatch.setattr(handlers, "SessionLocal", lambda: nullcontext(session))
    state = SimpleNamespace(clear=AsyncMock(), set_state=AsyncMock())
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=admin_id),
        text="ChatGPT; 19.99; USD; 15.11.2026; monthly",
        answer=AsyncMock(),
    )
    await handlers.quick_add_save(message, state)
    assert [s.name for s in SubscriptionService(session).search(admin_id, "ChatGPT")] == ["ChatGPT"]
    state.clear.assert_awaited_once()
    message.answer.assert_awaited_once()


def create_sub(session: Session, user_id: int, name: str) -> int:
    return (
        SubscriptionService(session)
        .create(
            user_id,
            SubscriptionInput(
                name=name,
                category="ИИ",
                price=Decimal("19.99"),
                currency="USD",
                billing_period="monthly",
                next_billing_date=date(2026, 11, 15),
            ),
        )
        .id
    )


def test_preferences_persist_and_are_user_scoped(session: Session, admin_id: int) -> None:
    before = get_preferences(session, admin_id)
    assert before.days
    changed = update_preferences(session, admin_id, timezone="Europe/Istanbul", days="7,1,3,3")
    assert changed.days == (1, 3, 7)
    assert changed.timezone == "Europe/Istanbul"
    assert get_preferences(session, admin_id).days == (1, 3, 7)
    assert get_preferences(session, admin_id + 1).timezone != "Europe/Istanbul"


@pytest.mark.parametrize("bad", ["", "-1", "366", "nope", "1,", "1,2,not-a-day"])
def test_invalid_reminder_days(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_reminder_days(bad)


def test_invalid_timezone_is_rejected_without_data_change(session: Session, admin_id: int) -> None:
    before = get_preferences(session, admin_id)
    with pytest.raises(ValueError):
        update_preferences(session, admin_id, timezone="Invalid/Zone")
    assert get_preferences(session, admin_id) == before
    with pytest.raises(ValueError):
        validate_timezone("no-such-timezone")


def test_search_is_case_insensitive_literal_and_owner_scoped(
    session: Session, admin_id: int
) -> None:
    create_sub(session, admin_id, "ChatGPT Plus")
    create_sub(session, admin_id, "Test_100%")
    create_sub(session, admin_id, "Яндекс Плюс")
    create_sub(session, admin_id + 1, "ChatGPT Private")
    service = SubscriptionService(session)
    assert [sub.name for sub in service.search(admin_id, "CHATgpt")] == ["ChatGPT Plus"]
    assert [sub.name for sub in service.search(admin_id, "100%")] == ["Test_100%"]
    assert service.search(admin_id, "private") == []
    assert [sub.name for sub in service.search(admin_id, "ЯНДЕКС")] == ["Яндекс Плюс"]
    with pytest.raises(ValueError):
        service.search(admin_id, "x")


def test_actual_expenses_use_paid_records_and_exact_minor_units(
    session: Session, admin_id: int
) -> None:
    subscription = create_sub(session, admin_id, "Service")
    another = create_sub(session, admin_id + 1, "Other user")
    payments = PaymentService(session)
    _, payment = payments.mark_paid(
        subscription, admin_id, amount="19.99", paid_at=date(2026, 10, 15)
    )
    payments.mark_paid(another, admin_id + 1, amount="100.00", paid_at=date(2026, 10, 15))
    payments.correct_payment(payment.id, admin_id, amount="20.01")
    totals = ReportService(session).actual_expenses(
        admin_id, start=date(2026, 10, 1), end=date(2026, 10, 31)
    )
    assert totals == {"USD": Decimal("20.01")}
    assert (
        ReportService(session).actual_expenses(
            admin_id, start=date(2026, 11, 1), end=date(2026, 11, 30)
        )
        == {}
    )


@pytest.mark.asyncio
async def test_changed_reminder_days_drive_delivery_and_preserve_deduplication(
    session: Session, admin_id: int, fake_bot
) -> None:
    today = date(2026, 6, 26)
    sub_id = create_sub(session, admin_id, "Reminder preference")
    sub = SubscriptionService(session).repo.get(sub_id)
    sub.next_billing_date = date(2026, 7, 1)
    session.commit()

    update_preferences(session, admin_id, days="5", timezone="Europe/Istanbul")
    first = await ReminderService(session, fake_bot).run_daily_check(today=today)
    second = await ReminderService(session, fake_bot).run_daily_check(today=today)
    assert first.sent == 1 and second.sent == 0
    assert len(fake_bot.sent) == 1

    update_preferences(session, admin_id, days="1")
    another = create_sub(session, admin_id, "Different reminder")
    SubscriptionService(session).repo.get(another).next_billing_date = date(2026, 7, 1)
    session.commit()
    third = await ReminderService(session, fake_bot).run_daily_check(today=today)
    assert third.sent == 0
