"""Payment business logic (mark paid, shift next billing date, history)."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.database.models import (
    BillingPeriod,
    Payment,
    PaymentCorrection,
    Subscription,
    SubscriptionStatus,
)
from app.database.repositories.payment_repository import PaymentRepository
from app.database.repositories.subscription_repository import SubscriptionRepository
from app.utils.dates import shift_date
from app.utils.validators import validate_currency, validate_optional_text

logger = logging.getLogger(__name__)


class PaymentAmountError(ValueError):
    """Raised when the user-supplied amount cannot be parsed."""


class DuplicatePaymentError(ValueError):
    """The selected billing cycle has already been recorded."""


class PaymentService:
    """Use cases around marking a subscription paid and browsing history."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = PaymentRepository(session)
        self.sub_repo = SubscriptionRepository(session)

    # ------------------------------------------------------------------
    # Mark paid
    # ------------------------------------------------------------------
    def mark_paid(
        self,
        subscription_id: int,
        user_id: int,
        *,
        amount: str | float | None = None,
        currency: str | None = None,
        note: str | None = None,
        paid_at: date | None = None,
        billing_due_date: date | None = None,
    ) -> tuple[Subscription, Payment]:
        """Record a payment and advance the subscription's ``next_billing_date``.

        Returns the updated subscription and the created payment record.
        Raises :class:`SubscriptionNotFoundError` if the subscription does not
        belong to the user and :class:`ArchivedSubscriptionError` if the
        subscription is archived.
        """
        subscription = self.sub_repo.get(subscription_id)
        if subscription is None or subscription.user_id != user_id:
            raise SubscriptionNotFoundError(f"Подписка #{subscription_id} не найдена.")
        if subscription.status == SubscriptionStatus.ARCHIVED.value:
            raise ArchivedSubscriptionError("Нельзя отметить архивную подписку как оплаченную.")

        if amount is None or amount == "":
            exact_amount = _parse_decimal_amount(
                str(Decimal(subscription.price_minor) / 100)
                if subscription.price_minor is not None
                else str(subscription.price)
            )
        else:
            exact_amount = _parse_decimal_amount(str(amount))
        effective_amount = float(exact_amount)
        effective_currency = validate_currency(currency or subscription.currency)
        effective_note = validate_optional_text(note or "", max_length=500, field="Комментарий")
        effective_date = paid_at or datetime.now(ZoneInfo(settings.timezone)).date()
        due_date = billing_due_date or subscription.next_billing_date
        if due_date != subscription.next_billing_date:
            raise DuplicatePaymentError("Дата оплачиваемого периода уже изменилась.")
        if (
            self.session.scalar(
                select(Payment.id).where(
                    Payment.subscription_id == subscription.id,
                    Payment.billing_due_date == due_date,
                )
            )
            is not None
        ):
            raise DuplicatePaymentError("Этот период подписки уже оплачен.")

        payment = Payment(
            subscription_id=subscription.id,
            paid_at=effective_date,
            amount=effective_amount,
            amount_minor=int(exact_amount * 100),
            billing_due_date=due_date,
            currency=effective_currency,
            note=effective_note,
        )
        self.repo.add(payment)

        # Advance next_billing_date for periodic subscriptions.
        if subscription.billing_period == BillingPeriod.MANUAL.value:
            # Do not auto-shift; user will be prompted.
            pass
        else:
            try:
                subscription.next_billing_date = shift_date(
                    subscription.next_billing_date, subscription.billing_period
                )
            except ValueError as exc:
                logger.warning(
                    "Could not auto-shift next_billing_date for sub %s: %s",
                    subscription.id,
                    exc,
                )

        # If subscription was paused, leave it paused; otherwise it stays active.
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise DuplicatePaymentError("Этот период подписки уже оплачен.") from exc
        logger.info(
            "Payment recorded for subscription %s: %s %s",
            subscription.id,
            payment.amount,
            payment.currency,
        )
        return subscription, payment

    def correct_payment(
        self, payment_id: int, user_id: int, *, amount: str, note: str | None = None
    ) -> Payment:
        """Adjust an existing payment without advancing the billing date again."""
        payment = self.session.get(Payment, payment_id)
        if payment is None:
            raise SubscriptionNotFoundError("Платёж не найден.")
        subscription = self.sub_repo.get(payment.subscription_id)
        if subscription is None or subscription.user_id != user_id:
            raise SubscriptionNotFoundError("Платёж не найден.")
        exact_amount = _parse_decimal_amount(amount)
        value = float(exact_amount)
        new_note = (
            payment.note
            if note is None
            else validate_optional_text(note, max_length=500, field="Комментарий")
        )
        old_minor = payment.amount_minor
        if old_minor is None:
            old_minor = int(Decimal(str(payment.amount)) * 100)
        self.session.add(
            PaymentCorrection(
                payment_id=payment.id,
                previous_amount_minor=old_minor,
                new_amount_minor=int(exact_amount * 100),
                previous_note=payment.note,
                new_note=new_note,
            )
        )
        payment.amount = value
        payment.amount_minor = int(exact_amount * 100)
        payment.note = new_note
        payment.corrected_at = datetime.now(UTC).replace(tzinfo=None)
        self.session.commit()
        return payment

    def correction_history(self, payment_id: int, user_id: int) -> list[PaymentCorrection]:
        payment = self.session.get(Payment, payment_id)
        subscription = self.sub_repo.get(payment.subscription_id) if payment else None
        if subscription is None or subscription.user_id != user_id:
            raise SubscriptionNotFoundError("Платёж не найден.")
        return list(
            self.session.scalars(
                select(PaymentCorrection)
                .where(PaymentCorrection.payment_id == payment_id)
                .order_by(PaymentCorrection.id)
            )
        )

    def set_next_billing_date(
        self, subscription_id: int, user_id: int, new_date: date
    ) -> Subscription:
        """Used after a ``manual``-period payment to ask the user for the new date."""
        subscription = self.sub_repo.get(subscription_id)
        if subscription is None or subscription.user_id != user_id:
            raise SubscriptionNotFoundError(f"Подписка #{subscription_id} не найдена.")
        subscription.next_billing_date = new_date
        self.session.commit()
        logger.info("Manual next_billing_date for sub %s set to %s", subscription.id, new_date)
        return subscription

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------
    def history(self, subscription_id: int, user_id: int, *, limit: int = 20) -> list[Payment]:
        subscription = self.sub_repo.get(subscription_id)
        if subscription is None or subscription.user_id != user_id:
            raise SubscriptionNotFoundError(f"Подписка #{subscription_id} не найдена.")
        return list(self.repo.list_for_subscription(subscription.id, limit=limit))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_amount(value: str | None) -> float:
    return float(_parse_decimal_amount(value))


def _parse_decimal_amount(value: str | None) -> Decimal:
    if value is None or not str(value).strip():
        return Decimal("0")
    cleaned = str(value).strip().replace(",", ".")
    try:
        amount = Decimal(cleaned)
    except InvalidOperation as exc:
        raise PaymentAmountError("Введите сумму числом, например: 19.99") from exc
    if not amount.is_finite():
        raise PaymentAmountError("Сумма должна быть конечным числом.")
    if amount < 0:
        raise PaymentAmountError("Сумма не может быть отрицательной.")
    if amount > Decimal("999999999999.99"):
        raise PaymentAmountError("Сумма превышает допустимый предел.")
    if amount.as_tuple().exponent < -2:
        raise PaymentAmountError("Допускается не более двух знаков после запятой.")
    return amount


__all__ = [
    "ArchivedSubscriptionError",
    "PaymentAmountError",
    "DuplicatePaymentError",
    "PaymentService",
    "SubscriptionNotFoundError",
]


# Avoid an import cycle at module top — these come from the subscription service.
from app.services.subscription_service import (  # noqa: E402
    ArchivedSubscriptionError,
    SubscriptionNotFoundError,
)
