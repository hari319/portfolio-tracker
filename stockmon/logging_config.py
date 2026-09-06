"""Central logging configuration.

Both entry points (``app.py`` and ``scheduled_run.py``) call
:func:`configure_logging` once with their own log file so web activity and
scheduled runs stay in separate, rotating files.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .paths import ADDITIONS_LOG_FILE, APP_LOG_FILE, ensure_directories

_CONFIGURED = False
_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def configure_logging(
    log_file: str | Path = APP_LOG_FILE,
    level: int = logging.INFO,
    console: bool = True,
) -> None:
    """Attach a rotating file handler (and optionally a console handler)."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    ensure_directories()
    formatter = logging.Formatter(_FORMAT)
    root = logging.getLogger()
    root.setLevel(level)

    file_handler = RotatingFileHandler(
        Path(log_file), maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    if console:
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        root.addHandler(stream_handler)

    # yfinance/urllib3 are extremely chatty at DEBUG/INFO level.
    logging.getLogger("yfinance").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("peewee").setLevel(logging.WARNING)

    _CONFIGURED = True
    clean_old_logs(max_age_days=1)


def clean_old_logs(max_age_days: int = 1) -> int:
    """Clean log files and rolled over logs older than ``max_age_days`` (1 day)."""
    import time
    from .paths import LOG_DIR
    if not LOG_DIR.exists():
        return 0

    now = time.time()
    cutoff = now - (max_age_days * 86400)
    cleaned = 0

    # Clean rolled-over log files (*.log.1, *.log.2, etc.) or stale console logs
    for p in LOG_DIR.iterdir():
        if not p.is_file():
            continue
        try:
            mtime = p.stat().st_mtime
            # If it's a rolled-over file (.log.1, .log.2) or console log older than cutoff
            if (p.name.count(".log.") > 0 or p.name == "scheduled_run_console.log") and mtime < cutoff:
                p.unlink()
                cleaned += 1
            # For primary log files (app.log, scheduler.log), if modified > 1 day ago and size is huge, truncate or rotate
            elif p.suffix == ".log" and mtime < cutoff and p.stat().st_size > 500_000:
                # Truncate old stale log
                with p.open("w", encoding="utf-8") as f:
                    f.write(f"--- Log truncated on startup ({time.strftime('%Y-%m-%d %H:%M:%S')}) ---\n")
                cleaned += 1
        except OSError:
            pass

    return cleaned


def get_additions_logger() -> logging.Logger:
    """Dedicated audit log of tickers added through the UI."""
    logger = logging.getLogger("stockmon.additions")
    if not logger.handlers:
        ensure_directories()
        handler = RotatingFileHandler(
            ADDITIONS_LOG_FILE, maxBytes=500_000, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
