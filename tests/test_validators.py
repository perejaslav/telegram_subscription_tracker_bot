"""Tests for input validators (spec §11, §12)."""

from __future__ import annotations

import pytest

from app.utils.dates import days_until, parse_user_date, shift_date
from app.utils.validators import (
    ValidationError,
    validate_billing_date,
    validate_billing_period,
    validate_category,
    validate_currency,
    validate_name,
    validate_optional_text,
    validate_optional_url,
    validate_price,
)


class TestValidateName:
    def test_ok(self) -> None:
        assert validate_name("  ChatGPT Plus  ") == "ChatGPT Plus"

    def test_empty(self) -> None:
        with pytest.raises(ValidationError, match="пустым"):
            validate_name("   ")

    def test_too_long(self) -> None:
        with pytest.raises(ValidationError, match="100 символов"):
            validate_name("x" * 101)


class TestValidatePrice:
    def test_ok_dot(self) -> None:
        assert validate_price("9.99") == 9.99

    def test_ok_comma(self) -> None:
        assert validate_price("10,50") == 10.5

    def test_negative(self) -> None:
        with pytest.raises(ValidationError, match="больше нуля"):
            validate_price("-1")

    def test_garbage(self) -> None:
        with pytest.raises(ValidationError, match="числом"):
            validate_price("abc")


class TestValidateCurrency:
    def test_ok(self) -> None:
        assert validate_currency("usd") == "USD"

    def test_too_long(self) -> None:
        with pytest.raises(ValidationError):
            validate_currency("A" * 11)

    def test_invalid_chars(self) -> None:
        with pytest.raises(ValidationError):
            validate_currency("руб")


class TestValidateBillingPeriod:
    def test_ok(self) -> None:
        assert validate_billing_period("Monthly") == "monthly"

    def test_unsupported(self) -> None:
        with pytest.raises(ValidationError):
            validate_billing_period("daily")


class TestValidateBillingDate:
    def test_ok(self) -> None:
        assert validate_billing_date("15.07.2026") == "15.07.2026"

    def test_bad_format(self) -> None:
        with pytest.raises(ValidationError, match="ДД.ММ.ГГГГ"):
            validate_billing_date("2026-07-15")

    def test_impossible_date(self) -> None:
        with pytest.raises(ValidationError):
            validate_billing_date("31.02.2026")


class TestOptionalFields:
    def test_url(self) -> None:
        assert validate_optional_url("https://example.com/x") == "https://example.com/x"
        assert validate_optional_url("-") is None
        with pytest.raises(ValidationError):
            validate_optional_url("ftp://example.com")

    def test_text(self) -> None:
        assert validate_optional_text("hello", max_length=10, field="X") == "hello"
        assert validate_optional_text("  ", max_length=10, field="X") is None
        with pytest.raises(ValidationError):
            validate_optional_text("x" * 11, max_length=10, field="X")


class TestValidateCategory:
    def test_ok(self) -> None:
        assert validate_category("ИИ") == "ИИ"

    def test_empty(self) -> None:
        with pytest.raises(ValidationError):
            validate_category("")


class TestDateUtils:
    def test_parse_format_roundtrip(self) -> None:
        from app.utils.dates import format_date

        assert parse_user_date("01.01.2026").isoformat() == "2026-01-01"
        assert format_date(parse_user_date("01.01.2026")) == "01.01.2026"

    def test_days_until(self) -> None:
        from datetime import date

        assert days_until(date(2026, 7, 1), date(2026, 6, 26)) == 5

    @pytest.mark.parametrize(
        ("start", "period", "expected"),
        [
            ("2026-01-31", "monthly", "2026-02-28"),
            ("2024-01-31", "monthly", "2024-02-29"),  # leap year
            ("2026-02-28", "monthly", "2026-03-28"),
            ("2026-03-31", "monthly", "2026-04-30"),
            ("2026-07-01", "weekly", "2026-07-08"),
            ("2026-07-01", "quarterly", "2026-10-01"),
            ("2026-07-01", "yearly", "2027-07-01"),
        ],
    )
    def test_shift_date(self, start: str, period: str, expected: str) -> None:
        from datetime import date

        assert shift_date(date.fromisoformat(start), period).isoformat() == expected
