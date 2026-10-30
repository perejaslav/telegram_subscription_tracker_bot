"""Tests for :class:`PaymentService`."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.database.models import BillingPeriod, SubscriptionStatus
from app.services.payment_service import (
    ArchivedSubscriptionError,
    DuplicatePaymentError,
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
    def test_same_cycle_cannot_be_paid_twice(self, session: Session, admin_id: int) -> None:
        sub_id = _make_sub(session, admin_id, next_billing_date=date(2026, 1, 31))
        service = PaymentService(session)
        sub, payment = service.mark_paid(sub_id, admin_id, billing_due_date=date(2026, 1, 31))
        assert payment.amount_minor == 1000
        assert sub.next_billing_date == date(2026, 2, 28)
        with pytest.raises(DuplicatePaymentError):
            service.mark_paid(sub_id, admin_id, billing_due_date=date(2026, 1, 31))
        assert len(service.history(sub_id, admin_id)) == 1
        assert sub.next_billing_date == date(2026, 2, 28)

    def test_overdue_payment_advances_only_one_unpaid_cycle(
        self, session: Session, admin_id: int
    ) -> None:
        sub_id = _make_sub(session, admin_id, next_billing_date=date(2026, 1, 31))
        service = PaymentService(session)
        sub, first = service.mark_paid(sub_id, admin_id, paid_at=date(2026, 5, 10))
        assert first.billing_due_date == date(2026, 1, 31)
        assert sub.next_billing_date == date(2026, 2, 28)
        _, second = service.mark_paid(sub_id, admin_id, paid_at=date(2026, 5, 10))
        assert second.billing_due_date == date(2026, 2, 28)
        assert len(service.history(sub_id, admin_id)) == 2

    def test_correction_has_audit_and_does_not_shift_billing_date(
        self, session: Session, admin_id: int
    ) -> None:
        sub_id = _make_sub(session, admin_id)
        service = PaymentService(session)
        sub, payment = service.mark_paid(sub_id, admin_id, amount="19.99", note="old")
        new_due = sub.next_billing_date
        corrected = service.correct_payment(payment.id, admin_id, amount="21.45", note="fixed")
        assert corrected.amount_minor == 2145
        assert sub.next_billing_date == new_due
        corrections = service.correction_history(payment.id, admin_id)
        assert len(corrections) == 1
        assert (corrections[0].previous_amount_minor, corrections[0].new_amount_minor) == (
            1999,
            2145,
        )

    def test_cannot_correct_another_users_payment(self, session: Session, admin_id: int) -> None:
        sub_id = _make_sub(session, admin_id)
        service = PaymentService(session)
        _, payment = service.mark_paid(sub_id, admin_id)
        with pytest.raises(Exception, match="Платёж не найден"):
            service.correct_payment(payment.id, admin_id + 1, amount="50")

    def test_exact_minor_units_for_large_amount(self, session: Session, admin_id: int) -> None:
        sub_id = _make_sub(session, admin_id)
        _, payment = PaymentService(session).mark_paid(sub_id, admin_id, amount="999999999999.99")
        assert payment.amount_minor == 99999999999999

    def test_subscription_price_minor_is_source_of_default_payment(
        self, session: Session, admin_id: int
    ) -> None:
        sub = SubscriptionService(session).create(
            admin_id,
            SubscriptionInput(
                name="Precise",
                category="ИИ",
                price=Decimal("999999999999.99"),
                currency="USD",
                billing_period="monthly",
                next_billing_date=date(2026, 7, 1),
            ),
        )
        assert sub.price_minor == 99999999999999
        _, payment = PaymentService(session).mark_paid(sub.id, admin_id)
        assert payment.amount_minor == 99999999999999

    def test_manual_period_is_idempotent(self, session: Session, admin_id: int) -> None:
        sub_id = _make_sub(session, admin_id, billing_period="manual")
        service = PaymentService(session)
        service.mark_paid(sub_id, admin_id)
        with pytest.raises(DuplicatePaymentError):
            service.mark_paid(sub_id, admin_id)
        assert len(service.history(sub_id, admin_id)) == 1

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

    @pytest.mark.parametrize("amount", ["NaN", "Infinity", "-Infinity", "1e9999", "1.001"])
    def test_invalid_money_is_rejected_without_payment_or_date_shift(
        self, session: Session, admin_id: int, amount: str
    ) -> None:
        sub_id = _make_sub(session, admin_id)
        service = PaymentService(session)
        with pytest.raises(PaymentAmountError):
            service.mark_paid(sub_id, admin_id, amount=amount)
        assert service.history(sub_id, admin_id) == []
        assert service.sub_repo.get(sub_id).next_billing_date == date(2026, 7, 1)

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
