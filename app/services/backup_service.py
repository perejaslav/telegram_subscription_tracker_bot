"""Online SQLite backup, integrity validation and retention."""

from __future__ import annotations

import logging
import os
import sqlite3
import tempfile
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy.engine import make_url

from app.config.settings import PROJECT_ROOT, settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class BackupResult:
    path: Path
    size_bytes: int


class BackupService:
    def __init__(self, backups_dir: Path | None = None, database_url: str | None = None):
        self.backups_dir = backups_dir or PROJECT_ROOT / "backups"
        self.database_url = database_url or settings.database_url
        self.backups_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self) -> BackupResult:
        source = self._resolve_sqlite_path(self.database_url)
        if source is None or not source.is_file():
            raise FileNotFoundError(f"SQLite database not found: {source}")
        stamp = datetime.now(UTC).strftime("%Y-%m-%d_%H-%M-%S_%f")
        target = self.backups_dir / f"subscriptions_{stamp}.db"
        pending = target.with_suffix(".pending")
        try:
            with closing(sqlite3.connect(f"file:{source}?mode=ro", uri=True)) as source_conn:
                with closing(sqlite3.connect(pending)) as target_conn:
                    source_conn.backup(target_conn)
                    result = target_conn.execute("PRAGMA integrity_check").fetchone()[0]
                    if result != "ok":
                        raise RuntimeError(f"SQLite integrity check failed: {result}")
            with closing(sqlite3.connect(pending)) as check_conn:
                if check_conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise RuntimeError("Backup verification failed")
            os.replace(pending, target)
        finally:
            pending.unlink(missing_ok=True)
        self.cleanup_old_backups()
        logger.info("SQLite online backup created: %s", target)
        return BackupResult(target, target.stat().st_size)

    def cleanup_old_backups(self, days: int = 30) -> None:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        for path in self.backups_dir.glob("subscriptions_*.db"):
            if datetime.fromtimestamp(path.stat().st_mtime, UTC) < cutoff:
                path.unlink()

    @staticmethod
    def verify_restore(backup_path: Path) -> None:
        """Restore to an isolated temporary database and validate its contents.

        Never overwrite the live database during verification.
        """
        with tempfile.TemporaryDirectory(prefix="bot-restore-") as directory:
            restored = Path(directory) / "restored.db"
            with closing(sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True)) as source:
                with closing(sqlite3.connect(restored)) as destination:
                    source.backup(destination)
                    integrity = destination.execute("PRAGMA integrity_check").fetchone()[0]
                    if integrity != "ok":
                        raise RuntimeError(f"Restored SQLite integrity check failed: {integrity}")
                    # Force a schema read as well as a page-integrity pass.
                    destination.execute("SELECT name FROM sqlite_master").fetchall()

    @staticmethod
    def _resolve_sqlite_path(url: str) -> Path | None:
        parsed = make_url(url)
        if (
            not parsed.drivername.startswith("sqlite")
            or not parsed.database
            or parsed.database == ":memory:"
        ):
            return None
        path = Path(parsed.database)
        return path if path.is_absolute() else PROJECT_ROOT / path


__all__ = ["BackupResult", "BackupService"]
