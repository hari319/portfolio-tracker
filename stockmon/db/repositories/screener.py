"""Repository for screener data — ``screener_day`` and ``screener_row`` tables.

This is the ONLY module that touches ``screener_cache.db``.
See docs/DATA_STORAGE_MIGRATION.md §5.3 for the hybrid schema design.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from .. import get_screener_connection

logger = logging.getLogger(__name__)

# The 15 "hot" columns promoted from JSON payload for indexed queries.
HOT_FIELDS = (
    "close", "open", "high", "low", "prev_close", "pct_change",
    "volume", "delivery_qty", "delivery_percent", "supertrend_dir",
    "sma_20", "close_near_high_pct", "volume_ratio_20", "range_pct_5",
    "series",
)


def _safe_float(val: Any) -> float | None:
    """Coerce to float, returning None on failure."""
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def save_screener_day(
    trade_date: str,
    data: dict[str, Any],
    items: list[dict[str, Any]],
) -> None:
    """Persist one day's screener data into both tables in one transaction.

    ``data`` is the full API response envelope.
    ``items`` is the list of per-stock dictionaries.
    """
    conn = get_screener_connection()
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    # Extract envelope (non-item top-level keys)
    envelope_keys = {k: v for k, v in data.items() if k != "items"}
    envelope_json = json.dumps(envelope_keys, ensure_ascii=False, default=str)

    total_items = data.get("total", len(items))
    timeframe = data.get("timeframe", "daily")
    source = data.get("source", "")

    conn.execute("BEGIN IMMEDIATE")
    try:
        # Upsert the day row
        conn.execute(
            """INSERT INTO screener_day(trade_date, fetched_at, total_items, timeframe, source, envelope)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(trade_date) DO UPDATE SET
                   fetched_at = excluded.fetched_at,
                   total_items = excluded.total_items,
                   timeframe = excluded.timeframe,
                   source = excluded.source,
                   envelope = excluded.envelope""",
            (trade_date, now, total_items, timeframe, source, envelope_json),
        )

        # Delete existing rows for this date (upsert approach)
        conn.execute("DELETE FROM screener_row WHERE trade_date = ?", (trade_date,))

        # Batch insert rows
        row_data = []
        for item in items:
            symbol = item.get("symbol")
            if not symbol:
                continue

            # Build the payload: everything NOT in the hot fields
            payload = {k: v for k, v in item.items() if k not in HOT_FIELDS and k != "symbol"}
            payload_json = json.dumps(payload, ensure_ascii=False, default=str)

            row_data.append((
                trade_date,
                symbol,
                _safe_float(item.get("close")),
                _safe_float(item.get("open")),
                _safe_float(item.get("high")),
                _safe_float(item.get("low")),
                _safe_float(item.get("prev_close")),
                _safe_float(item.get("pct_change")),
                _safe_float(item.get("volume")),
                _safe_float(item.get("delivery_qty")),
                _safe_float(item.get("delivery_percent")),
                str(item.get("supertrend_dir", "")) if item.get("supertrend_dir") is not None else None,
                _safe_float(item.get("sma_20")),
                _safe_float(item.get("close_near_high_pct")),
                _safe_float(item.get("volume_ratio_20")),
                _safe_float(item.get("range_pct_5")),
                str(item.get("series", "")) if item.get("series") is not None else None,
                payload_json,
            ))

        conn.executemany(
            """INSERT INTO screener_row(
                   trade_date, symbol, close, open, high, low, prev_close,
                   pct_change, volume, delivery_qty, delivery_percent,
                   supertrend_dir, sma_20, close_near_high_pct,
                   volume_ratio_20, range_pct_5, series, payload
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            row_data,
        )

        conn.execute("COMMIT")
        logger.info("Saved screener data: %s (%d rows)", trade_date, len(row_data))
    except Exception:
        conn.execute("ROLLBACK")
        raise


def list_saved_dates() -> list[dict[str, Any]]:
    """List all locally saved screener dates and metadata."""
    conn = get_screener_connection()
    rows = conn.execute(
        """SELECT trade_date, fetched_at, total_items
           FROM screener_day
           ORDER BY trade_date DESC"""
    ).fetchall()
    return [
        {
            "date": row["trade_date"],
            "total": row["total_items"],
            "fetched_at": row["fetched_at"],
        }
        for row in rows
    ]


def date_exists(trade_date: str) -> bool:
    """Check whether data for a given trade date is already stored."""
    conn = get_screener_connection()
    row = conn.execute(
        "SELECT 1 FROM screener_day WHERE trade_date = ?", (trade_date,)
    ).fetchone()
    return row is not None


def load_screener_for_date(trade_date: str) -> dict[str, Any] | None:
    """Load full screener data for a single date, reconstructing the original shape.

    Returns the data in the same format as the original JSON files.
    """
    conn = get_screener_connection()

    day_row = conn.execute(
        "SELECT trade_date, fetched_at, total_items, timeframe, source, envelope FROM screener_day WHERE trade_date = ?",
        (trade_date,),
    ).fetchone()
    if day_row is None:
        return None

    # Reconstruct the envelope
    envelope: dict[str, Any] = {}
    if day_row["envelope"]:
        try:
            envelope = json.loads(day_row["envelope"])
        except (json.JSONDecodeError, TypeError):
            pass

    # Load all rows for this date
    item_rows = conn.execute(
        """SELECT symbol, close, open, high, low, prev_close, pct_change,
                  volume, delivery_qty, delivery_percent, supertrend_dir,
                  sma_20, close_near_high_pct, volume_ratio_20, range_pct_5,
                  series, payload
           FROM screener_row WHERE trade_date = ?
           ORDER BY symbol""",
        (trade_date,),
    ).fetchall()

    items = []
    for row in item_rows:
        # Start with the cold payload
        try:
            item = json.loads(row["payload"]) if row["payload"] else {}
        except (json.JSONDecodeError, TypeError):
            item = {}
        # Overlay hot fields and symbol
        item["symbol"] = row["symbol"]
        for field in HOT_FIELDS:
            item[field] = row[field]
        items.append(item)

    # Rebuild the complete response shape
    result = dict(envelope)
    result["items"] = items
    result["date"] = trade_date
    result["total"] = day_row["total_items"]
    result["timeframe"] = day_row["timeframe"]
    return result


def load_hot_columns_for_dates(
    dates: list[str],
    columns: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Load only the promoted hot columns for the specified dates.

    This is the query that replaces the 154 MB file-parsing path in
    multi_day_analyzer.py — an indexed lookup returning only the needed data.
    """
    conn = get_screener_connection()
    if not dates:
        return []

    # Default to the 13 analyzer fields + symbol + trade_date
    if columns is None:
        columns = list(HOT_FIELDS)

    # Always include symbol and trade_date
    select_cols = ["trade_date", "symbol"] + [c for c in columns if c not in ("trade_date", "symbol")]
    select_clause = ", ".join(select_cols)

    placeholders = ", ".join("?" for _ in dates)
    rows = conn.execute(
        f"""SELECT {select_clause}
            FROM screener_row
            WHERE trade_date IN ({placeholders})
            ORDER BY symbol, trade_date""",
        dates,
    ).fetchall()

    return [dict(row) for row in rows]


def get_latest_date() -> str | None:
    """Return the most recent trade date in the cache, or None."""
    conn = get_screener_connection()
    row = conn.execute(
        "SELECT trade_date FROM screener_day ORDER BY trade_date DESC LIMIT 1"
    ).fetchone()
    return row["trade_date"] if row else None


def prune_old_dates(keep_days: int = 60) -> int:
    """Delete screener data older than the N most recent trading days.

    Returns the number of days deleted.  ON DELETE CASCADE handles screener_row.
    See §5.3 — retention is matched to the upstream API's rolling window.
    """
    conn = get_screener_connection()
    conn.execute("BEGIN IMMEDIATE")
    try:
        result = conn.execute(
            """DELETE FROM screener_day
               WHERE trade_date NOT IN (
                   SELECT trade_date FROM screener_day ORDER BY trade_date DESC LIMIT ?
               )""",
            (keep_days,),
        )
        deleted = result.rowcount
        conn.execute("COMMIT")
        if deleted > 0:
            logger.info("Pruned %d old screener day(s) beyond %d-day retention", deleted, keep_days)
        return deleted
    except Exception:
        conn.execute("ROLLBACK")
        raise
