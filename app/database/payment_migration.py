"""Backward-compatible SQLite stage-4 payment schema upgrade.

Preserves historical REAL columns for old readers; integer minor units become
authoritative for new writes. Historical values are rounded to 2 decimals once.
Run only after taking a verified SQLite backup in production.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def upgrade_payment_schema(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return
    inspector = inspect(engine)
    if "payments" not in inspector.get_table_names():
        return
    payments_columns = {column["name"] for column in inspector.get_columns("payments")}
    if "amount_minor" not in payments_columns:
        db_filename = engine.url.database
        if not db_filename or db_filename == ":memory:":
            raise ValueError("Legacy payment schema requires file-backed SQLite backup")
        backup_path = Path(db_filename).with_name(
            f"{Path(db_filename).stem}-pre-payment-migration-"
            f"{datetime.now(UTC).strftime('%Y%m%d-%H%M%S%f')}.db"
        )
        with sqlite3.connect(db_filename) as source, sqlite3.connect(backup_path) as target:
            source.backup(target)
            if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Payment migration backup failed integrity check")
    with engine.begin() as conn:
        for table, cols in {
            "subscriptions": {"price_minor": "INTEGER"},
            "payments": {
                "amount_minor": "INTEGER",
                "billing_due_date": "DATE",
                "corrected_at": "DATETIME",
            },
        }.items():
            existing = {c["name"] for c in inspect(conn).get_columns(table)}
            for name, kind in cols.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {kind}"))
        for table, original, minor in (
            ("subscriptions", "price", "price_minor"),
            ("payments", "amount", "amount_minor"),
        ):
            # Identifiers come exclusively from this fixed, reviewed tuple.
            rows = conn.execute(
                text(f"SELECT id, {original} FROM {table} WHERE {minor} IS NULL")  # noqa: S608
            ).all()
            for row_id, value in rows:
                amount = Decimal(str(value))
                if not amount.is_finite() or abs(amount) > Decimal("999999999999.99"):
                    raise ValueError(f"Unsafe legacy amount in {table} id={row_id}")
                cents = int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
                conn.execute(
                    text(f"UPDATE {table} SET {minor}=:cents WHERE id=:id"),  # noqa: S608
                    {"cents": cents, "id": row_id},
                )
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_payment_billing_cycle "
                "ON payments(subscription_id, billing_due_date)"
            )
        )
