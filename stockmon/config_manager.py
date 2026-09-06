"""Reading and writing ``config/settings.json``.

The same file is read by the Flask UI and by the Windows scheduled task, which
is how a schedule change made in the browser reaches the scheduler.
"""

from __future__ import annotations

import copy
import logging
import re
from typing import Any, Iterable

from .errors import ValidationError
from .jsonstore import read_json, write_json
from .paths import SETTINGS_FILE, ensure_directories

logger = logging.getLogger(__name__)

TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

DEFAULT_SETTINGS: dict[str, Any] = {
    "schedule": {
        "run_times": ["09:30", "11:30"],
        "timezone": "Asia/Kolkata",
        "task_name": "StockMonitor-DailyUpdate",
    },
    "data": {
        "default_exchange_suffix": ".NS",
        "history_period": "10y",
        "ema_periods": [9, 21, 50, 100, 200],
        "max_workers": 4,
        "retries": 2,
        "retry_backoff_seconds": 1.5,
        # Matches the upstream API 60-day rolling window (§5.3 of DATA_STORAGE_MIGRATION.md)
        "screener_retention_days": 60,
    },
    "ui": {
        "status_poll_seconds": 5,
        "price_decimals": 2,
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_settings() -> dict[str, Any]:
    """Return settings merged over the defaults, creating the file if missing."""
    ensure_directories()
    stored = read_json(SETTINGS_FILE, default=None)
    if stored is None:
        logger.info("No settings file found, creating default %s", SETTINGS_FILE)
        write_json(SETTINGS_FILE, DEFAULT_SETTINGS)
        return copy.deepcopy(DEFAULT_SETTINGS)
    if not isinstance(stored, dict):
        logger.error("Malformed settings file %s - using defaults", SETTINGS_FILE)
        return copy.deepcopy(DEFAULT_SETTINGS)
    return _deep_merge(DEFAULT_SETTINGS, stored)


def save_settings(settings: dict[str, Any]) -> None:
    write_json(SETTINGS_FILE, settings)


def get_run_times() -> list[str]:
    times = load_settings()["schedule"]["run_times"]
    if not isinstance(times, list) or not times:
        logger.warning("Invalid run_times in settings, using defaults")
        return list(DEFAULT_SETTINGS["schedule"]["run_times"])
    return [str(value) for value in times]


def validate_run_times(times: Iterable[Any]) -> list[str]:
    """Normalise and validate a list of ``HH:MM`` strings."""
    cleaned: list[str] = []
    for raw in times:
        value = str(raw).strip()
        if not TIME_PATTERN.match(value):
            raise ValidationError(f"'{value}' is not a valid 24-hour time (expected HH:MM).")
        if value in cleaned:
            raise ValidationError(f"Duplicate run time '{value}'.")
        cleaned.append(value)
    if len(cleaned) != 2:
        raise ValidationError("Exactly two scheduled run times are required.")
    return sorted(cleaned)


def sync_scheduled_task() -> bool:
    """Sync Windows Task Scheduler triggers with settings.json automatically."""
    import subprocess
    from .paths import BASE_DIR

    script = BASE_DIR / "scripts" / "register_task.ps1"
    if not script.exists():
        return False
    try:
        cmd = [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            logger.info("Auto-synced Windows Task Scheduler triggers: %s", result.stdout.strip())
            return True
        logger.warning("Failed to auto-sync Task Scheduler: %s", result.stderr.strip())
        return False
    except Exception as exc:
        logger.warning("Error running register_task.ps1: %s", exc)
        return False


def set_run_times(times: Iterable[Any]) -> list[str]:
    """Persist validated run times, sync with Windows Task Scheduler, and return them."""
    cleaned = validate_run_times(times)
    settings = load_settings()
    settings["schedule"]["run_times"] = cleaned
    save_settings(settings)
    logger.info("Scheduled run times updated to %s", ", ".join(cleaned))
    sync_scheduled_task()
    return cleaned
