"""Tests for :class:`ReportService`."""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.config.settings import PROJECT_ROOT
from app.services.export_service import ExportService
from app.services.report_service import ReportService
from app.services.subscription_service import SubscriptionInput, SubscriptionService


@pytest.fixture()
def exports_dir(monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as tmp:
        # Make PROJECT_ROOT.point to a temp dir for the lifetime of the test
        # so ExportService() resolves exports_dir under it.
        monkeypatch.setattr("app.services.export_service.PROJECT_ROOT", Path(tmp))
        yield Path(tmp)


def _make(session: Session, admin_id: int, **kwargs: object) -> int:
    sub = SubscriptionService(session).create(
        admin_id,
        SubscriptionInput(
            name=kwargs.get("name", "Sub"),
            category=kwargs.get("category", "ИИ"),
            price=float(kwargs.get("price", 10.0)),
            currency=str(kwargs.get("currency", "USD")),
            billing_period=str(kwargs.get("billing_period", "monthly")),
            next_billing_date=kwargs.get("next_billing_date", date(2026, 7, 1)),
        ),
    )
    return sub.id


class TestSummary:
    def test_empty_summary(self, session: Session, admin_id: int) -> None:
        summary = ReportService(session).summary(admin_id)
        assert summary.active_count == 0
        assert summary.totals_by_currency == []

    def test_monthly_total(self, session: Session, admin_id: int) -> None:
        _make(session, admin_id, name="A", currency="USD", price=10, billing_period="monthly")
        _make(session, admin_id, name="B", currency="USD", price=20, billing_period="monthly")
        summary = ReportService(session).summary(admin_id)
        assert summary.active_count == 2
        assert len(summary.totals_by_currency) == 1
        assert summary.totals_by_currency[0].currency == "USD"
        assert summary.totals_by_currency[0].monthly_equivalent == pytest.approx(30.0)
        assert summary.totals_by_currency[0].yearly_equivalent == pytest.approx(360.0)

    def test_yearly_divided_by_12(self, session: Session, admin_id: int) -> None:
        _make(session, admin_id, name="Domain", currency="RUB", price=1200, billing_period="yearly")
        summary = ReportService(session).summary(admin_id)
        rub = next(t for t in summary.totals_by_currency if t.currency == "RUB")
        assert rub.monthly_equivalent == pytest.approx(100.0)

    def test_category_breakdown(self, session: Session, admin_id: int) -> None:
        _make(session, admin_id, name="A", category="ИИ", price=20)
        _make(session, admin_id, name="B", category="работа", price=10)
        summary = ReportService(session).summary(admin_id)
        assert "ИИ" in summary.by_category
        assert "работа" in summary.by_category

    def test_upcoming(self, session: Session, admin_id: int) -> None:
        today = date(2026, 6, 26)
        _make(session, admin_id, name="Soon", next_billing_date=date(2026, 6, 30))
        _make(session, admin_id, name="Far", next_billing_date=date(2027, 6, 1))
        items = ReportService(session).upcoming(admin_id, days=30, today=today)
        assert [s.name for s in items] == ["Soon"]

    def test_render_contains_amounts(self, session: Session, admin_id: int) -> None:
        _make(session, admin_id, name="ChatGPT", currency="USD", price=20)
        summary = ReportService(session).summary(admin_id)
        text = ReportService.render_summary(summary)
        assert "20.00 USD" in text
        assert "Сводка" in text


class TestExportService:
    def test_csv_subscriptions(self, session: Session, admin_id: int, exports_dir: Path) -> None:
        _make(session, admin_id, name="ChatGPT", currency="USD", price=20)
        result = ExportService(session).export_subscriptions(admin_id, today=date(2026, 6, 26))
        assert result.rows == 1
        content = result.path.read_text(encoding="utf-8")
        assert "ChatGPT" in content
        assert "USD" in content

    def test_csv_payments(self, session: Session, admin_id: int, exports_dir: Path) -> None:
        sub_id = _make(session, admin_id)
        from app.services.payment_service import PaymentService

        PaymentService(session).mark_paid(sub_id, admin_id)
        result = ExportService(session).export_payments(admin_id, today=date(2026, 6, 26))
        assert result.rows == 1
        assert "Sub" in result.path.read_text(encoding="utf-8")

    def test_csv_collision_uses_suffix(
        self, session: Session, admin_id: int, exports_dir: Path
    ) -> None:
        svc = ExportService(session)
        first = svc.export_subscriptions(admin_id, today=date(2026, 6, 26))
        second = svc.export_subscriptions(admin_id, today=date(2026, 6, 26))
        assert first.path != second.path
        assert first.path.name != second.path.name
        assert first.path.exists() and second.path.exists()


# Touch unused import for lint.
_ = PROJECT_ROOT
