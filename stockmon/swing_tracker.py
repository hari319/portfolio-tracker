"""Business logic and services for the Swing Tracker tab.

Handles ticker normalization, range parsing, percentage distance calculations,
price resolution (portfolio table check first, otherwise fetch), and batch refresh.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from .data_fetcher import fetch_ticker_quote
from .db.repositories import swing_tracker as _repo
from .errors import ValidationError
from .portfolio import normalize_symbol
from .service import load_snapshot

logger = logging.getLogger(__name__)

# Regex pattern to extract two numbers from a range like "100-105", "100 - 105", "100 to 105"
_RANGE_PATTERN = re.compile(
    r"^\s*([0-9]+(?:[.,][0-9]+)?)\s*(?:-|–|—|to)\s*([0-9]+(?:[.,][0-9]+)?)\s*$",
    re.IGNORECASE,
)
# Single number pattern
_SINGLE_NUM_PATTERN = re.compile(r"^\s*([0-9]+(?:[.,][0-9]+)?)\s*$")


def parse_range_or_number(
    val: str | int | float | None,
) -> tuple[float | None, bool, float | None, float | None]:
    """Parse a string/number that could be a single value or a range (e.g. '100-105').

    Returns:
        (average_value, is_range, low, high)
        All numbers are None if parsing fails or input is empty.
    """
    if val is None:
        return (None, False, None, None)

    if isinstance(val, (int, float)):
        f = float(val)
        return (f, False, f, f)

    cleaned = str(val).strip().replace("₹", "").replace("$", "").replace(",", "")
    if not cleaned:
        return (None, False, None, None)

    # 1. Try range match
    range_match = _RANGE_PATTERN.match(cleaned)
    if range_match:
        try:
            n1 = float(range_match.group(1))
            n2 = float(range_match.group(2))
            low = min(n1, n2)
            high = max(n1, n2)
            avg = round((low + high) / 2.0, 4)
            return (avg, True, low, high)
        except (ValueError, TypeError):
            pass

    # 2. Try single number match
    single_match = _SINGLE_NUM_PATTERN.match(cleaned)
    if single_match:
        try:
            n = float(single_match.group(1))
            return (n, False, n, n)
        except (ValueError, TypeError):
            pass

    return (None, False, None, None)


def calculate_distance_pct(
    current_price: float | int | None,
    target_val: str | int | float | None,
) -> float | None:
    """Calculate percentage distance from Current Price to Target/Zone/SL value.

    Formula: ((value - current_price) / current_price) * 100.0
    If target_val is a range (e.g. '100-105'), uses the average of the range.
    """
    if current_price is None:
        return None
    try:
        cp = float(current_price)
        if cp <= 0:
            return None
    except (ValueError, TypeError):
        return None

    avg_val, _, _, _ = parse_range_or_number(target_val)
    if avg_val is None:
        return None

    return round(((avg_val - cp) / cp) * 100.0, 2)


def check_portfolio_table_price(symbol: str) -> float | None:
    """Check if ticker already exists in the Portfolio tables with a current price.

    Inspects active portfolio tables (BAPA, MADI) from the latest snapshot.
    Returns float price if found and > 0, else None.
    """
    try:
        norm_sym = normalize_symbol(symbol)
    except Exception:
        norm_sym = str(symbol or "").strip().upper()

    base_sym = norm_sym.replace(".NS", "").replace(".BO", "")

    try:
        snapshot = load_snapshot()
        portfolios = snapshot.get("portfolios", {})
        for _, pdata in portfolios.items():
            rows = pdata.get("rows", [])
            for r in rows:
                r_sym = str(r.get("symbol") or "").strip().upper()
                r_disp = str(r.get("display") or "").strip().upper()
                r_base = r_sym.replace(".NS", "").replace(".BO", "")

                if norm_sym in (r_sym, r_disp) or base_sym == r_base:
                    price = r.get("price")
                    if price is not None:
                        try:
                            fp = float(price)
                            if fp > 0:
                                return fp
                        except (ValueError, TypeError):
                            pass
    except Exception as exc:
        logger.debug("Error checking portfolio table for %s: %s", symbol, exc)

    return None


def resolve_ticker_price(symbol: str) -> tuple[float | None, str]:
    """Check Portfolio table first for current price; if found, reuse it.

    Otherwise fetch quote.
    Returns:
        (price, source_label) where source_label is 'portfolio' | 'live' | 'failed'
    """
    try:
        norm_sym = normalize_symbol(symbol)
    except Exception as exc:
        raise ValidationError(f"Invalid ticker symbol: {symbol}") from exc

    # 1. Check if the ticker already exists in the Portfolio table with a current price
    cached_price = check_portfolio_table_price(norm_sym)
    if cached_price is not None and cached_price > 0:
        logger.info("Reusing existing Portfolio table price for %s: %s", norm_sym, cached_price)
        return (round(cached_price, 2), "portfolio")

    # 2. Otherwise fetch it
    try:
        quote = fetch_ticker_quote(norm_sym)
        if quote and quote.get("price") is not None and float(quote["price"]) > 0:
            return (round(float(quote["price"]), 2), "live")
    except Exception as exc:
        logger.warning("Quote fetch failed for %s: %s", norm_sym, exc)

    return (None, "failed")


def load_swing_trades() -> dict[str, Any]:
    """Return all swing trades enriched with calculated distance percentages and all sources."""
    trades = _repo.list_trades()
    sources = _repo.list_sources()

    enriched_trades = []
    for t in trades:
        cp = t.get("current_price")
        item = dict(t)
        item["buy_zone_dist_pct"] = calculate_distance_pct(cp, t.get("buy_zone"))
        item["stop_loss_dist_pct"] = calculate_distance_pct(cp, t.get("stop_loss"))
        item["target1_dist_pct"] = calculate_distance_pct(cp, t.get("target1"))
        item["target2_dist_pct"] = calculate_distance_pct(cp, t.get("target2"))

        # Range averages for convenient frontend rendering
        item["buy_zone_avg"] = parse_range_or_number(t.get("buy_zone"))[0]
        item["stop_loss_avg"] = parse_range_or_number(t.get("stop_loss"))[0]
        item["target1_avg"] = parse_range_or_number(t.get("target1"))[0]
        item["target2_avg"] = parse_range_or_number(t.get("target2"))[0]

        enriched_trades.append(item)

    return {
        "trades": enriched_trades,
        "sources": sources,
    }


def add_swing_trade(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate, resolve price if needed, and insert a new swing trade."""
    raw_sym = str(payload.get("symbol") or "").strip()
    if not raw_sym:
        raise ValidationError("Ticker symbol is required.")

    symbol = normalize_symbol(raw_sym)
    trade_date = str(payload.get("date") or "").strip() or datetime.now().strftime("%Y-%m-%d")

    current_price = payload.get("current_price")
    if current_price is None or str(current_price).strip() == "":
        resolved_price, _ = resolve_ticker_price(symbol)
        current_price = resolved_price
    else:
        try:
            current_price = float(current_price)
        except (ValueError, TypeError):
            resolved_price, _ = resolve_ticker_price(symbol)
            current_price = resolved_price

    trade_data = {
        "symbol": symbol,
        "date": trade_date,
        "current_price": current_price,
        "current_price_updated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "buy_zone": payload.get("buy_zone"),
        "stop_loss": payload.get("stop_loss"),
        "target1": payload.get("target1"),
        "target2": payload.get("target2"),
        "pattern_break": payload.get("pattern_break"),
        "thesis": payload.get("thesis"),
        "trade_source": payload.get("trade_source"),
    }

    return _repo.add_trade(trade_data)


def update_swing_trade(trade_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and update a swing trade."""
    existing = _repo.get_trade(trade_id)
    if not existing:
        raise ValidationError(f"Swing trade #{trade_id} not found.")

    raw_sym = str(payload.get("symbol") or existing["symbol"]).strip()
    symbol = normalize_symbol(raw_sym)

    current_price = payload.get("current_price", existing["current_price"])
    if current_price is not None and str(current_price).strip() != "":
        try:
            current_price = float(current_price)
        except (ValueError, TypeError):
            current_price = existing["current_price"]
    else:
        current_price = None

    update_data = {
        "symbol": symbol,
        "date": str(payload.get("date") or existing["date"]).strip(),
        "current_price": current_price,
        "buy_zone": payload.get("buy_zone", existing["buy_zone"]),
        "stop_loss": payload.get("stop_loss", existing["stop_loss"]),
        "target1": payload.get("target1", existing["target1"]),
        "target2": payload.get("target2", existing["target2"]),
        "pattern_break": payload.get("pattern_break", existing["pattern_break"]),
        "thesis": payload.get("thesis", existing["thesis"]),
        "trade_source": payload.get("trade_source", existing["trade_source"]),
    }

    updated = _repo.update_trade(trade_id, update_data)
    if not updated:
        raise ValidationError(f"Could not update swing trade #{trade_id}.")
    return updated


def delete_swing_trade(trade_id: int) -> bool:
    """Delete a swing trade by id."""
    return _repo.delete_trade(trade_id)


def refresh_swing_trade_price(trade_id: int) -> dict[str, Any]:
    """Refresh the current price for a specific swing trade."""
    trade = _repo.get_trade(trade_id)
    if not trade:
        raise ValidationError(f"Swing trade #{trade_id} not found.")

    symbol = trade["symbol"]
    # Check portfolio first, then fetch
    price, _ = resolve_ticker_price(symbol)
    now_iso = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    if price is not None and price > 0:
        _repo.update_trade_price(trade_id, price, now_iso)
        trade = _repo.get_trade(trade_id) or trade

    return trade


def refresh_all_swing_trade_prices() -> dict[str, Any]:
    """Auto-refresh current prices for all swing trades.

    Called during scheduled runs at 9:30 AM (and manual triggers).
    Reuses portfolio table prices first, otherwise fetches.
    """
    trades = _repo.list_trades()
    if not trades:
        return {"total": 0, "updated": 0, "failed": 0}

    unique_symbols = sorted({t["symbol"] for t in trades if t.get("symbol")})
    resolved_prices: dict[str, float | None] = {}

    for sym in unique_symbols:
        price, _ = resolve_ticker_price(sym)
        resolved_prices[sym] = price

    now_iso = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    updated_count = 0
    failed_count = 0

    for t in trades:
        trade_id = t["id"]
        sym = t["symbol"]
        price = resolved_prices.get(sym)
        if price is not None and price > 0:
            _repo.update_trade_price(trade_id, price, now_iso)
            updated_count += 1
        else:
            failed_count += 1

    logger.info(
        "Swing trades price refresh complete: %s updated, %s failed, %s total",
        updated_count,
        failed_count,
        len(trades),
    )
    return {"total": len(trades), "updated": updated_count, "failed": failed_count}
