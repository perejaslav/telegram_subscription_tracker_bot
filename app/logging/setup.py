"""Application logging setup.

Logs go to ``logs/app.log`` (rotating) and to stderr. A small filter masks
the bot token and obviously private URL query params so they never end up in
logs (per spec §6 / §16).
"""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.config.settings import PROJECT_ROOT, settings

# ---------------------------------------------------------------------------
# Sensitive-data masking
# ---------------------------------------------------------------------------

_TOKEN_PATTERN = re.compile(r"(?i)(bot)?:?(\d{6,12}:[A-Za-z0-9_-]{20,})")
# Mask query params that look like tokens / keys / sessions.
_PRIVATE_QUERY_KEYS = re.compile(
    r"(?i)(token|access_token|sid|phpsessid|api[_-]?key|password)=[^&\s]+"
)


class SensitiveDataFilter(logging.Filter):
    """Strip bot tokens and private URL query params from log records."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        msg = record.getMessage()
        msg = _TOKEN_PATTERN.sub("bot:<TOKEN>", msg)
        msg = _PRIVATE_QUERY_KEYS.sub(lambda m: f"{m.group(1)}=***", msg)
        record.msg = msg
        record.args = ()
        return True


def setup_logging() -> None:
    """Configure root logger once per process."""
    root = logging.getLogger()
    if getattr(root, "_app_configured", False):
        return

    root.setLevel(settings.log_level)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    mask = SensitiveDataFilter()

    # File handler (rotating, ~1 MB × 3 backups).
    log_dir: Path = PROJECT_ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(mask)

    # Console handler.
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.addFilter(mask)

    root.addHandler(file_handler)
    root.addHandler(console_handler)
    root._app_configured = True  # type: ignore[attr-defined]

    # Quiet noisy libraries.
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
    logging.getLogger("apscheduler.scheduler").setLevel(logging.INFO)