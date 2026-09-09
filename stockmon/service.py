"""Orchestration layer: fetch -> compute EMAs -> snapshot -> publish status."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from . import status as status_store
from .config_manager import load_settings
from .data_fetcher import get_ticker_data
from .ema import build_ema_matrix
from .errors import DataFetchError
from .db.repositories import snapshots as _snap_repo
from .portfolio import (
    PORTFOLIO_NAMES,
    display_name,
    load_portfolios,
    load_tracker_portfolios_meta,
    get_all_portfolio_tracker_symbols,
    tradingview_url,
)

logger = logging.getLogger(__name__)


def empty_snapshot(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = settings or load_settings()
    return {
        "generated_at": None,
        "source": None,
        "ema_periods": list(settings["data"]["ema_periods"]),
        "portfolios": {name: {"rows": []} for name in PORTFOLIO_NAMES},
        "stats": {"total": 0, "ok": 0, "failed": 0},
        "errors": [],
    }


def load_snapshot() -> dict[str, Any]:
    """Return the last persisted snapshot, or an empty one."""
    snapshot = _snap_repo.load_latest_snapshot()
    if not isinstance(snapshot, dict) or "portfolios" not in snapshot:
        return empty_snapshot()
    for name in PORTFOLIO_NAMES:
        snapshot["portfolios"].setdefault(name, {"rows": []})
    snapshot.setdefault("errors", [])
    snapshot.setdefault("stats", {"total": 0, "ok": 0, "failed": 0})
    return snapshot


def save_snapshot(snapshot: dict[str, Any]) -> None:
    _snap_repo.save_snapshot(snapshot)


def compute_cost_risk(price: float | None, avg_price: float | None) -> tuple[float | None, str | None]:
    """Calculate cost drawdown percentage and risk tier against average purchase price.

    Tiers:
    - mild: 0.01% to 4.99% below avg price (drawdown in (-5.0, 0))
    - moderate (stop-loss zone): 5.00% to 9.99% below avg price (drawdown in (-10.0, -5.0])
    - critical: 10.00% or more below avg price (drawdown <= -10.0)
    - None: at or above cost basis (drawdown >= 0), or missing price / avg_price.
    """
    if price is None or avg_price is None or avg_price <= 0:
        return None, None

    drawdown_pct = round(((price - avg_price) / avg_price) * 100.0, 2)
    if drawdown_pct >= 0:
        return drawdown_pct, None

    if drawdown_pct > -5.0:
        return drawdown_pct, "mild"
    elif drawdown_pct > -10.0:
        return drawdown_pct, "moderate"
    else:
        return drawdown_pct, "critical"


def build_row(symbol: str, settings: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fetch one ticker and build its table row. Never raises."""
    settings = settings or load_settings()
    data_cfg = settings["data"]
    decimals = int(settings["ui"].get("price_decimals", 2))

    row: dict[str, Any] = {
        "symbol": symbol,
        "display": display_name(symbol),
        "name": "",
        "avg_price": None,
        "cost_drawdown_pct": None,
        "risk_tier": None,
        "is_sourced": False,
        "is_manual": True,
        "url": tradingview_url(symbol),
        "price": None,
        "price_display": "",
        "signal": "Hold",
        "currency": "INR",
        "as_of": None,
        "error": None,
        "notes": [],
        "emas": {str(period): _blank_cell() for period in data_cfg["ema_periods"]},
    }

    try:
        data = get_ticker_data(
            symbol,
            period=str(data_cfg.get("history_period", "10y")),
            retries=int(data_cfg.get("retries", 2)),
            backoff_seconds=float(data_cfg.get("retry_backoff_seconds", 1.5)),
        )
    except DataFetchError as exc:
        logger.error("Skipping %s - %s", symbol, exc.message)
        row["error"] = exc.message
        return row
    except Exception as exc:  # defensive: never let one ticker kill the run
        logger.exception("Unexpected error while processing %s", symbol)
        row["error"] = f"Unexpected error: {type(exc).__name__}: {exc}"
        return row

    weekly_close = (
        data.weekly["Close"] if "Close" in getattr(data.weekly, "columns", []) else pd.Series(dtype="float64")
    )
    matrix, notes = build_ema_matrix(
        symbol=symbol,
        price=data.price,
        daily_close=data.daily["Close"],
        weekly_close=weekly_close,
        periods=data_cfg["ema_periods"],
        decimals=decimals,
    )

    # Signal: "Sell" when price is below the daily 200 EMA, "Hold" otherwise.
    ema200_cell = matrix.get("200", {}).get("daily", {})
    signal = "Sell" if ema200_cell.get("below") else "Hold"

    row.update(
        {
            "price": round(data.price, decimals) if data.price is not None else None,
            "price_display": f"{data.price:,.{decimals}f}" if data.price is not None else "-",
            "name": data.name,
            "signal": signal,
            "currency": data.currency,
            "as_of": data.as_of,
            "emas": matrix,
            "notes": data.notes + notes,
        }
    )

    if getattr(data, "fetch_symbol", None) and data.fetch_symbol != symbol:
        row["fetch_symbol"] = data.fetch_symbol
        row["url"] = tradingview_url(data.fetch_symbol)

    if data.price is not None and data.price > 0:
        try:
            from .db.repositories import quotes as _quote_repo
            quote_payload = {
                "price": round(data.price, decimals),
                "currency": data.currency or "INR",
                "name": data.name or symbol,
            }
            _quote_repo.save_quote(symbol, quote_payload)
            fetch_sym = getattr(data, "fetch_symbol", None)
            if fetch_sym and fetch_sym != symbol:
                _quote_repo.save_quote(fetch_sym, quote_payload)
            if "." in symbol:
                bare = symbol.split(".")[0]
                _quote_repo.save_quote(bare, quote_payload)
        except Exception as exc:
            logger.debug("Failed to cache quote for %s: %s", symbol, exc)

    return row


def _blank_cell() -> dict[str, Any]:
    blank = {"value": None, "below": False, "display": "N/A", "available": False}
    return {"daily": dict(blank), "weekly": dict(blank)}


# EMA periods ordered from highest priority to lowest.  A ticker below the
# daily 200 EMA sorts before one below only the daily 9 EMA.
_PRIORITY_EMAS = [200, 100, 50, 21, 9]


def _ema_sort_key(row: dict[str, Any]) -> tuple[int, str]:
    """Return ``(priority, display_name)`` for sorting rows.

    Priority 0 = below daily 200 EMA (highest), …, 4 = below daily 9 only,
    5 = above all daily EMAs.
    6 = fetch problem / error (shown at last in table).
    Ties broken alphabetically.
    """
    if row.get("error") or row.get("price") is None:
        return (len(_PRIORITY_EMAS) + 1, row.get("display", row.get("symbol", "")))

    emas = row.get("emas", {})
    for idx, period in enumerate(_PRIORITY_EMAS):
        cell = emas.get(str(period), {})
        if cell.get("daily", {}).get("below"):
            return (idx, row.get("display", row.get("symbol", "")))
    return (len(_PRIORITY_EMAS), row.get("display", row.get("symbol", "")))


def refresh_portfolios(
    source: str = "manual",
    portfolios: dict[str, list[str]] | None = None,
    publish: bool = True,
) -> dict[str, Any]:
    """Refresh every ticker in both portfolios and persist the snapshot."""
    settings = load_settings()
    port_meta = load_tracker_portfolios_meta(PORTFOLIO_NAMES)
    if portfolios is None:
        portfolios = {name: list(symbols.keys()) for name, symbols in port_meta.items()}

    max_workers = max(1, int(settings["data"].get("max_workers", 4)))

    tracker_symbols = {symbol for tickers in portfolios.values() for symbol in tickers}
    pt_symbols = set(get_all_portfolio_tracker_symbols())
    symbols = sorted(tracker_symbols | pt_symbols)
    logger.info("Refreshing %s unique ticker(s) with %s worker(s)", len(symbols), max_workers)

    rows_by_symbol: dict[str, dict[str, Any]] = {}
    if symbols:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for row in pool.map(lambda symbol: build_row(symbol, settings), symbols):
                rows_by_symbol[row["symbol"]] = row

    snapshot = empty_snapshot(settings)
    snapshot["generated_at"] = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    snapshot["source"] = source

    errors: list[dict[str, str]] = []
    ok_count = 0
    for name in PORTFOLIO_NAMES:
        rows = []
        for symbol in portfolios.get(name, []):
            if symbol in rows_by_symbol:
                row = dict(rows_by_symbol[symbol])
                meta = port_meta.get(name, {}).get(symbol, {})
                row["avg_price"] = meta.get("avg_price")
                row["is_sourced"] = meta.get("is_sourced", False)
                row["is_manual"] = meta.get("is_manual", True)
                if meta.get("stock_name"):
                    row["name"] = meta["stock_name"]
                drawdown_pct, risk_tier = compute_cost_risk(row.get("price"), row.get("avg_price"))
                row["cost_drawdown_pct"] = drawdown_pct
                row["risk_tier"] = risk_tier
                rows.append(row)
        rows.sort(key=_ema_sort_key)
        snapshot["portfolios"][name] = {"rows": rows}

    for symbol in tracker_symbols:
        row = rows_by_symbol.get(symbol)
        if row and row.get("error"):
            errors.append({"symbol": symbol, "message": row["error"]})
        elif row:
            ok_count += 1

    snapshot["errors"] = errors
    snapshot["stats"] = {"total": len(tracker_symbols), "ok": ok_count, "failed": len(errors)}
    save_snapshot(snapshot)

    if publish:
        status_store.bump(
            source=source,
            message=f"{ok_count}/{len(tracker_symbols)} ticker(s) refreshed successfully.",
            summary=snapshot["stats"],
        )

    if errors:
        logger.warning("Refresh finished with %s failure(s): %s", len(errors), ", ".join(e["symbol"] for e in errors))
    else:
        logger.info("Refresh finished successfully for %s ticker(s)", len(symbols))
    return snapshot


def upsert_row(portfolio_name: str, row: dict[str, Any], source: str = "ticker-added") -> dict[str, Any]:
    """Insert/replace a single row in the stored snapshot and publish it."""
    drawdown_pct, risk_tier = compute_cost_risk(row.get("price"), row.get("avg_price"))
    row["cost_drawdown_pct"] = drawdown_pct
    row["risk_tier"] = risk_tier
    snapshot = load_snapshot()
    bucket = snapshot["portfolios"].setdefault(portfolio_name, {"rows": []})
    rows = [existing for existing in bucket["rows"] if existing.get("symbol") != row["symbol"]]
    rows.append(row)
    rows.sort(key=_ema_sort_key)
    bucket["rows"] = rows
    snapshot["generated_at"] = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    snapshot["source"] = source
    _recalculate_stats(snapshot)
    save_snapshot(snapshot)
    status_store.bump(source=source, message=f"{row['symbol']} added to {portfolio_name}.", summary=snapshot["stats"])
    return snapshot


def drop_row(portfolio_name: str, symbol: str, source: str = "ticker-removed") -> dict[str, Any]:
    snapshot = load_snapshot()
    bucket = snapshot["portfolios"].setdefault(portfolio_name, {"rows": []})
    bucket["rows"] = [row for row in bucket["rows"] if row.get("symbol") != symbol]
    snapshot["generated_at"] = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    snapshot["source"] = source
    _recalculate_stats(snapshot)
    save_snapshot(snapshot)
    status_store.bump(source=source, message=f"{symbol} removed from {portfolio_name}.", summary=snapshot["stats"])
    return snapshot


def _recalculate_stats(snapshot: dict[str, Any]) -> None:
    seen: dict[str, dict[str, Any]] = {}
    for bucket in snapshot["portfolios"].values():
        for row in bucket.get("rows", []):
            seen[row["symbol"]] = row
    errors = [
        {"symbol": symbol, "message": row["error"]}
        for symbol, row in seen.items()
        if row.get("error")
    ]
    snapshot["errors"] = errors
    snapshot["stats"] = {"total": len(seen), "ok": len(seen) - len(errors), "failed": len(errors)}
