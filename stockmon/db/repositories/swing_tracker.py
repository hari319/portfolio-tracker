"""Repository for the ``swing_tracker`` and ``swing_tracker_source`` tables.

Handles CRUD operations for swing trades and persisted trade source options.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .. import get_connection

logger = logging.getLogger(__name__)


def _row_to_dict(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "symbol": row["symbol"],
        "date": row["date"],
        "current_price": row["current_price"],
        "current_price_updated_at": row["current_price_updated_at"],
        "buy_zone": row["buy_zone"] or "",
        "stop_loss": row["stop_loss"] or "",
        "target1": row["target1"] or "",
        "target2": row["target2"] or "",
        "pattern_break": row["pattern_break"] or "",
        "thesis": row["thesis"] or "",
        "trade_source": row["trade_source"] or "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_trades() -> list[dict[str, Any]]:
    """Return all swing trades ordered by date DESC, then id DESC."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT id, symbol, date, current_price, current_price_updated_at,
                  buy_zone, stop_loss, target1, target2, pattern_break,
                  thesis, trade_source, created_at, updated_at
           FROM swing_tracker
           ORDER BY date DESC, id DESC"""
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_trade(trade_id: int) -> dict[str, Any] | None:
    """Return a single swing trade by id, or None."""
    conn = get_connection()
    row = conn.execute(
        """SELECT id, symbol, date, current_price, current_price_updated_at,
                  buy_zone, stop_loss, target1, target2, pattern_break,
                  thesis, trade_source, created_at, updated_at
           FROM swing_tracker
           WHERE id = ?""",
        (trade_id,),
    ).fetchone()
    if row is None:
        return None
    return _row_to_dict(row)


def add_trade(data: dict[str, Any]) -> dict[str, Any]:
    """Insert a new swing trade and return the persisted record."""
    conn = get_connection()
    now_iso = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    price_updated = data.get("current_price_updated_at") or now_iso

    cursor = conn.execute(
        """INSERT INTO swing_tracker (
               symbol, date, current_price, current_price_updated_at,
               buy_zone, stop_loss, target1, target2, pattern_break,
               thesis, trade_source, created_at, updated_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data["symbol"],
            data.get("date") or datetime.now().strftime("%Y-%m-%d"),
            data.get("current_price"),
            price_updated,
            str(data.get("buy_zone") or "").strip(),
            str(data.get("stop_loss") or "").strip(),
            str(data.get("target1") or "").strip(),
            str(data.get("target2") or "").strip(),
            str(data.get("pattern_break") or "").strip(),
            str(data.get("thesis") or ""),
            str(data.get("trade_source") or "").strip(),
            now_iso,
            now_iso,
        ),
    )
    new_id = cursor.lastrowid
    trade = get_trade(new_id)
    if trade is None:
        raise RuntimeError(f"Failed to retrieve newly inserted swing trade {new_id}")

    # Also make sure the trade source is recorded if not empty
    source = str(data.get("trade_source") or "").strip()
    if source:
        add_source(source)

    return trade


def update_trade(trade_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
    """Update an existing swing trade."""
    conn = get_connection()
    existing = get_trade(trade_id)
    if not existing:
        return None

    now_iso = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    symbol = data.get("symbol", existing["symbol"])
    trade_date = data.get("date", existing["date"])
    current_price = data.get("current_price", existing["current_price"])
    price_updated = data.get("current_price_updated_at", existing["current_price_updated_at"])
    buy_zone = str(data.get("buy_zone", existing["buy_zone"]) or "").strip()
    stop_loss = str(data.get("stop_loss", existing["stop_loss"]) or "").strip()
    target1 = str(data.get("target1", existing["target1"]) or "").strip()
    target2 = str(data.get("target2", existing["target2"]) or "").strip()
    pattern_break = str(data.get("pattern_break", existing["pattern_break"]) or "").strip()
    thesis = str(data.get("thesis", existing["thesis"]) if "thesis" in data else existing["thesis"])
    trade_source = str(data.get("trade_source", existing["trade_source"]) or "").strip()

    conn.execute(
        """UPDATE swing_tracker
           SET symbol = ?, date = ?, current_price = ?, current_price_updated_at = ?,
               buy_zone = ?, stop_loss = ?, target1 = ?, target2 = ?, pattern_break = ?,
               thesis = ?, trade_source = ?, updated_at = ?
           WHERE id = ?""",
        (
            symbol,
            trade_date,
            current_price,
            price_updated,
            buy_zone,
            stop_loss,
            target1,
            target2,
            pattern_break,
            thesis,
            trade_source,
            now_iso,
            trade_id,
        ),
    )

    if trade_source:
        add_source(trade_source)

    return get_trade(trade_id)


def delete_trade(trade_id: int) -> bool:
    """Delete a swing trade by id."""
    conn = get_connection()
    res = conn.execute("DELETE FROM swing_tracker WHERE id = ?", (trade_id,))
    return res.rowcount > 0


def update_trade_price(trade_id: int, current_price: float | None, updated_at: str | None = None) -> None:
    """Update current price and price timestamp for a swing trade."""
    conn = get_connection()
    now_iso = updated_at or datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    conn.execute(
        """UPDATE swing_tracker
           SET current_price = ?, current_price_updated_at = ?, updated_at = ?
           WHERE id = ?""",
        (current_price, now_iso, now_iso, trade_id),
    )


def list_sources() -> list[str]:
    """Return all persisted trade source names in alphabetical order."""
    conn = get_connection()
    rows = conn.execute("SELECT name FROM swing_tracker_source ORDER BY name COLLATE NOCASE ASC").fetchall()
    return [r["name"] for r in rows]


def add_source(name: str) -> str:
    """Persist a trade source option if it doesn't already exist."""
    clean_name = str(name or "").strip()
    if not clean_name:
        return ""
    conn = get_connection()
    now_iso = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    conn.execute(
        "INSERT OR IGNORE INTO swing_tracker_source (name, created_at) VALUES (?, ?)",
        (clean_name, now_iso),
    )
    return clean_name
