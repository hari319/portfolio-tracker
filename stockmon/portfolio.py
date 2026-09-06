"""Portfolio membership: validation, persistence and TradingView links.

Persistence now uses SQLite via ``stockmon.db.repositories.portfolios``.
The ``config/portfolios.json`` file is no longer the source of truth —
portfolios live in the ``portfolio`` and ``portfolio_ticker`` tables.

Public API is unchanged so routes.py and scheduled_run.py need no modification.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from .config_manager import load_settings
from .errors import ValidationError
from .db.repositories import portfolios as _repo
from .logging_config import get_additions_logger

logger = logging.getLogger(__name__)

PORTFOLIO_NAMES = ("BAPA", "MADI")

DEFAULT_PORTFOLIOS: dict[str, list[str]] = {
    "BAPA": ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS"],
    "MADI": ["INFY.NS", "ITC.NS", "CARTRADE.NS"],
}

# NSE/BSE tickers such as M&M.NS, BAJAJ-AUTO.NS, 500325.BO or the index ^NSEI.
SYMBOL_PATTERN = re.compile(r"^\^?[A-Z0-9][A-Z0-9&\-_]{0,19}(\.(NS|BO))?$")

EXCHANGE_BY_SUFFIX = {".NS": "NSE", ".BO": "BSE"}


def normalize_symbol(raw: str) -> str:
    """Upper-case a ticker and append the default exchange suffix if missing."""
    if raw is None:
        raise ValidationError("Ticker symbol is required.")
    symbol = str(raw).strip().upper().replace(" ", "")
    if not symbol:
        raise ValidationError("Ticker symbol is required.")
    if not SYMBOL_PATTERN.match(symbol):
        raise ValidationError(
            f"'{symbol}' is not a valid ticker. Use letters/digits, e.g. RELIANCE or RELIANCE.NS."
        )
    if not symbol.startswith("^") and "." not in symbol:
        suffix = load_settings()["data"].get("default_exchange_suffix", ".NS")
        symbol = f"{symbol}{suffix}"
    return symbol


def validate_portfolio(name: str) -> str:
    portfolio = str(name or "").strip().upper()
    if portfolio not in PORTFOLIO_NAMES:
        raise ValidationError(
            f"Unknown portfolio '{name}'. Expected one of: {', '.join(PORTFOLIO_NAMES)}."
        )
    return portfolio


def display_name(symbol: str) -> str:
    """Ticker without the exchange suffix, for table display."""
    for suffix in EXCHANGE_BY_SUFFIX:
        if symbol.endswith(suffix):
            return symbol[: -len(suffix)]
    return symbol


def tradingview_url(symbol: str) -> str:
    """Chart URL for the ticker on TradingView."""
    base = display_name(symbol).lstrip("^")
    exchange = next(
        (name for suffix, name in EXCHANGE_BY_SUFFIX.items() if symbol.endswith(suffix)),
        "NSE",
    )
    return f"https://www.tradingview.com/chart/?symbol={quote(f'{exchange}:{base}')}"


def load_portfolios() -> dict[str, list[str]]:
    """Return both portfolios, seeding defaults if empty.

    Now reads from the ``portfolio_ticker`` table instead of a JSON file.
    """
    result = _repo.load_portfolios(PORTFOLIO_NAMES)

    # If both portfolios are empty (first run before migration), seed defaults
    if all(len(v) == 0 for v in result.values()):
        # Check if this is truly empty or just no tickers yet
        from .db import get_connection
        conn = get_connection()
        count = conn.execute("SELECT COUNT(*) FROM portfolio_ticker").fetchone()[0]
        if count == 0:
            logger.info("No portfolio tickers found, checking for portfolios.json fallback")
            # Don't auto-seed — the migration script handles this
            pass

    return result


def save_portfolios(portfolios: dict[str, list[str]]) -> None:
    _repo.save_portfolios(portfolios)


def add_ticker(portfolio_name: str, raw_symbol: str) -> str:
    """Validate and append a ticker. Raises :class:`ValidationError` on duplicates."""
    portfolio = validate_portfolio(portfolio_name)
    symbol = normalize_symbol(raw_symbol)

    if _repo.ticker_exists(portfolio, symbol):
        raise ValidationError(f"{symbol} is already in the {portfolio} portfolio.")

    _repo.add_ticker(portfolio, symbol)
    logger.info("Added %s to %s", symbol, portfolio)
    return symbol


def remove_ticker(portfolio_name: str, raw_symbol: str) -> str:
    portfolio = validate_portfolio(portfolio_name)
    symbol = normalize_symbol(raw_symbol)

    if not _repo.ticker_exists(portfolio, symbol):
        raise ValidationError(f"{symbol} is not in the {portfolio} portfolio.")

    _repo.remove_ticker(portfolio, symbol)
    _repo.forget_pending_addition(portfolio, symbol)
    logger.info("Removed %s from %s", symbol, portfolio)
    return symbol


def record_addition(portfolio_name: str, symbol: str) -> None:
    """Log an addition so the next scheduled run can report what it picked up."""
    _repo.record_pending_addition(portfolio_name, symbol)
    get_additions_logger().info("ADDED %s to %s", symbol, portfolio_name)


def consume_pending_additions() -> list[dict[str, Any]]:
    """Return and clear the tickers added since the previous scheduled run.

    Now uses BEGIN IMMEDIATE to prevent the §1.5 lost-update race.
    """
    return _repo.consume_pending_additions()


def peek_pending_additions() -> list[dict[str, Any]]:
    return _repo.peek_pending_additions()
