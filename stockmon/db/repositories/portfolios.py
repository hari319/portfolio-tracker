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


def load_tracker_portfolios_meta(
    names: tuple[str, ...] = ("BAPA", "MADI"),
) -> dict[str, dict[str, dict[str, Any]]]:
    """Return enriched portfolio ticker metadata for Tracker tab tables.

    Returns ``{portfolio_name: {symbol: {
        'symbol': symbol,
        'stock_name': str,
        'avg_price': float | None,
        'is_sourced': bool,
        'is_manual': bool,
        'total_qty': float
    }}}``.

    For MADI:
      Sourced from:
        - Portfolio Tracker 'MADI' open holdings (status = 'open')
        - Portfolio Tracker 'LOAN' open holdings where person is 'MADI'
      Plus manual tickers in ``portfolio_ticker`` for 'MADI'.

    For BAPA:
      Sourced from:
        - Portfolio Tracker 'BAPA' open holdings (status = 'open')
        - Portfolio Tracker 'LOAN' open holdings where person is 'BAPA'
      Plus manual tickers in ``portfolio_ticker`` for 'BAPA'.

    If the same ticker exists in both personal and loan, computes the combined
    weighted average purchase price across all open lots.
    """
    from ...portfolio import normalize_symbol

    conn = get_connection()
    result: dict[str, dict[str, dict[str, Any]]] = {}

    for name in names:
        ensure_portfolio(name)
        port_key = name.strip().upper()

        # 1. Fetch open holdings from Portfolio Tracker for this portfolio:
        #    - h.portfolio_name == port_key
        #    - OR (h.portfolio_name == 'LOAN' AND h.person == port_key)
        holding_query = """
            SELECT
                h.id,
                h.portfolio_name,
                h.symbol,
                COALESCE(h.stock_name, h.scheme_name, '') AS stock_name,
                h.person,
                COALESCE(SUM(b.quantity), 0.0) AS total_qty,
                COALESCE(SUM(COALESCE(b.invested_amount, b.quantity * b.avg_price)), 0.0) AS total_invested
            FROM holding h
            LEFT JOIN buy_lot b ON b.holding_id = h.id
            WHERE h.status = 'open'
              AND (
                  h.portfolio_name = ?
                  OR (h.portfolio_name = 'LOAN' AND UPPER(TRIM(COALESCE(h.person, ''))) = ?)
              )
            GROUP BY h.id
        """
        holding_rows = conn.execute(holding_query, (port_key, port_key)).fetchall()

        aggregated: dict[str, dict[str, Any]] = {}
        for row in holding_rows:
            raw_sym = (row["symbol"] or "").strip()
            if not raw_sym:
                continue
            try:
                norm_sym = normalize_symbol(raw_sym)
            except Exception:
                norm_sym = raw_sym.upper()

            qty = float(row["total_qty"] or 0.0)
            invested = float(row["total_invested"] or 0.0)
            stock_name = (row["stock_name"] or "").strip()

            if norm_sym not in aggregated:
                aggregated[norm_sym] = {
                    "symbol": norm_sym,
                    "stock_name": stock_name,
                    "total_qty": qty,
                    "total_invested": invested,
                }
            else:
                aggregated[norm_sym]["total_qty"] += qty
                aggregated[norm_sym]["total_invested"] += invested
                if not aggregated[norm_sym]["stock_name"] and stock_name:
                    aggregated[norm_sym]["stock_name"] = stock_name

        # Calculate weighted average and mark as sourced
        meta_by_symbol: dict[str, dict[str, Any]] = {}
        for norm_sym, data in aggregated.items():
            t_qty = data["total_qty"]
            t_inv = data["total_invested"]
            # Only include if open quantity > 0 (position is not sold out)
            if t_qty <= 0:
                continue
            avg_p = round(t_inv / t_qty, 2) if t_qty > 0 else 0.0
            meta_by_symbol[norm_sym] = {
                "symbol": norm_sym,
                "stock_name": data["stock_name"],
                "avg_price": avg_p,
                "is_sourced": True,
                "is_manual": False,
                "total_qty": t_qty,
            }

        # 2. Fetch manual additions from portfolio_ticker
        manual_rows = conn.execute(
            "SELECT symbol FROM portfolio_ticker WHERE portfolio_name = ? ORDER BY added_at",
            (name,),
        ).fetchall()

        for m_row in manual_rows:
            raw_sym = (m_row["symbol"] or "").strip()
            if not raw_sym:
                continue
            try:
                norm_sym = normalize_symbol(raw_sym)
            except Exception:
                norm_sym = raw_sym.upper()

            if norm_sym in meta_by_symbol:
                # Exists in both Portfolio Tracker and manual table
                meta_by_symbol[norm_sym]["is_manual"] = True
            else:
                # Purely manual ticker
                meta_by_symbol[norm_sym] = {
                    "symbol": norm_sym,
                    "stock_name": "",
                    "avg_price": None,
                    "is_sourced": False,
                    "is_manual": True,
                    "total_qty": 0.0,
                }

        result[name] = meta_by_symbol

    return result


def get_all_portfolio_tracker_symbols() -> list[str]:
    """Return all unique symbols currently held in open holdings across all portfolios (MADI, BAPA, LOAN)."""
    from ...portfolio import normalize_symbol

    conn = get_connection()
    rows = conn.execute("SELECT DISTINCT symbol FROM holding WHERE status = 'open'").fetchall()
    symbols = set()
    for row in rows:
        raw_sym = (row["symbol"] or "").strip()
        if not raw_sym:
            continue
        try:
            symbols.add(normalize_symbol(raw_sym))
        except Exception:
            symbols.add(raw_sym.upper())
    return sorted(symbols)


def load_portfolios(names: tuple[str, ...] = ("BAPA", "MADI")) -> dict[str, list[str]]:
    """Return portfolios as ``{name: [symbol, ...]}``, including sourced tickers from Portfolio Tracker."""
    meta = load_tracker_portfolios_meta(names)
    return {name: list(symbols.keys()) for name, symbols in meta.items()}


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
