"""Filesystem layout for the application.

All locations can be overridden with environment variables so the Flask app and
the scheduled task can be pointed at the same folders even when they are started
from different working directories.
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _dir_from_env(var: str, default: Path) -> Path:
    value = os.environ.get(var)
    return Path(value).expanduser().resolve() if value else default


CONFIG_DIR = _dir_from_env("STOCKMON_CONFIG_DIR", BASE_DIR / "config")
DATA_DIR = _dir_from_env("STOCKMON_DATA_DIR", BASE_DIR / "data")
LOG_DIR = _dir_from_env("STOCKMON_LOG_DIR", BASE_DIR / "logs")

SETTINGS_FILE = CONFIG_DIR / "settings.json"
SETTINGS_TEMPLATE_FILE = BASE_DIR / "config.template.json"
PORTFOLIOS_FILE = CONFIG_DIR / "portfolios.json"

SNAPSHOT_FILE = DATA_DIR / "snapshot.json"
STATUS_FILE = DATA_DIR / "status.json"
PENDING_ADDITIONS_FILE = DATA_DIR / "pending_additions.json"
STOCK_STATUS_FILE = DATA_DIR / "stock_status.json"
QUOTES_CACHE_FILE = DATA_DIR / "quotes_cache.json"
SCREENER_DIR = DATA_DIR / "screener"
SCREENER_CACHE_FILE = DATA_DIR / "screener_cache.json"

# SQLite database files (§4.1 of DATA_STORAGE_MIGRATION.md)
DB_FILE = DATA_DIR / "stockmon.db"
SCREENER_DB_FILE = DATA_DIR / "screener_cache.db"
BACKUP_DIR = _dir_from_env("STOCKMON_BACKUP_DIR", BASE_DIR / "backups")

APP_LOG_FILE = LOG_DIR / "app.log"
SCHEDULER_LOG_FILE = LOG_DIR / "scheduler.log"
ADDITIONS_LOG_FILE = LOG_DIR / "ticker_additions.log"


def ensure_directories() -> None:
    """Create the config/data/log/backup directories if they do not exist yet."""
    for directory in (CONFIG_DIR, DATA_DIR, LOG_DIR, SCREENER_DIR, BACKUP_DIR):
        directory.mkdir(parents=True, exist_ok=True)
