"""Database backup service — copies the SQLite file with a timestamped name."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.config.settings import PROJECT_ROOT, settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class BackupResult:
    path: Path
    size_bytes: int


class BackupService:
    """Create timestamped SQLite backups under ``backups/``."""

    def __init__(self) -> None:
        self.backups_dir: Path = PROJECT_ROOT / "backups"
        self.backups_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self) -> BackupResult:
        db_path = self._resolve_sqlite_path(settings.database_url)
        if db_path is None or not db_path.exists():
            raise FileNotFoundError(f"Database file not found: {db_path}")
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        target = self.backups_dir / f"subscriptions_{stamp}.db"
        counter = 1
        while target.exists():
            target = self.backups_dir / f"subscriptions_{stamp}_{counter}.db"
            counter += 1
        shutil.copy2(db_path, target)
        size = target.stat().st_size
        logger.info("Backup created: %s (%s bytes)", target, size)
        return BackupResult(path=target, size_bytes=size)

    @staticmethod
    def _resolve_sqlite_path(url: str) -> Path | None:
        if not url.startswith("sqlite"):
            return None
        raw = url.replace("sqlite:///", "", 1)
        if not raw or raw == ":memory:":
            return None
        path = Path(raw)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path


__all__ = ["BackupResult", "BackupService"]
