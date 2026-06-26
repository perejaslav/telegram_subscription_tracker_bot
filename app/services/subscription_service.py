"""Subscription business logic (create / edit / status / delete)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.database.models import Subscription, SubscriptionStatus
from app.database.repositories.subscription_repository import SubscriptionRepository
from app.utils.dates import parse_user_date
from app.utils.validators import (
    ValidationError,
    validate_billing_period,
    validate_category,
    validate_currency,
    validate_name,
    validate_optional_text,
    validate_optional_url,
    validate_price,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SubscriptionInput:
    """Validated user-supplied data for a subscription."""

    name: str
    category: str
    price: float
    currency: str
    billing_period: str
    next_billing_date: date
    payment_method: str | None = None
    management_url: str | None = None
    note: str | None = None


class SubscriptionNotFoundError(LookupError):
    """Raised when a subscription id does not exist."""


class ArchivedSubscriptionError(RuntimeError):
    """Raised when an operation requires a non-archived subscription."""


class SubscriptionService:
    """Use cases around subscription lifecycle."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = SubscriptionRepository(session)

    # ------------------------------------------------------------------
    # Validation helpers — exposed for the FSM steps in the bot layer.
    # ------------------------------------------------------------------
    @staticmethod
    def validate_field(field: str, value: str) -> Any:
        """Validate a single field and return the normalized value."""
        try:
            if field == "name":
                return validate_name(value)
            if field == "category":
                return validate_category(value)
            if field == "price":
                return validate_price(value)
            if field == "currency":
                return validate_currency(value)
            if field == "billing_period":
                return validate_billing_period(value)
            if field == "next_billing_date":
                parsed = parse_user_date(value)
                return parsed.isoformat()
            if field == "payment_method":
                return validate_optional_text(
                    value, max_length=100, field="Способ оплаты"
                )
            if field == "management_url":
                return validate_optional_url(value)
            if field == "note":
                return validate_optional_text(value, max_length=1000, field="Заметка")
        except ValidationError as exc:
            raise ValidationError(str(exc)) from exc
        raise ValidationError(f"Неизвестное поле: {field}")

    # ------------------------------------------------------------------
    # Use cases
    # ------------------------------------------------------------------
    def create(self, user_id: int, payload: SubscriptionInput) -> Subscription:
        """Create a new active subscription for the given user."""
        subscription = Subscription(
            user_id=user_id,
            name=payload.name,
            category=payload.category,
            price=payload.price,
            currency=payload.currency,
            billing_period=payload.billing_period,
            next_billing_date=payload.next_billing_date,
            payment_method=payload.payment_method,
            management_url=payload.management_url,
            note=payload.note,
            status=SubscriptionStatus.ACTIVE.value,
        )
        self.repo.add(subscription)
        self.session.commit()
        logger.info("Subscription %s created for user %s", subscription.id, user_id)
        return subscription

    def update_field(
        self, subscription_id: int, user_id: int, field: str, raw_value: str
    ) -> Subscription:
        """Update a single field on an existing subscription."""
        subscription = self._get_for_user(subscription_id, user_id)
        normalized = self.validate_field(field, raw_value)
        if field == "next_billing_date":
            subscription.next_billing_date = parse_user_date(normalized)
        else:
            setattr(subscription, field, normalized)
        self.session.commit()
        logger.info("Subscription %s: field %s updated", subscription_id, field)
        return subscription

    def change_status(
        self,
        subscription_id: int,
        user_id: int,
        new_status: SubscriptionStatus,
    ) -> Subscription:
        """Switch the subscription to a new status."""
        subscription = self._get_for_user(subscription_id, user_id)
        subscription.status = new_status.value
        if new_status == SubscriptionStatus.ARCHIVED:
            from datetime import datetime

            subscription.archived_at = datetime.utcnow()
        self.session.commit()
        logger.info("Subscription %s status → %s", subscription_id, new_status.value)
        return subscription

    def delete(self, subscription_id: int, user_id: int) -> None:
        """Hard-delete a subscription."""
        subscription = self._get_for_user(subscription_id, user_id)
        self.repo.delete(subscription)
        self.session.commit()
        logger.info("Subscription %s deleted by user %s", subscription_id, user_id)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _get_for_user(self, subscription_id: int, user_id: int) -> Subscription:
        sub = self.repo.get(subscription_id)
        if sub is None or sub.user_id != user_id:
            raise SubscriptionNotFoundError(f"Подписка #{subscription_id} не найдена.")
        return sub


__all__ = [
    "ArchivedSubscriptionError",
    "SubscriptionInput",
    "SubscriptionNotFoundError",
    "SubscriptionService",
]
