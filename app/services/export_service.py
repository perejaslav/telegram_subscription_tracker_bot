"""CSV export service for subscriptions and payments."""

from __future__ import annotations

import csv
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from app.config.settings import PROJECT_ROOT
from app.database.models import Payment
from app.database.repositories.payment_repository import PaymentRepository
from app.database.repositories.subscription_repository import SubscriptionRepository

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ExportResult:
    path: Path
    rows: int


class ExportService:
    """Generate dated CSV exports under ``exports/``."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.sub_repo = SubscriptionRepository(session)
        self.pay_repo = PaymentRepository(session)
        self.exports_dir: Path = PROJECT_ROOT / "exports"
        self.exports_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    def export_subscriptions(
        self, user_id: int, *, today: date | None = None
    ) -> ExportResult:
        today = today or date.today()
        subs = list(self.sub_repo.list_for_user(user_id))
        path = self._resolve_path("subscriptions", today)
        headers = [
            "id",
            "name",
            "category",
            "price",
            "currency",
            "billing_period",
            "next_billing_date",
            "payment_method",
            "management_url",
            "note",
            "status",
            "created_at",
            "updated_at",
            "archived_at",
        ]
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(headers)
            for s in subs:
                writer.writerow(
                    [
                        s.id,
                        s.name,
                        s.category,
                        f"{s.price:.2f}",
                        s.currency,
                        s.billing_period,
                        s.next_billing_date.isoformat(),
                        s.payment_method or "",
                        s.management_url or "",
                        s.note or "",
                        s.status,
                        s.created_at.isoformat(sep=" ", timespec="seconds")
                        if s.created_at
                        else "",
                        s.updated_at.isoformat(sep=" ", timespec="seconds")
                        if s.updated_at
                        else "",
                        s.archived_at.isoformat(sep=" ", timespec="seconds")
                        if s.archived_at
                        else "",
                    ]
                )
        logger.info("Exported %s subscriptions to %s", len(subs), path)
        return ExportResult(path=path, rows=len(subs))

    def export_payments(
        self, user_id: int, *, today: date | None = None
    ) -> ExportResult:
        today = today or date.today()
        payments = list(self._iter_payments(user_id))
        path = self._resolve_path("payments", today)
        headers = [
            "id",
            "subscription_id",
            "subscription_name",
            "paid_at",
            "amount",
            "currency",
            "note",
            "created_at",
        ]
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(headers)
            for p, sub_name in payments:
                writer.writerow(
                    [
                        p.id,
                        p.subscription_id,
                        sub_name,
                        p.paid_at.isoformat(),
                        f"{p.amount:.2f}",
                        p.currency,
                        p.note or "",
                        p.created_at.isoformat(sep=" ", timespec="seconds")
                        if p.created_at
                        else "",
                    ]
                )
        logger.info("Exported %s payments to %s", len(payments), path)
        return ExportResult(path=path, rows=len(payments))

    # ------------------------------------------------------------------
    def _iter_payments(self, user_id: int) -> Iterable[tuple[Payment, str]]:
        for sub in self.sub_repo.list_for_user(user_id):
            for p in self.pay_repo.list_for_subscription(sub.id, limit=None):
                yield p, sub.name

    def _resolve_path(self, prefix: str, today: date) -> Path:
        base = self.exports_dir / f"{prefix}_{today.isoformat()}.csv"
        if not base.exists():
            return base
        # Collision handling per spec §12: append _HH-MM.
        suffix = today.strftime("%H-%M")
        candidate = self.exports_dir / f"{prefix}_{today.isoformat()}_{suffix}.csv"
        counter = 1
        while candidate.exists():
            candidate = self.exports_dir / (
                f"{prefix}_{today.isoformat()}_{suffix}_{counter}.csv"
            )
            counter += 1
        return candidate


__all__ = ["ExportResult", "ExportService"]
