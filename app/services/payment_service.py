"""Payment business logic (mark paid, shift next billing date, history)."""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app.database.models import BillingPeriod, Payment, Subscription, SubscriptionStatus
from app.database.repositories.payment_repository import PaymentRepository
from app.database.repositories.subscription_repository import SubscriptionRepository
from app.utils.dates import shift_date
from app.utils.validators import validate_optional_text

logger = logging.getLogger(__name__)


class PaymentAmountError(ValueError):
    """Raised when the user-supplied amount cannot be parsed."""


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
            raise ArchivedSubscriptionError(
                "Нельзя отметить архивную подписку как оплаченную."
            )

        effective_amount = (
            float(amount) if isinstance(amount, (int, float)) else _parse_amount(amount)
        )
        effective_currency = (currency or subscription.currency).strip().upper()
        effective_note = validate_optional_text(
            note or "", max_length=500, field="Комментарий"
        )
        effective_date = paid_at or date.today()

        payment = Payment(
            subscription_id=subscription.id,
            paid_at=effective_date,
            amount=effective_amount,
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
        self.session.commit()
        logger.info(
            "Payment recorded for subscription %s: %s %s",
            subscription.id,
            payment.amount,
            payment.currency,
        )
        return subscription, payment

    def set_next_billing_date(
        self, subscription_id: int, user_id: int, new_date: date
    ) -> Subscription:
        """Used after a ``manual``-period payment to ask the user for the new date."""
        subscription = self.sub_repo.get(subscription_id)
        if subscription is None or subscription.user_id != user_id:
            raise SubscriptionNotFoundError(f"Подписка #{subscription_id} не найдена.")
        subscription.next_billing_date = new_date
        self.session.commit()
        logger.info(
            "Manual next_billing_date for sub %s set to %s", subscription.id, new_date
        )
        return subscription

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------
    def history(
        self, subscription_id: int, user_id: int, *, limit: int = 20
    ) -> list[Payment]:
        subscription = self.sub_repo.get(subscription_id)
        if subscription is None or subscription.user_id != user_id:
            raise SubscriptionNotFoundError(f"Подписка #{subscription_id} не найдена.")
        return list(self.repo.list_for_subscription(subscription.id, limit=limit))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_amount(value: str | None) -> float:
    if value is None or not str(value).strip():
        return 0.0
    cleaned = str(value).strip().replace(",", ".")
    try:
        amount = Decimal(cleaned)
    except InvalidOperation as exc:
        raise PaymentAmountError("Введите сумму числом, например: 19.99") from exc
    if amount < 0:
        raise PaymentAmountError("Сумма не может быть отрицательной.")
    return float(amount)


__all__ = [
    "ArchivedSubscriptionError",
    "PaymentAmountError",
    "PaymentService",
    "SubscriptionNotFoundError",
]


# Avoid an import cycle at module top — these come from the subscription service.
from app.services.subscription_service import (  # noqa: E402
    ArchivedSubscriptionError,
    SubscriptionNotFoundError,
)
