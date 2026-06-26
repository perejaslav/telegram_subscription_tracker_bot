"""Tests for :class:`SubscriptionService`."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.database.models import SubscriptionStatus
from app.services.subscription_service import (
    SubscriptionInput,
    SubscriptionNotFoundError,
    SubscriptionService,
)
from app.utils.validators import ValidationError


def _payload(**overrides: object) -> SubscriptionInput:
    defaults: dict[str, object] = {
        "name": "ChatGPT",
        "category": "ИИ",
        "price": 20.0,
        "currency": "USD",
        "billing_period": "monthly",
        "next_billing_date": date(2026, 7, 1),
        "payment_method": None,
        "management_url": None,
        "note": None,
    }
    defaults.update(overrides)
    return SubscriptionInput(**defaults)  # type: ignore[arg-type]


class TestCreate:
    def test_ok(self, session: Session, admin_id: int) -> None:
        sub = SubscriptionService(session).create(admin_id, _payload())
        assert sub.id is not None
        assert sub.status == SubscriptionStatus.ACTIVE.value
        assert sub.user_id == admin_id


class TestValidateField:
    @pytest.mark.parametrize(
        ("field", "value", "expected_error"),
        [
            ("name", "", "пустым"),
            ("price", "abc", "числом"),
            ("price", "-1", "больше нуля"),
            ("currency", "руб", "латинских"),
            ("billing_period", "daily", "Период"),
            ("next_billing_date", "2026-07-01", "ДД.ММ.ГГГГ"),
            ("management_url", "ftp://x", "http"),
        ],
    )
    def test_invalid(self, field: str, value: str, expected_error: str) -> None:
        with pytest.raises(ValidationError, match=expected_error):
            SubscriptionService.validate_field(field, value)


class TestUpdateField:
    def test_ok(self, session: Session, admin_id: int) -> None:
        svc = SubscriptionService(session)
        sub = svc.create(admin_id, _payload())
        updated = svc.update_field(sub.id, admin_id, "price", "25.00")
        assert updated.price == 25.0

    def test_invalid(self, session: Session, admin_id: int) -> None:
        svc = SubscriptionService(session)
        sub = svc.create(admin_id, _payload())
        with pytest.raises(ValidationError):
            svc.update_field(sub.id, admin_id, "price", "abc")

    def test_wrong_owner(self, session: Session, admin_id: int) -> None:
        svc = SubscriptionService(session)
        sub = svc.create(admin_id, _payload())
        with pytest.raises(SubscriptionNotFoundError):
            svc.update_field(sub.id, admin_id + 1, "price", "1.00")


class TestChangeStatus:
    def test_archive_sets_timestamp(self, session: Session, admin_id: int) -> None:
        svc = SubscriptionService(session)
        sub = svc.create(admin_id, _payload())
        assert sub.archived_at is None
        sub = svc.change_status(sub.id, admin_id, SubscriptionStatus.ARCHIVED)
        assert sub.status == SubscriptionStatus.ARCHIVED.value
        assert sub.archived_at is not None


class TestDelete:
    def test_ok(self, session: Session, admin_id: int) -> None:
        svc = SubscriptionService(session)
        sub = svc.create(admin_id, _payload())
        svc.delete(sub.id, admin_id)
        assert svc.repo.get(sub.id) is None
