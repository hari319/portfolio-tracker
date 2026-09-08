"""Repository for the ``dividend`` table.

All SQL for dividend tracking is encapsulated here.
See docs/DATA_STORAGE_MIGRATION.md §5.4 and docs/SHEET_FORMAT.md.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .. import get_connection

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def list_dividends(portfolio_name: str) -> list[dict[str, Any]]:
    """Return all dividend records for a portfolio ordered by received date descending."""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT id, portfolio_name, symbol, value, received_date, created_at
        FROM dividend
        WHERE portfolio_name = ?
        ORDER BY id DESC
        """,
        (portfolio_name,),
    ).fetchall()
    return [dict(r) for r in rows]


def add_dividend(
    portfolio_name: str,
    symbol: str,
    value: float,
    received_date: str,
) -> int:
    """Insert a new dividend record."""
    conn = get_connection()
    now = _utc_now_iso()
    cur = conn.execute(
        """
        INSERT INTO dividend (portfolio_name, symbol, value, received_date, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (portfolio_name, symbol.strip().upper(), value, received_date.strip(), now),
    )
    return cur.lastrowid


def delete_dividend(dividend_id: int) -> bool:
    """Delete a dividend record by ID."""
    conn = get_connection()
    cur = conn.execute("DELETE FROM dividend WHERE id = ?", (dividend_id,))
    return cur.rowcount > 0


def total_dividends(portfolio_name: str | None = None) -> float:
    """Return total dividend amount for a portfolio or all portfolios."""
    conn = get_connection()
    if portfolio_name:
        row = conn.execute(
            "SELECT COALESCE(SUM(value), 0.0) AS total FROM dividend WHERE portfolio_name = ?",
            (portfolio_name,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT COALESCE(SUM(value), 0.0) AS total FROM dividend"
        ).fetchone()
    return float(row["total"]) if row else 0.0
