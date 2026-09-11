"""HTTP routes for the core tracker."""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any
from concurrent.futures import ThreadPoolExecutor

from flask import Blueprint, Response, jsonify, request, send_from_directory, stream_with_context

from ... import status as status_store
from ...config_manager import get_run_times, load_settings, set_run_times
from ...errors import ValidationError
from ...data_fetcher import fetch_ticker_quote
from ...paths import BASE_DIR
from ...portfolio import (
    add_ticker,
    normalize_symbol,
    record_addition,
    remove_ticker,
    validate_portfolio,
)
from ...service import build_row, drop_row, load_snapshot, refresh_portfolios, upsert_row, save_snapshot

logger = logging.getLogger(__name__)

tracker_bp = Blueprint("tracker", __name__)

_REFRESH_LOCK = threading.Lock()

SSE_MAX_SECONDS = 300
SSE_TICK_SECONDS = 2

def _tables_payload(snapshot: dict[str, Any] | None = None, message: str = "") -> dict[str, Any]:
    snapshot = snapshot if snapshot is not None else load_snapshot()
    status = status_store.read_status()
    return {
        "ok": True,
        "message": message,
        "generated_at": snapshot.get("generated_at"),
        "source": snapshot.get("source"),
        "stats": snapshot.get("stats", {}),
        "errors": snapshot.get("errors", []),
        "version": status["version"],
        "status": status,
        "snapshot": snapshot,
    }

@tracker_bp.route("/")
def index():
    return send_from_directory(str(BASE_DIR / "frontend" / "dist"), "index.html")

@tracker_bp.get("/api/data")
def api_data():
    """Raw snapshot, useful for debugging or external tooling."""
    return jsonify(load_snapshot())

@tracker_bp.get("/api/tables")
def api_tables():
    return jsonify(_tables_payload())

@tracker_bp.get("/api/status")
def api_status():
    return jsonify(status_store.read_status())

@tracker_bp.post("/api/refresh")
def api_refresh():
    if not _REFRESH_LOCK.acquire(blocking=False):
        return jsonify({"ok": False, "error": "A refresh is already running. Please wait."}), 409
    try:
        snapshot = refresh_portfolios(source="manual")
    except Exception as exc:
        logger.exception("Manual refresh failed")
        return jsonify({"ok": False, "error": f"Refresh failed: {exc}"}), 500
    finally:
        _REFRESH_LOCK.release()

    stats = snapshot["stats"]
    message = f"Refreshed {stats['ok']}/{stats['total']} ticker(s)."
    if stats["failed"]:
        message += f" {stats['failed']} failed - see the errors panel."
    return jsonify(_tables_payload(snapshot, message))

@tracker_bp.post("/api/tickers")
def api_add_ticker():
    payload = request.get_json(silent=True) or request.form
    portfolio = validate_portfolio(payload.get("portfolio", ""))
    symbol = normalize_symbol(payload.get("symbol", ""))

    from ...portfolio import load_tracker_portfolios_meta
    port_meta = load_tracker_portfolios_meta((portfolio,)).get(portfolio, {})
    bare = symbol.split(".")[0]
    matched_meta = next(
        (m for s, m in port_meta.items() if s == symbol or s.split(".")[0] == bare),
        None,
    )
    if matched_meta and matched_meta.get("is_manual"):
        raise ValidationError(f"{matched_meta['symbol']} is already in the {portfolio} portfolio.")

    # Fetch immediately so the row appears without waiting for a scheduled run.
    row = build_row(symbol)
    if row["error"]:
        raise ValidationError(
            f"Could not fetch data for {symbol} ({row['error']}). The ticker was not added."
        )

    # Use the resolved exchange symbol if switched (e.g. .BO if .NS was not available)
    target_symbol = row.get("fetch_symbol") or symbol
    if target_symbol != symbol:
        row["symbol"] = target_symbol

    add_ticker(portfolio, target_symbol)
    record_addition(portfolio, target_symbol)

    # Attach sourced metadata if ticker already exists in Portfolio Tracker
    meta = port_meta.get(target_symbol) or port_meta.get(symbol, {})
    row["avg_price"] = meta.get("avg_price")
    row["is_sourced"] = meta.get("is_sourced", False)
    row["is_manual"] = True
    if meta.get("stock_name"):
        row["name"] = meta["stock_name"]

    snapshot = upsert_row(portfolio, row)

    return jsonify(_tables_payload(snapshot, f"{target_symbol} added to {portfolio} and fetched live."))

@tracker_bp.delete("/api/tickers")
def api_remove_ticker():
    payload = request.get_json(silent=True) or request.form
    portfolio = validate_portfolio(payload.get("portfolio", ""))
    raw_symbol = payload.get("symbol", "")
    symbol = remove_ticker(portfolio, raw_symbol)

    from ...portfolio import load_tracker_portfolios_meta
    port_meta = load_tracker_portfolios_meta((portfolio,)).get(portfolio, {})
    if symbol not in port_meta:
        snapshot = drop_row(portfolio, symbol)
        msg = f"{symbol} removed from {portfolio}."
    else:
        # Sourced record remains, only manual record was removed
        snapshot = load_snapshot()
        for r in snapshot.get("portfolios", {}).get(portfolio, {}).get("rows", []):
            if r.get("symbol") == symbol:
                r["is_manual"] = False
                break
        save_snapshot(snapshot)
        msg = f"{symbol} manual entry removed; still tracked via Portfolio Tracker."

    return jsonify(_tables_payload(snapshot, msg))

@tracker_bp.get("/api/schedule")
def api_get_schedule():
    settings = load_settings()
    return jsonify(
        {
            "ok": True,
            "run_times": get_run_times(),
            "task_name": settings["schedule"].get("task_name"),
            "timezone": settings["schedule"].get("timezone"),
        }
    )

@tracker_bp.post("/api/schedule")
def api_set_schedule():
    payload = request.get_json(silent=True) or request.form
    times = payload.get("run_times")
    if times is None:
        times = [payload.get("run_time_1"), payload.get("run_time_2")]
    if isinstance(times, str):
        times = [part.strip() for part in times.split(",") if part.strip()]

    run_times = set_run_times(times)
    return jsonify(
        {
            "ok": True,
            "run_times": run_times,
            "message": f"Scheduled run times updated to {', '.join(run_times)} and synced with Windows Task Scheduler.",
        }
    )

@tracker_bp.get("/api/stream")
def api_stream():
    """Server-Sent Events feed that fires whenever the status version changes."""

    @stream_with_context
    def event_source():
        last_version = request.args.get("version", type=int)
        if last_version is None:
            last_version = status_store.read_status()["version"]
        deadline = time.monotonic() + SSE_MAX_SECONDS
        yield f"retry: {SSE_TICK_SECONDS * 1000}\\n\\n"
        while time.monotonic() < deadline:
            status = status_store.read_status()
            if status["version"] != last_version:
                last_version = status["version"]
                yield f"event: update\\ndata: {json.dumps(status)}\\n\\n"
            else:
                yield ": keep-alive\\n\\n"
            time.sleep(SSE_TICK_SECONDS)

    return Response(
        event_source(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

@tracker_bp.get("/api/stock-info")
def api_stock_info():
    symbol = request.args.get("symbol", "").strip()
    if not symbol:
        return jsonify({"ok": False, "error": "Symbol query parameter is required."}), 400
    try:
        normalized = normalize_symbol(symbol)
        quote = fetch_ticker_quote(normalized)
        return jsonify({"ok": True, **quote})
    except Exception as exc:
        logger.warning("Failed to fetch stock info for %s: %s", symbol, exc)
        return jsonify({"ok": False, "error": str(exc)}), 400

@tracker_bp.post("/api/stock-quotes")
def api_stock_quotes():
    """Fetch live quotes in parallel for a list of symbols."""
    payload = request.get_json(silent=True) or {}
    raw_symbols = payload.get("symbols", [])
    if isinstance(raw_symbols, str):
        raw_symbols = [s.strip() for s in raw_symbols.split(",") if s.strip()]

    symbols = [normalize_symbol(s) for s in raw_symbols if s]
    if not symbols:
        return jsonify({"ok": True, "quotes": {}})

    results = {}
    unique_symbols = sorted(set(symbols))
    with ThreadPoolExecutor(max_workers=min(8, len(unique_symbols))) as executor:
        futures = {executor.submit(fetch_ticker_quote, sym): sym for sym in unique_symbols}
        for future in futures:
            sym = futures[future]
            try:
                quote = future.result()
                results[sym] = quote
            except Exception as exc:
                logger.info("Quote fetch failed for %s: %s", sym, exc)
                results[sym] = {"symbol": sym, "error": str(exc), "price": None}

    return jsonify({"ok": True, "quotes": results})
