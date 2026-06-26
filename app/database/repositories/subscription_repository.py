"""Data access layer for :class:`Subscription`."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Subscription, SubscriptionStatus


class SubscriptionRepository:
    """Thin wrapper around SQLAlchemy queries for subscriptions."""

    def __init__(self, session: Session) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    def get(self, subscription_id: int) -> Subscription | None:
        return self.session.get(Subscription, subscription_id)

    def get_or_none(self, subscription_id: int) -> Subscription | None:
        return self.session.get(Subscription, subscription_id)

    def list_for_user(self, user_id: int) -> Sequence[Subscription]:
        stmt = (
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .order_by(Subscription.next_billing_date.asc())
        )
        return self.session.execute(stmt).scalars().all()

    def list_by_status(
        self, user_id: int, status: SubscriptionStatus | str
    ) -> Sequence[Subscription]:
        value = status.value if isinstance(status, SubscriptionStatus) else status
        stmt = (
            select(Subscription)
            .where(Subscription.user_id == user_id, Subscription.status == value)
            .order_by(Subscription.next_billing_date.asc())
        )
        return self.session.execute(stmt).scalars().all()

    def list_active(self, user_id: int) -> Sequence[Subscription]:
        return self.list_by_status(user_id, SubscriptionStatus.ACTIVE)

    def list_upcoming(
        self, user_id: int, *, before: date, statuses: Sequence[str] | None = None
    ) -> Sequence[Subscription]:
        target_statuses = list(statuses) if statuses else [SubscriptionStatus.ACTIVE.value]
        stmt = (
            select(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.status.in_(target_statuses),
                Subscription.next_billing_date <= before,
            )
            .order_by(Subscription.next_billing_date.asc())
        )
        return self.session.execute(stmt).scalars().all()

    def list_by_category(self, user_id: int, category: str) -> Sequence[Subscription]:
        stmt = (
            select(Subscription)
            .where(Subscription.user_id == user_id, Subscription.category == category)
            .order_by(Subscription.name.asc())
        )
        return self.session.execute(stmt).scalars().all()

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------
    def add(self, subscription: Subscription) -> Subscription:
        self.session.add(subscription)
        self.session.flush()
        return subscription

    def delete(self, subscription: Subscription) -> None:
        self.session.delete(subscription)
        self.session.flush()


__all__ = ["SubscriptionRepository"]
