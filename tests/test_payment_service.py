"""Tests for :class:`PaymentService`."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.database.models import BillingPeriod, SubscriptionStatus
from app.services.payment_service import (
    ArchivedSubscriptionError,
    PaymentAmountError,
    PaymentService,
)
from app.services.subscription_service import SubscriptionInput, SubscriptionService


def _make_sub(session: Session, admin_id: int, **kwargs: object) -> int:
    payload = SubscriptionInput(
        name=kwargs.get("name", "Sub"),
        category=kwargs.get("category", "ИИ"),
        price=float(kwargs.get("price", 10.0)),
        currency=str(kwargs.get("currency", "USD")),
        billing_period=str(kwargs.get("billing_period", "monthly")),
        next_billing_date=kwargs.get("next_billing_date", date(2026, 7, 1)),
    )
    sub = SubscriptionService(session).create(admin_id, payload)
    return sub.id


class TestMarkPaid:
    def test_monthly_shift(self, session: Session, admin_id: int) -> None:
        sub_id = _make_sub(
            session, admin_id, billing_period="monthly", next_billing_date=date(2026, 1, 31)
        )
        sub, payment = PaymentService(session).mark_paid(sub_id, admin_id)
        assert payment.amount == 10.0
        assert sub.next_billing_date == date(2026, 2, 28)  # non-leap year

    def test_yearly_shift(self, session: Session, admin_id: int) -> None:
        sub_id = _make_sub(
            session, admin_id, billing_period="yearly", next_billing_date=date(2025, 2, 28)
        )
        sub, _ = PaymentService(session).mark_paid(sub_id, admin_id)
        assert sub.next_billing_date == date(2026, 2, 28)

    def test_manual_no_auto_shift(self, session: Session, admin_id: int) -> None:
        sub_id = _make_sub(
            session, admin_id, billing_period="manual", next_billing_date=date(2026, 7, 1)
        )
        sub, _ = PaymentService(session).mark_paid(sub_id, admin_id)
        assert sub.next_billing_date == date(2026, 7, 1)

    def test_custom_amount(self, session: Session, admin_id: int) -> None:
        sub_id = _make_sub(session, admin_id, price=10.0)
        _, payment = PaymentService(session).mark_paid(sub_id, admin_id, amount="12,50")
        assert payment.amount == 12.5

    def test_archived_blocked(self, session: Session, admin_id: int) -> None:
        sub_id = _make_sub(session, admin_id)
        SubscriptionService(session).change_status(sub_id, admin_id, SubscriptionStatus.ARCHIVED)
        with pytest.raises(ArchivedSubscriptionError):
            PaymentService(session).mark_paid(sub_id, admin_id)

    def test_negative_amount(self, session: Session, admin_id: int) -> None:
        sub_id = _make_sub(session, admin_id)
        with pytest.raises(PaymentAmountError):
            PaymentService(session).mark_paid(sub_id, admin_id, amount="-5")

    def test_history(self, session: Session, admin_id: int) -> None:
        sub_id = _make_sub(session, admin_id)
        for _ in range(3):
            PaymentService(session).mark_paid(sub_id, admin_id)
        history = PaymentService(session).history(sub_id, admin_id, limit=10)
        assert len(history) == 3


class TestSetNextBillingDate:
    def test_manual(self, session: Session, admin_id: int) -> None:
        sub_id = _make_sub(
            session, admin_id, billing_period="manual", next_billing_date=date(2026, 7, 1)
        )
        sub = PaymentService(session).set_next_billing_date(sub_id, admin_id, date(2026, 8, 15))
        assert sub.next_billing_date == date(2026, 8, 15)


# Touch imports for typing/linters.
_ = BillingPeriod
