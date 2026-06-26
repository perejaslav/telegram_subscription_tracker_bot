"""Data access layer for :class:`ReminderLog`."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import ReminderLog


class ReminderLogRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def exists(self, subscription_id: int, reminder_date: date, days_before: int) -> bool:
        stmt = select(ReminderLog.id).where(
            ReminderLog.subscription_id == subscription_id,
            ReminderLog.reminder_date == reminder_date,
            ReminderLog.days_before == days_before,
        )
        return self.session.execute(stmt).first() is not None

    def add(
        self,
        subscription_id: int,
        reminder_date: date,
        days_before: int,
        status: str = "sent",
    ) -> ReminderLog:
        log = ReminderLog(
            subscription_id=subscription_id,
            reminder_date=reminder_date,
            days_before=days_before,
            status=status,
        )
        self.session.add(log)
        self.session.flush()
        return log


__all__ = ["ReminderLogRepository"]
