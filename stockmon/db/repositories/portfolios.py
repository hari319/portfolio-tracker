"""Repository for ``portfolio`` and ``portfolio_ticker`` tables.

Replaces ``portfolio.py``'s use of ``config/portfolios.json`` for data
and ``data/pending_additions.json``.  The public API contract is preserved:
functions return the same shapes as before.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .. import get_connection

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Portfolios
# ---------------------------------------------------------------------------

def ensure_portfolio(name: str, kind: str = "personal") -> None:
    """Create the portfolio row if it doesn't exist."""
    conn = get_connection()
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    conn.execute(
        "INSERT OR IGNORE INTO portfolio(name, kind, created_at) VALUES (?, ?, ?)",
        (name, kind, now),
    )


def load_portfolios(names: tuple[str, ...] = ("BAPA", "MADI")) -> dict[str, list[str]]:
    """Return portfolios as ``{name: [symbol, ...]}``, matching the old JSON shape."""
    conn = get_connection()
    result: dict[str, list[str]] = {}
    for name in names:
        ensure_portfolio(name)
        rows = conn.execute(
            "SELECT symbol FROM portfolio_ticker WHERE portfolio_name = ? ORDER BY added_at",
            (name,),
        ).fetchall()
        result[name] = [row["symbol"] for row in rows]
    return result


def save_portfolios(portfolios: dict[str, list[str]]) -> None:
    """Bulk-replace all portfolio tickers — used during import only.

    For normal add/remove operations, use ``add_ticker`` / ``remove_ticker``.
    """
    conn = get_connection()
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    conn.execute("BEGIN IMMEDIATE")
    try:
        for name, symbols in portfolios.items():
            ensure_portfolio(name)
            conn.execute("DELETE FROM portfolio_ticker WHERE portfolio_name = ?", (name,))
            for symbol in symbols:
                conn.execute(
                    "INSERT INTO portfolio_ticker(portfolio_name, symbol, added_at) VALUES (?, ?, ?)",
                    (name, symbol, now),
                )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def add_ticker(portfolio_name: str, symbol: str) -> None:
    """Add a ticker to a portfolio. Raises on duplicate (composite PK)."""
    conn = get_connection()
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    ensure_portfolio(portfolio_name)
    conn.execute(
        "INSERT INTO portfolio_ticker(portfolio_name, symbol, added_at) VALUES (?, ?, ?)",
        (portfolio_name, symbol, now),
    )


def remove_ticker(portfolio_name: str, symbol: str) -> None:
    """Remove a ticker from a portfolio."""
    conn = get_connection()
    conn.execute(
        "DELETE FROM portfolio_ticker WHERE portfolio_name = ? AND symbol = ?",
        (portfolio_name, symbol),
    )


def ticker_exists(portfolio_name: str, symbol: str) -> bool:
    """Check if a ticker is already in the portfolio."""
    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM portfolio_ticker WHERE portfolio_name = ? AND symbol = ?",
        (portfolio_name, symbol),
    ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# Pending additions
# ---------------------------------------------------------------------------

def record_pending_addition(portfolio_name: str, symbol: str) -> None:
    """Queue a ticker addition for the next scheduled run."""
    conn = get_connection()
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    conn.execute(
        "INSERT INTO pending_addition(portfolio_name, symbol, added_at) VALUES (?, ?, ?)",
        (portfolio_name, symbol, now),
    )


def consume_pending_additions() -> list[dict[str, Any]]:
    """Atomically read and mark all pending additions as consumed.

    Uses ``BEGIN IMMEDIATE`` so a concurrent ``record_pending_addition``
    lands *after* the snapshot and is picked up next run. Nothing is lost.
    (This fixes the §1.5 lost-update race.)
    """
    conn = get_connection()
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    conn.execute("BEGIN IMMEDIATE")
    try:
        rows = conn.execute(
            "SELECT id, portfolio_name, symbol, added_at FROM pending_addition WHERE consumed_at IS NULL"
        ).fetchall()
        if rows:
            conn.execute(
                "UPDATE pending_addition SET consumed_at = ? WHERE consumed_at IS NULL",
                (now,),
            )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    return [
        {"portfolio": row["portfolio_name"], "symbol": row["symbol"], "added_at": row["added_at"]}
        for row in rows
    ]


def peek_pending_additions() -> list[dict[str, Any]]:
    """Return pending additions without consuming them."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT portfolio_name, symbol, added_at FROM pending_addition WHERE consumed_at IS NULL"
    ).fetchall()
    return [
        {"portfolio": row["portfolio_name"], "symbol": row["symbol"], "added_at": row["added_at"]}
        for row in rows
    ]


def forget_pending_addition(portfolio_name: str, symbol: str) -> None:
    """Remove a queued addition so the next scheduled run doesn't report it."""
    conn = get_connection()
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    conn.execute(
        """UPDATE pending_addition SET consumed_at = ?
           WHERE portfolio_name = ? AND symbol = ? AND consumed_at IS NULL""",
        (now, portfolio_name, symbol),
    )
