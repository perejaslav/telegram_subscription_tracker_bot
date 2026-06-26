"""SQLAlchemy ORM models (spec §13)."""

from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.engine import Base


class SubscriptionStatus(str, enum.Enum):
    """Lifecycle of a subscription (spec §8.1)."""

    ACTIVE = "active"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    ARCHIVED = "archived"


class BillingPeriod(str, enum.Enum):
    """How often a subscription is billed (spec §11)."""

    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"
    MANUAL = "manual"


class Subscription(Base):
    """A tracked subscription (spec §13, table ``subscriptions``)."""

    __tablename__ = "subscriptions"
    __table_args__ = (
        Index("ix_subscriptions_user_status", "user_id", "status"),
        Index("ix_subscriptions_next_billing", "next_billing_date"),
        Index("ix_subscriptions_category", "category"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)
    billing_period: Mapped[str] = mapped_column(String(20), nullable=False)
    next_billing_date: Mapped[date] = mapped_column(Date, nullable=False)
    payment_method: Mapped[str | None] = mapped_column(String(100), nullable=True)
    management_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=SubscriptionStatus.ACTIVE.value
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    payments: Mapped[list["Payment"]] = relationship(
        back_populates="subscription",
        cascade="all, delete-orphan",
        order_by="Payment.paid_at.desc()",
    )
    reminder_logs: Mapped[list["ReminderLog"]] = relationship(
        back_populates="subscription",
        cascade="all, delete-orphan",
    )


class Payment(Base):
    """A recorded payment against a subscription (spec §13)."""

    __tablename__ = "payments"
    __table_args__ = (Index("ix_payments_subscription", "subscription_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False
    )
    paid_at: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )

    subscription: Mapped[Subscription] = relationship(back_populates="payments")


class ReminderLog(Base):
    """Audit trail of sent reminders (used in stage 4)."""

    __tablename__ = "reminder_logs"
    __table_args__ = (
        Index(
            "uq_reminder_subscription_date_days",
            "subscription_id",
            "reminder_date",
            "days_before",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False
    )
    reminder_date: Mapped[date] = mapped_column(Date, nullable=False)
    days_before: Mapped[int] = mapped_column(Integer, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="sent")

    subscription: Mapped[Subscription] = relationship(back_populates="reminder_logs")


class UserSettings(Base):
    """Per-user overrides (spec §13, table ``settings``)."""

    __tablename__ = "settings"
    __table_args__ = (Index("ix_settings_user", "user_id", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="UTC")
    reminder_days: Mapped[str] = mapped_column(
        String(100), nullable=False, default="1,3,7"
    )
    reminder_check_time: Mapped[str] = mapped_column(
        String(5), nullable=False, default="09:00"
    )
    default_currency: Mapped[str] = mapped_column(
        String(10), nullable=False, default="RUB"
    )
    show_archived: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )


__all__ = [
    "BillingPeriod",
    "Payment",
    "ReminderLog",
    "Subscription",
    "SubscriptionStatus",
    "UserSettings",
]
