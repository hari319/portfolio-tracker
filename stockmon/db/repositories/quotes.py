"""Repository for the ``quote_cache`` table.

Replaces ``data_fetcher.py``'s use of ``data/quotes_cache.json``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .. import get_connection

logger = logging.getLogger(__name__)


def load_quotes_cache() -> dict[str, dict[str, Any]]:
    """Return all cached quotes keyed by symbol."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT symbol, price, currency, name, fetched_at FROM quote_cache"
    ).fetchall()
    cache: dict[str, dict[str, Any]] = {}
    for row in rows:
        cache[row["symbol"]] = {
            "price": row["price"],
            "currency": row["currency"],
            "name": row["name"],
            "fetched_at": row["fetched_at"],
        }
    return cache


def get_quote(symbol: str) -> dict[str, Any] | None:
    """Return a single cached quote, or None."""
    conn = get_connection()
    row = conn.execute(
        "SELECT symbol, price, currency, name, fetched_at FROM quote_cache WHERE symbol = ?",
        (symbol,),
    ).fetchone()
    if row is None:
        return None
    return {
        "price": row["price"],
        "currency": row["currency"],
        "name": row["name"],
        "fetched_at": row["fetched_at"],
    }


def save_quote(symbol: str, quote: dict[str, Any]) -> None:
    """Upsert a quote into the cache."""
    conn = get_connection()
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    conn.execute(
        """INSERT INTO quote_cache(symbol, price, currency, name, fetched_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(symbol) DO UPDATE SET
               price = excluded.price,
               currency = excluded.currency,
               name = excluded.name,
               fetched_at = excluded.fetched_at""",
        (
            symbol,
            quote.get("price"),
            quote.get("currency"),
            quote.get("name"),
            now,
        ),
    )
