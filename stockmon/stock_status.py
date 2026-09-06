"""Stock Status data storage and management.

Persists analysis records (Ticker, Date of Analysis, Price, Base/Bull/Bear targets, Remarks)
into the ``stock_status`` table in ``stockmon.db``.

Migrated from flat JSON (data/stock_status.json) to per-row CRUD operations
via ``stockmon.db.repositories.stock_status``.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from .errors import ValidationError
from .db.repositories import stock_status as _repo
from .portfolio import normalize_symbol

logger = logging.getLogger(__name__)


def load_stock_statuses() -> list[dict[str, Any]]:
    """Return the list of saved stock status entries."""
    return _repo.load_all()


def save_stock_statuses(items: list[dict[str, Any]]) -> None:
    """Save the list of stock status entries.

    Note: This legacy function is kept for API compatibility but now
    delegates to per-row operations. For normal use, prefer add/update/delete.
    """
    # Bulk replace: delete all and re-insert
    from .db import get_connection
    conn = get_connection()
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("DELETE FROM stock_status")
        for item in items:
            _repo.add(item)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def add_stock_status(payload: dict[str, Any]) -> dict[str, Any]:
    """Add a new stock status entry and persist it."""
    raw_symbol = payload.get("symbol", "").strip()
    if not raw_symbol:
        raise ValidationError("Ticker symbol is required.")

    symbol = normalize_symbol(raw_symbol)
    name = payload.get("name", "").strip()
    price = payload.get("price_of_analysis")

    try:
        price_val = float(price) if price is not None and price != "" else None
    except (ValueError, TypeError):
        price_val = None

    date_str = payload.get("date_of_analysis")
    if not date_str or not str(date_str).strip():
        date_str = datetime.now().strftime("%Y-%m-%d")
    else:
        date_str = str(date_str).strip()

    base = payload.get("base") or ["", ""]
    bull = payload.get("bull") or ["", ""]
    bear = payload.get("bear") or ["", ""]

    if not isinstance(base, list):
        base = [str(base), ""]
    if not isinstance(bull, list):
        bull = [str(bull), ""]
    if not isinstance(bear, list):
        bear = [str(bear), ""]

    base = [str(base[0]) if len(base) > 0 else "", str(base[1]) if len(base) > 1 else ""]
    bull = [str(bull[0]) if len(bull) > 0 else "", str(bull[1]) if len(bull) > 1 else ""]
    bear = [str(bear[0]) if len(bear) > 0 else "", str(bear[1]) if len(bear) > 1 else ""]

    best_entry = payload.get("best_entry")
    try:
        best_entry_val = float(best_entry) if best_entry is not None and best_entry != "" else None
    except (ValueError, TypeError):
        best_entry_val = None

    status_val = str(payload.get("status", "")).strip()

    entry: dict[str, Any] = {
        "id": uuid.uuid4().hex[:12],
        "symbol": symbol,
        "name": name,
        "date_of_analysis": date_str,
        "price_of_analysis": price_val,
        "best_entry": best_entry_val,
        "status": status_val,
        "currency": payload.get("currency", "INR"),
        "base": base,
        "bull": bull,
        "bear": bear,
        "remarks": str(payload.get("remarks", "")).strip(),
        "created_at": datetime.now().isoformat(),
    }

    _repo.add(entry)
    logger.info("Added stock status entry for %s (id=%s)", symbol, entry["id"])
    return entry


def delete_stock_status(item_id: str) -> list[dict[str, Any]]:
    """Delete a stock status entry by id."""
    _repo.delete(item_id)
    logger.info("Deleted stock status entry with id=%s", item_id)
    return _repo.load_all()


def update_stock_status(item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Update an existing stock status entry by id."""
    existing = _repo.get_by_id(item_id)
    if existing is None:
        raise ValidationError(f"Stock status entry with id '{item_id}' not found.")

    # Build changes dict for the repository
    changes: dict[str, Any] = {}

    if "name" in payload and payload["name"]:
        changes["name"] = str(payload["name"]).strip()

    if "price_of_analysis" in payload and payload["price_of_analysis"] is not None and payload["price_of_analysis"] != "":
        try:
            changes["price_of_analysis"] = float(payload["price_of_analysis"])
        except (ValueError, TypeError):
            pass

    if "best_entry" in payload:
        best_val = payload["best_entry"]
        try:
            changes["best_entry"] = float(best_val) if best_val is not None and best_val != "" else None
        except (ValueError, TypeError):
            changes["best_entry"] = None

    if "status" in payload:
        changes["status"] = str(payload.get("status", "")).strip()

    if "date_of_analysis" in payload and payload["date_of_analysis"]:
        changes["date_of_analysis"] = str(payload["date_of_analysis"]).strip()

    for key in ("base", "bull", "bear"):
        if key in payload:
            val = payload[key]
            if not isinstance(val, list):
                val = [str(val), ""]
            changes[key] = [
                str(val[0]) if len(val) > 0 else "",
                str(val[1]) if len(val) > 1 else "",
            ]

    if "remarks" in payload:
        changes["remarks"] = str(payload.get("remarks", "")).strip()

    _repo.update(item_id, changes)
    logger.info("Updated stock status entry for %s (id=%s)", existing.get("symbol"), item_id)

    # Return the updated entry
    updated = _repo.get_by_id(item_id)
    return updated if updated else existing
