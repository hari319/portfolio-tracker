"""Repository for the ``summary_value`` table.

Encapsulates fixed user-entered summary panel figures (§8).
See docs/DATA_STORAGE_MIGRATION.md §5.4 and docs/SHEET_FORMAT.md §4.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .. import get_connection

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


DEFAULT_SUMMARY_FIELDS = [
    ("current_stock_etf_invest", 0.0, "Current Stock & ETF Invest"),
    ("current_mf_invest", 0.0, "Current MF Invest"),
    ("current_mf_redeem", 0.0, "Current MF Redeem"),
    ("loan_amount", 0.0, "Loan Amount"),
    ("current_mf_redeem_profit", 0.0, "Current MF Redeem + Profit"),
]


def ensure_defaults() -> None:
    """Seed default summary keys if not present."""
    conn = get_connection()
    now = _utc_now_iso()
    for key, val, label in DEFAULT_SUMMARY_FIELDS:
        conn.execute(
            """
            INSERT OR IGNORE INTO summary_value (key, value, label, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (key, val, label, now),
        )


def get_all() -> dict[str, float]:
    """Return dictionary of {key: value} for all summary fields."""
    conn = get_connection()
    ensure_defaults()
    rows = conn.execute("SELECT key, value FROM summary_value").fetchall()
    return {row["key"]: float(row["value"]) for row in rows}


def get_all_rows() -> list[dict[str, Any]]:
    """Return all rows with metadata for the summary settings UI."""
    conn = get_connection()
    ensure_defaults()
    rows = conn.execute("SELECT key, value, label, updated_at FROM summary_value ORDER BY rowid").fetchall()
    return [dict(r) for r in rows]


def upsert(key: str, value: float, label: str | None = None) -> None:
    """Insert or update a summary value."""
    conn = get_connection()
    now = _utc_now_iso()
    if label:
        conn.execute(
            """
            INSERT INTO summary_value (key, value, label, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                label = excluded.label,
                updated_at = excluded.updated_at
            """,
            (key, value, label, now),
        )
    else:
        conn.execute(
            """
            INSERT INTO summary_value (key, value, label, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (key, value, key.replace("_", " ").title(), now),
        )
