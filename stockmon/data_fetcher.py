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
    """Fetch live quote for a symbol with alternate exchange fallback and persistent caching."""
    live_price = None
    currency = "INR"
    name = ""
    actual_symbol = symbol

    def _attempt_fetch(sym: str) -> tuple[float | None, str | None, str]:
        lp, cur, nm = None, None, ""
        try:
            lp, cur, nm = fetch_live_price(sym)
        except Exception as exc:
            logger.info("Live price attempt failed for %s: %s", sym, exc)
        if lp is None or lp <= 0:
            try:
                daily = fetch_daily_history(sym, period="5d", retries=1)
                if not daily.empty and "Close" in daily.columns:
                    lp = float(daily["Close"].iloc[-1])
            except Exception as exc:
                logger.info("Daily close fallback failed for %s: %s", sym, exc)
        return lp, cur, nm

    live_price, cur, nm = _attempt_fetch(symbol)
    if cur:
        currency = cur
    if nm:
        name = nm

    # If primary exchange failed, try alternate exchange (.NS ↔ .BO)
    alt_symbol = _alternate_symbol(symbol)
    if (live_price is None or live_price <= 0) and alt_symbol:
        logger.info("Primary quote fetch failed for %s; trying alternate %s", symbol, alt_symbol)
        alt_lp, alt_cur, alt_nm = _attempt_fetch(alt_symbol)
        if alt_lp is not None and alt_lp > 0:
            live_price = alt_lp
            actual_symbol = alt_symbol
            if alt_cur:
                currency = alt_cur
            if alt_nm:
                name = alt_nm

    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M")

    # If fetch succeeded:
    if live_price is not None and live_price > 0:
        quote = {
            "symbol": actual_symbol,
            "requested_symbol": symbol,
            "name": name or actual_symbol,
            "price": round(live_price, 2),
            "currency": currency or "INR",
            "as_of": now_iso,
            "is_cached": False,
        }
        try:
            save_quote_to_cache(symbol, quote)
            if actual_symbol != symbol:
                save_quote_to_cache(actual_symbol, quote)
            if "." in actual_symbol:
                save_quote_to_cache(actual_symbol.split(".")[0], quote)
        except Exception as exc:
            logger.warning("Could not save quote to cache: %s", exc)
        return quote

    # If fetch failed: Check cached quotes
    cache = load_quotes_cache()
    for s in (symbol, alt_symbol, symbol.split(".")[0] if "." in symbol else None):
        if s and s in cache and cache[s].get("price") is not None:
            cached = dict(cache[s])
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
    fetch_symbol: str = ""


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
    if "." not in symbol and not symbol.startswith("^"):
        return f"{symbol}.BO"
    return None


def get_ticker_data(
    symbol: str,
    period: str = "10y",
    retries: int = 2,
    backoff_seconds: float = 1.5,
) -> TickerData:
    """Fetch history + live price and return a :class:`TickerData` bundle.

    If the primary exchange fails (e.g. .NS has no data or is delisted) or provides fewer than
    :data:`AUTO_SWITCH_MIN_BARS` daily bars, the alternate exchange (.NS ↔ .BO) is tried
    automatically. Whichever exchange supplies valid/more history is used.
    """
    from .ema import resample_weekly  # local import keeps module import order simple

    fetch_symbol = symbol
    alt_symbol = _alternate_symbol(symbol)
    notes: list[str] = []
    daily = None

    try:
        daily = fetch_daily_history(symbol, period=period, retries=retries, backoff_seconds=backoff_seconds)
    except DataFetchError as exc:
        if alt_symbol:
            logger.info(
                "Primary exchange failed for %s (%s); trying alternate exchange %s",
                symbol, exc.message, alt_symbol,
            )
            try:
                daily = fetch_daily_history(
                    alt_symbol, period=period, retries=retries, backoff_seconds=backoff_seconds
                )
                fetch_symbol = alt_symbol
                notes.append(
                    f"Symbol {symbol} not available on primary exchange; using {alt_symbol} data."
                )
            except DataFetchError:
                raise exc
        else:
            raise

    # --- auto-switch: try the other exchange if history is thin (< AUTO_SWITCH_MIN_BARS) ---
    if alt_symbol and fetch_symbol == symbol and len(daily) < AUTO_SWITCH_MIN_BARS:
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
        fetch_symbol=fetch_symbol,
    )


def symbol_exists(symbol: str) -> bool:
    """Cheap existence probe used when a ticker is added through the UI."""
    try:
        fetch_daily_history(symbol, period="1mo", retries=1)
        return True
    except DataFetchError:
        alt = _alternate_symbol(symbol)
        if alt:
            try:
                fetch_daily_history(alt, period="1mo", retries=1)
                return True
            except DataFetchError:
                return False
        return False
