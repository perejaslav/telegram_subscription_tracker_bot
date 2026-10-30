"""Legacy SQLite upgrade must preserve records and create a restorable snapshot."""

import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, text

from app.database.payment_migration import upgrade_payment_schema


def test_upgrade_legacy_sqlite_and_repeated_upgrade(tmp_path: Path) -> None:
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE subscriptions (id INTEGER PRIMARY KEY, price REAL NOT NULL)")
        conn.execute(
            "CREATE TABLE payments (id INTEGER PRIMARY KEY, subscription_id INTEGER NOT NULL, "
            "amount REAL NOT NULL)"
        )
        conn.execute("INSERT INTO subscriptions VALUES (1, 19.99)")
        conn.execute("INSERT INTO payments VALUES (1, 1, 12.35)")

    engine = create_engine(f"sqlite:///{path}")
    upgrade_payment_schema(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT amount_minor FROM payments")).scalar() == 1235
        assert conn.execute(text("SELECT price_minor FROM subscriptions")).scalar() == 1999
        assert conn.execute(text("SELECT count(*) FROM payments")).scalar() == 1
    backups = list(tmp_path.glob("old-pre-payment-migration-*.db"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT amount FROM payments").fetchone()[0] == 12.35
        assert "amount_minor" not in [c[1] for c in conn.execute("PRAGMA table_info(payments)")]
    upgrade_payment_schema(engine)
    assert len(list(tmp_path.glob("old-pre-payment-migration-*.db"))) == 1
    engine.dispose()
