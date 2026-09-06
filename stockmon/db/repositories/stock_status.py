"""Repository for the ``stock_status`` table.

Replaces ``stock_status.py``'s use of ``data/stock_status.json``.
The whole-list rewrite becomes per-row add/update/delete.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from .. import get_connection

logger = logging.getLogger(__name__)


def _row_to_dict(row) -> dict[str, Any]:
    """Convert a sqlite3.Row to the dict shape the frontend/routes expect."""
    return {
        "id": row["id"],
        "symbol": row["symbol"],
        "name": row["name"],
        "date_of_analysis": row["date_of_analysis"],
        "price_of_analysis": row["price_of_analysis"],
        "best_entry": row["best_entry"],
        "status": row["status"],
        "base": [row["base_low"] or "", row["base_high"] or ""],
        "bull": [row["bull_low"] or "", row["bull_high"] or ""],
        "bear": [row["bear_low"] or "", row["bear_high"] or ""],
        "remarks": row["remarks"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _parse_range(val) -> tuple[Any, Any]:
    """Parse a [low, high] list into two values (may be None or float)."""
    if not isinstance(val, (list, tuple)) or len(val) < 2:
        return (None, None)
    low = val[0]
    high = val[1]
    try:
        low = float(low) if low not in (None, "", "None") else None
    except (ValueError, TypeError):
        low = None
    try:
        high = float(high) if high not in (None, "", "None") else None
    except (ValueError, TypeError):
        high = None
    return (low, high)


def load_all() -> list[dict[str, Any]]:
    """Return all stock status entries, newest first."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT id, symbol, name, date_of_analysis, price_of_analysis,
                  best_entry, status, base_low, base_high,
                  bull_low, bull_high, bear_low, bear_high,
                  remarks, created_at, updated_at
           FROM stock_status
           ORDER BY created_at DESC"""
    ).fetchall()
    return [_row_to_dict(row) for row in rows]


def get_by_id(item_id: str) -> dict[str, Any] | None:
    """Return a single stock status entry, or None."""
    conn = get_connection()
    row = conn.execute(
        """SELECT id, symbol, name, date_of_analysis, price_of_analysis,
                  best_entry, status, base_low, base_high,
                  bull_low, bull_high, bear_low, bear_high,
                  remarks, created_at, updated_at
           FROM stock_status WHERE id = ?""",
        (item_id,),
    ).fetchone()
    if row is None:
        return None
    return _row_to_dict(row)


def add(entry: dict[str, Any]) -> None:
    """Insert a new stock status entry."""
    conn = get_connection()
    base_low, base_high = _parse_range(entry.get("base"))
    bull_low, bull_high = _parse_range(entry.get("bull"))
    bear_low, bear_high = _parse_range(entry.get("bear"))
    now = datetime.now().isoformat()

    conn.execute(
        """INSERT INTO stock_status(
               id, symbol, name, date_of_analysis, price_of_analysis,
               best_entry, status, base_low, base_high,
               bull_low, bull_high, bear_low, bear_high,
               remarks, created_at, updated_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            entry["id"],
            entry["symbol"],
            entry.get("name", ""),
            entry["date_of_analysis"],
            entry.get("price_of_analysis"),
            entry.get("best_entry"),
            entry.get("status", ""),
            base_low, base_high,
            bull_low, bull_high,
            bear_low, bear_high,
            entry.get("remarks", ""),
            entry.get("created_at", now),
            now,
        ),
    )


def update(item_id: str, changes: dict[str, Any]) -> None:
    """Update specific fields of a stock status entry."""
    conn = get_connection()
    now = datetime.now().isoformat()

    # Build SET clause dynamically from provided changes
    sets: list[str] = []
    params: list[Any] = []

    simple_fields = ["name", "date_of_analysis", "price_of_analysis",
                     "best_entry", "status", "remarks"]
    for field in simple_fields:
        if field in changes:
            sets.append(f"{field} = ?")
            params.append(changes[field])

    for key in ("base", "bull", "bear"):
        if key in changes:
            low, high = _parse_range(changes[key])
            sets.append(f"{key}_low = ?")
            sets.append(f"{key}_high = ?")
            params.append(low)
            params.append(high)

    if not sets:
        return

    sets.append("updated_at = ?")
    params.append(now)
    params.append(item_id)

    conn.execute(
        f"UPDATE stock_status SET {', '.join(sets)} WHERE id = ?",
        params,
    )


def delete(item_id: str) -> None:
    """Delete a stock status entry by id."""
    conn = get_connection()
    conn.execute("DELETE FROM stock_status WHERE id = ?", (item_id,))
