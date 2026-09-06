"""yfinance access layer.

Every network call is wrapped so a single bad ticker (invalid symbol, delisted
stock, timeout) never aborts a portfolio refresh.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from datetime import datetime
from .errors import DataFetchError
from .db.repositories import quotes as _quotes_repo

logger = logging.getLogger(__name__)


def load_quotes_cache() -> dict[str, dict[str, Any]]:
    return _quotes_repo.load_quotes_cache()


def save_quote_to_cache(symbol: str, quote: dict[str, Any]) -> None:
    _quotes_repo.save_quote(symbol, quote)


def fetch_ticker_quote(symbol: str) -> dict[str, Any]:
    """Fetch live quote for a symbol with strictly max 2 total attempts and persistent caching."""
    live_price = None
    currency = "INR"
    name = ""

    # Attempt 1: Fast live price
    try:
        live_price, cur, nm = fetch_live_price(symbol)
        if cur:
            currency = cur
        if nm:
            name = nm
    except Exception as exc:
        logger.info("Attempt 1 failed for %s: %s", symbol, exc)

    # Attempt 2: Fallback to last close from daily history if live price was not found
    if live_price is None or live_price <= 0:
        try:
            daily = fetch_daily_history(symbol, period="5d", retries=1)
            if not daily.empty and "Close" in daily.columns:
                live_price = float(daily["Close"].iloc[-1])
        except Exception as exc:
            logger.info("Attempt 2 (daily close fallback) failed for %s: %s", symbol, exc)

    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M")

    # If fetch succeeded:
    if live_price is not None and live_price > 0:
        quote = {
            "symbol": symbol,
            "name": name or symbol,
            "price": round(live_price, 2),
            "currency": currency or "INR",
            "as_of": now_iso,
            "is_cached": False,
        }
        try:
            save_quote_to_cache(symbol, quote)
        except Exception as exc:
            logger.warning("Could not save quote to cache: %s", exc)
        return quote

    # If fetch failed: Check cached quotes
    cache = load_quotes_cache()
    if symbol in cache and cache[symbol].get("price") is not None:
        cached = dict(cache[symbol])
        cached["is_cached"] = True
        logger.info("Using cached quote for %s: %s", symbol, cached)
        return cached

    raise DataFetchError(symbol, f"Could not fetch price for {symbol}.")


@dataclass
class TickerData:
    """Normalised market data for one ticker."""

    symbol: str
    name: str
    price: float | None
    currency: str
    as_of: str | None
    daily: pd.DataFrame
    weekly: pd.DataFrame = field(default_factory=pd.DataFrame)
    notes: list[str] = field(default_factory=list)


def _import_yfinance():
    try:
        import yfinance as yf  # imported lazily so unit tests can run offline
    except ImportError as exc:  # pragma: no cover - environment issue
        raise DataFetchError("yfinance", f"yfinance is not installed ({exc}).") from exc
    return yf


def fetch_daily_history(
    symbol: str,
    period: str = "10y",
    retries: int = 2,
    backoff_seconds: float = 1.5,
) -> pd.DataFrame:
    """Download the daily OHLCV history for ``symbol``.

    Raises:
        DataFetchError: when the download fails or returns no rows.
    """
    yf = _import_yfinance()
    last_error: str = "unknown error"

    for attempt in range(1, max(1, retries) + 1):
        try:
            frame = yf.Ticker(symbol).history(
                period=period, interval="1d", auto_adjust=False, raise_errors=False
            )
        except Exception as exc:  # yfinance raises a wide variety of exceptions
            last_error = f"{type(exc).__name__}: {exc}"
            logger.warning("Fetch attempt %s/%s failed for %s - %s", attempt, retries, symbol, last_error)
        else:
            if frame is not None and not frame.empty and "Close" in frame.columns:
                frame = frame.dropna(subset=["Close"])
                if not frame.empty:
                    if not isinstance(frame.index, pd.DatetimeIndex):
                        frame.index = pd.to_datetime(frame.index, errors="coerce")
                        frame = frame[frame.index.notna()]
                    return frame.sort_index()
            last_error = "no price rows returned (unknown or delisted symbol?)"
            logger.warning("Fetch attempt %s/%s returned no data for %s", attempt, retries, symbol)

        if attempt < retries:
            time.sleep(backoff_seconds * attempt)

    raise DataFetchError(symbol, last_error)


def fetch_live_price(symbol: str) -> tuple[float | None, str | None, str]:
    """Best-effort live price, currency, and company name.

    Returns ``(price, currency, name)``; any element may be ``None`` / empty on
    failure.
    """
    yf = _import_yfinance()
    price = None
    currency = None
    name = ""
    try:
        ticker = yf.Ticker(symbol)
        fast_info: Any = ticker.fast_info
        for key in ("last_price", "lastPrice"):
            try:
                price = fast_info[key]
            except (KeyError, TypeError, AttributeError):
                price = getattr(fast_info, key, None) if price is None else price
            if price is not None:
                break
        try:
            currency = fast_info["currency"]
        except (KeyError, TypeError, AttributeError):
            currency = getattr(fast_info, "currency", None)
        # Best-effort company name from the full info dict.
        try:
            info = ticker.info
            name = info.get("longName") or info.get("shortName") or ""
        except Exception:
            pass
    except Exception as exc:
        logger.info("Live quote unavailable for %s (%s) - falling back to last close", symbol, exc)
    return (float(price) if price is not None else None, currency, name)


# Minimum daily bars before we try the alternate exchange (.NS ↔ .BO).
# 400 ≈ 200 EMA × 2, i.e. enough for a reliable 200-period EMA.
AUTO_SWITCH_MIN_BARS = 400

_EXCHANGE_PAIRS = {".NS": ".BO", ".BO": ".NS"}


def _alternate_symbol(symbol: str) -> str | None:
    """Return the same ticker on the other exchange, or *None* if not applicable."""
    for suffix, alt_suffix in _EXCHANGE_PAIRS.items():
        if symbol.endswith(suffix):
            return symbol[: -len(suffix)] + alt_suffix
    return None


def get_ticker_data(
    symbol: str,
    period: str = "10y",
    retries: int = 2,
    backoff_seconds: float = 1.5,
) -> TickerData:
    """Fetch history + live price and return a :class:`TickerData` bundle.

    If the primary exchange provides fewer than :data:`AUTO_SWITCH_MIN_BARS`
    daily bars, the alternate exchange (``.NS`` ↔ ``.BO``) is tried
    automatically.  Whichever exchange supplies more history is used.
    """
    from .ema import resample_weekly  # local import keeps module import order simple

    daily = fetch_daily_history(symbol, period=period, retries=retries, backoff_seconds=backoff_seconds)
    notes: list[str] = []

    # --- auto-switch: try the other exchange if history is thin ---------------
    fetch_symbol = symbol  # symbol actually used for live price / notes
    alt_symbol = _alternate_symbol(symbol)
    if alt_symbol and len(daily) < AUTO_SWITCH_MIN_BARS:
        try:
            alt_daily = fetch_daily_history(
                alt_symbol, period=period, retries=retries, backoff_seconds=backoff_seconds
            )
            if len(alt_daily) > len(daily):
                logger.info(
                    "Switching %s → %s (%s bars vs %s)",
                    symbol, alt_symbol, len(alt_daily), len(daily),
                )
                daily = alt_daily
                fetch_symbol = alt_symbol
                notes.append(
                    f"Using {alt_symbol} data ({len(alt_daily)} bars) — "
                    f"more history than {symbol} ({len(daily)})."
                )
        except DataFetchError:
            logger.info("Alternate symbol %s not available, keeping %s", alt_symbol, symbol)

    last_close = float(daily["Close"].iloc[-1])
    live_price, currency, stock_name = fetch_live_price(fetch_symbol)

    price = live_price if live_price and live_price > 0 else last_close
    if live_price is None:
        notes.append("Live quote unavailable; using the latest available close.")

    # Keep the forming candle in sync with the live price so "current" EMAs match
    # what an intraday chart shows.
    if live_price and live_price > 0:
        today = pd.Timestamp.now(tz=daily.index.tz) if daily.index.tz is not None else pd.Timestamp.now()
        if daily.index[-1].date() == today.date():
            daily.iloc[-1, daily.columns.get_loc("Close")] = live_price

    weekly = resample_weekly(daily)
    if weekly.empty:
        notes.append("Weekly candles could not be derived from the daily history.")

    as_of = daily.index[-1].isoformat()
    return TickerData(
        symbol=symbol,
        name=stock_name,
        price=price,
        currency=currency or "INR",
        as_of=as_of,
        daily=daily,
        weekly=weekly,
        notes=notes,
    )


def symbol_exists(symbol: str) -> bool:
    """Cheap existence probe used when a ticker is added through the UI."""
    try:
        fetch_daily_history(symbol, period="1mo", retries=1)
        return True
    except DataFetchError:
        return False
