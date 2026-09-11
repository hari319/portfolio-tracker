"""Repository for the ``swing_tracker`` and ``swing_tracker_source`` tables.

Handles CRUD operations for swing trades and persisted trade source options.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .. import get_connection

logger = logging.getLogger(__name__)


def _normalize_sources(val: Any) -> tuple[str, list[str]]:
    """Normalize trade source input (list or comma-separated string) to (str, list)."""
    if isinstance(val, list):
        items = [str(s).strip() for s in val if str(s).strip()]
    elif isinstance(val, str):
        items = [s.strip() for s in val.split(",") if s.strip()]
    else:
        items = []
    # Deduplicate while preserving order
    seen = set()
    deduped = []
    for s in items:
        if s not in seen:
            seen.add(s)
            deduped.append(s)
    return (", ".join(deduped), deduped)


def _row_to_dict(row) -> dict[str, Any]:
    raw_source = row["trade_source"] or ""
    _, sources = _normalize_sources(raw_source)
    status = row["status"] if "status" in row.keys() else "active"
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
        "trade_source": raw_source,
        "trade_sources": sources,
        "status": status or "active",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_trades(status: str | None = None) -> list[dict[str, Any]]:
    """Return all swing trades ordered by date DESC, then id DESC, optionally filtered by status."""
    conn = get_connection()
    if status:
        rows = conn.execute(
            """SELECT id, symbol, date, current_price, current_price_updated_at,
                      buy_zone, stop_loss, target1, target2, pattern_break,
                      thesis, trade_source, status, created_at, updated_at
               FROM swing_tracker
               WHERE status = ?
               ORDER BY date DESC, id DESC""",
            (status,),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT id, symbol, date, current_price, current_price_updated_at,
                      buy_zone, stop_loss, target1, target2, pattern_break,
                      thesis, trade_source, status, created_at, updated_at
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
                  thesis, trade_source, status, created_at, updated_at
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
    status = str(data.get("status") or "active").strip().lower()

    source_input = data.get("trade_sources")
    if source_input is None:
        source_input = data.get("trade_source")
    source_str, sources_list = _normalize_sources(source_input)

    cursor = conn.execute(
        """INSERT INTO swing_tracker (
               symbol, date, current_price, current_price_updated_at,
               buy_zone, stop_loss, target1, target2, pattern_break,
               thesis, trade_source, status, created_at, updated_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
            source_str,
            status,
            now_iso,
            now_iso,
        ),
    )
    new_id = cursor.lastrowid
    trade = get_trade(new_id)
    if trade is None:
        raise RuntimeError(f"Failed to retrieve newly inserted swing trade {new_id}")

    # Register all unique sources
    for src in sources_list:
        add_source(src)

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
    status = str(data.get("status", existing.get("status", "active"))).strip().lower()

    if data.get("trade_sources") is not None:
        source_str, sources_list = _normalize_sources(data["trade_sources"])
    elif data.get("trade_source") is not None:
        source_str, sources_list = _normalize_sources(data["trade_source"])
    else:
        source_str = existing["trade_source"]
        sources_list = existing.get("trade_sources", [])

    conn.execute(
        """UPDATE swing_tracker
           SET symbol = ?, date = ?, current_price = ?, current_price_updated_at = ?,
               buy_zone = ?, stop_loss = ?, target1 = ?, target2 = ?, pattern_break = ?,
               thesis = ?, trade_source = ?, status = ?, updated_at = ?
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
            source_str,
            status,
            now_iso,
            trade_id,
        ),
    )

    for src in sources_list:
        add_source(src)

    return get_trade(trade_id)


def update_trade_status(trade_id: int, status: str) -> dict[str, Any] | None:
    """Update status of a swing trade (e.g. 'active' -> 'completed')."""
    conn = get_connection()
    now_iso = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    res = conn.execute(
        "UPDATE swing_tracker SET status = ?, updated_at = ? WHERE id = ?",
        (status, now_iso, trade_id),
    )
    if res.rowcount == 0:
        return None
    return get_trade(trade_id)


def delete_trade(trade_id: int) -> bool:
    """Permanently delete a swing trade by id."""
    conn = get_connection()
    res = conn.execute("DELETE FROM swing_tracker WHERE id = ?", (trade_id,))
    return res.rowcount > 0


def bulk_delete_trades(trade_ids: list[int]) -> int:
    """Permanently delete multiple swing trades by ID."""
    if not trade_ids:
        return 0
    conn = get_connection()
    placeholders = ",".join("?" for _ in trade_ids)
    res = conn.execute(f"DELETE FROM swing_tracker WHERE id IN ({placeholders})", trade_ids)
    return res.rowcount


def delete_all_completed() -> int:
    """Permanently delete all completed swing trades."""
    conn = get_connection()
    res = conn.execute("DELETE FROM swing_tracker WHERE status = 'completed'")
    return res.rowcount


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
