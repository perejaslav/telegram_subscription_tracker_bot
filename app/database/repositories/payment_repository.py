"""Data access layer for :class:`Payment`."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Payment


class PaymentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, payment: Payment) -> Payment:
        self.session.add(payment)
        self.session.flush()
        return payment

    def list_for_subscription(
        self, subscription_id: int, *, limit: int | None = None
    ) -> Sequence[Payment]:
        stmt = (
            select(Payment)
            .where(Payment.subscription_id == subscription_id)
            .order_by(Payment.paid_at.desc(), Payment.id.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        return self.session.execute(stmt).scalars().all()


__all__ = ["PaymentRepository"]
