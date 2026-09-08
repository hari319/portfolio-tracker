"""HTTP routes for the portfolio monitor UI and its JSON/SSE endpoints."""

from __future__ import annotations

from datetime import datetime
import io
import json
import logging
import threading
import time
from typing import Any

from flask import (
    Blueprint,
    Response,
    jsonify,
    render_template,
    request,
    send_from_directory,
    stream_with_context,
)

from .. import status as status_store
from ..config_manager import get_run_times, load_settings, set_run_times
from ..errors import DataFetchError, ValidationError
from ..data_fetcher import fetch_ticker_quote
from ..screener import (
    auto_detect_nonce,
    fetch_screener_data,
    list_saved_screener_dates,
    load_cached_screener,
)
from ..multi_day_analyzer import (
    analyze_multi_day_sequences,
    sync_historical_dates,
)
from ..paths import BASE_DIR
from ..portfolio import (
    PORTFOLIO_NAMES,
    add_ticker,
    load_portfolios,
    normalize_symbol,
    record_addition,
    remove_ticker,
    validate_portfolio,
)
from concurrent.futures import ThreadPoolExecutor
from ..service import build_row, drop_row, load_snapshot, refresh_portfolios, upsert_row
from ..stock_status import add_stock_status, delete_stock_status, load_stock_statuses, update_stock_status

logger = logging.getLogger(__name__)

bp = Blueprint("main", __name__)

# Guards against overlapping refreshes triggered by impatient clicking.
_REFRESH_LOCK = threading.Lock()

SSE_MAX_SECONDS = 300
SSE_TICK_SECONDS = 2


def _render_tables(snapshot: dict[str, Any]) -> str:
    try:
        return render_template(
            "_tables.html",
            snapshot=snapshot,
            portfolio_names=PORTFOLIO_NAMES,
            periods=snapshot.get("ema_periods", load_settings()["data"]["ema_periods"]),
        )
    except Exception:
        return ""


def _tables_payload(snapshot: dict[str, Any] | None = None, message: str = "") -> dict[str, Any]:
    snapshot = snapshot if snapshot is not None else load_snapshot()
    status = status_store.read_status()
    return {
        "ok": True,
        "message": message,
        "html": _render_tables(snapshot),
        "generated_at": snapshot.get("generated_at"),
        "source": snapshot.get("source"),
        "stats": snapshot.get("stats", {}),
        "errors": snapshot.get("errors", []),
        "version": status["version"],
        "status": status,
        "snapshot": snapshot,
    }


@bp.app_errorhandler(ValidationError)
def _handle_validation_error(exc: ValidationError):
    return jsonify({"ok": False, "error": str(exc)}), 400


@bp.app_errorhandler(DataFetchError)
def _handle_data_fetch_error(exc: DataFetchError):
    return jsonify({"ok": False, "error": str(exc)}), 502


@bp.route("/")
def index():
    dist_index = BASE_DIR / "frontend" / "dist" / "index.html"
    if dist_index.exists():
        return send_from_directory(str(BASE_DIR / "frontend" / "dist"), "index.html")

    settings = load_settings()
    snapshot = load_snapshot()
    return render_template(
        "index.html",
        snapshot=snapshot,
        settings=settings,
        portfolio_names=PORTFOLIO_NAMES,
        periods=snapshot.get("ema_periods", settings["data"]["ema_periods"]),
        run_times=get_run_times(),
        status=status_store.read_status(),
        poll_seconds=int(settings["ui"].get("status_poll_seconds", 5)),
    )


@bp.get("/api/data")
def api_data():
    """Raw snapshot, useful for debugging or external tooling."""
    return jsonify(load_snapshot())


@bp.get("/api/tables")
def api_tables():
    return jsonify(_tables_payload())


@bp.get("/api/status")
def api_status():
    return jsonify(status_store.read_status())


@bp.post("/api/refresh")
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


@bp.post("/api/tickers")
def api_add_ticker():
    payload = request.get_json(silent=True) or request.form
    portfolio = validate_portfolio(payload.get("portfolio", ""))
    symbol = normalize_symbol(payload.get("symbol", ""))

    if symbol in load_portfolios()[portfolio]:
        raise ValidationError(f"{symbol} is already in the {portfolio} portfolio.")

    # Fetch immediately so the row appears without waiting for a scheduled run.
    row = build_row(symbol)
    if row["error"]:
        raise ValidationError(
            f"Could not fetch data for {symbol} ({row['error']}). The ticker was not added."
        )

    add_ticker(portfolio, symbol)
    record_addition(portfolio, symbol)
    snapshot = upsert_row(portfolio, row)

    return jsonify(_tables_payload(snapshot, f"{symbol} added to {portfolio} and fetched live."))


@bp.delete("/api/tickers")
def api_remove_ticker():
    payload = request.get_json(silent=True) or request.form
    portfolio = validate_portfolio(payload.get("portfolio", ""))
    symbol = remove_ticker(portfolio, payload.get("symbol", ""))
    snapshot = drop_row(portfolio, symbol)
    return jsonify(_tables_payload(snapshot, f"{symbol} removed from {portfolio}."))


@bp.get("/api/schedule")
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


@bp.post("/api/schedule")
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


@bp.get("/api/stream")
def api_stream():
    """Server-Sent Events feed that fires whenever the status version changes."""

    @stream_with_context
    def event_source():
        last_version = request.args.get("version", type=int)
        if last_version is None:
            last_version = status_store.read_status()["version"]
        deadline = time.monotonic() + SSE_MAX_SECONDS
        yield f"retry: {SSE_TICK_SECONDS * 1000}\n\n"
        while time.monotonic() < deadline:
            status = status_store.read_status()
            if status["version"] != last_version:
                last_version = status["version"]
                yield f"event: update\ndata: {json.dumps(status)}\n\n"
            else:
                yield ": keep-alive\n\n"
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


@bp.get("/api/stock-info")
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


@bp.get("/api/stock-status")
def api_get_stock_status():
    items = load_stock_statuses()
    return jsonify({"ok": True, "items": items})


@bp.post("/api/stock-status")
def api_add_stock_status():
    payload = request.get_json(silent=True) or request.form
    if not payload:
        return jsonify({"ok": False, "error": "Invalid request payload."}), 400
    try:
        entry = add_stock_status(payload)
        items = load_stock_statuses()
        return jsonify(
            {
                "ok": True,
                "entry": entry,
                "items": items,
                "message": f"Stock status for {entry['symbol']} saved successfully.",
            }
        )
    except ValidationError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        logger.exception("Failed to save stock status")
        return jsonify({"ok": False, "error": f"Failed to save stock status: {exc}"}), 500


@bp.delete("/api/stock-status/<item_id>")
def api_delete_stock_status(item_id: str):
    try:
        items = delete_stock_status(item_id)
        return jsonify({"ok": True, "items": items, "message": "Stock status removed."})
    except Exception as exc:
        logger.exception("Failed to delete stock status %s", item_id)
        return jsonify({"ok": False, "error": f"Failed to delete stock status: {exc}"}), 500


@bp.put("/api/stock-status/<item_id>")
def api_update_stock_status(item_id: str):
    payload = request.get_json(silent=True) or request.form
    if not payload:
        return jsonify({"ok": False, "error": "Invalid request payload."}), 400
    try:
        entry = update_stock_status(item_id, payload)
        items = load_stock_statuses()
        return jsonify(
            {
                "ok": True,
                "entry": entry,
                "items": items,
                "message": f"Stock status for {entry.get('symbol')} updated successfully.",
            }
        )
    except ValidationError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        logger.exception("Failed to update stock status %s", item_id)
        return jsonify({"ok": False, "error": f"Failed to update stock status: {exc}"}), 500


@bp.post("/api/stock-quotes")
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


@bp.get("/api/screener/data")
def api_screener_data():
    date = request.args.get("date", "").strip()
    data = load_cached_screener(date)
    saved_dates = list_saved_screener_dates()
    nonce_info = (data.get("nonce_info") if data else {})
    multi_day_summary = None

    # Automatically enrich items with multi-day trajectory metrics
    if data and data.get("items") and len(saved_dates) >= 2:
        try:
            analysis = analyze_multi_day_sequences(max_days=11)
            if analysis and analysis.get("ok") and analysis.get("items_by_symbol"):
                by_sym = analysis["items_by_symbol"]
                for item in data["items"]:
                    sym = item.get("symbol")
                    if sym and sym in by_sym:
                        item.update(by_sym[sym])
                multi_day_summary = analysis.get("setups_summary")
        except Exception as exc:
            logger.debug("Automatic multi-day enrichment skipped: %s", exc)

    return jsonify({
        "ok": True,
        "data": data,
        "saved_dates": saved_dates,
        "nonce_info": nonce_info,
        "multi_day_summary": multi_day_summary,
    })


@bp.post("/api/screener/fetch")
def api_screener_fetch():
    payload = request.get_json(silent=True) or {}
    nonce = payload.get("nonce", "").strip()
    date = payload.get("date", "").strip()
    search = payload.get("search", "").strip()
    per_page = int(payload.get("per_page", 3489))

    try:
        data = fetch_screener_data(nonce=nonce, date=date, search=search, per_page=per_page)
        saved_dates = list_saved_screener_dates()

        multi_day_summary = None
        if data and data.get("items") and len(saved_dates) >= 2:
            try:
                analysis = analyze_multi_day_sequences(max_days=11, force_recompute=True)
                if analysis and analysis.get("ok") and analysis.get("items_by_symbol"):
                    by_sym = analysis["items_by_symbol"]
                    for item in data["items"]:
                        sym = item.get("symbol")
                        if sym and sym in by_sym:
                            item.update(by_sym[sym])
                    multi_day_summary = analysis.get("setups_summary")
            except Exception as exc:
                logger.debug("Multi-day enrichment after fetch skipped: %s", exc)

        return jsonify({
            "ok": True,
            "data": data,
            "saved_dates": saved_dates,
            "nonce_info": data.get("nonce_info", {}),
            "multi_day_summary": multi_day_summary,
            "message": f"Successfully loaded {data.get('total', len(data.get('items', [])))} stocks for {data.get('date', 'latest')}.",
        })
    except ValidationError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except DataFetchError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502
    except Exception as exc:
        logger.exception("Unexpected error during screener fetch")
        return jsonify({"ok": False, "error": f"Internal server error: {exc}"}), 500


@bp.get("/api/screener/detect-nonce")
def api_screener_detect_nonce():
    nonce = auto_detect_nonce()
    if nonce:
        return jsonify({"ok": True, "nonce": nonce})
    return jsonify({"ok": False, "error": "Could not auto-detect nonce from website."}), 404


@bp.post("/api/screener/sync-history")
def api_screener_sync_history():
    payload = request.get_json(silent=True) or {}
    max_days = int(payload.get("max_days", 11))
    target_dates = payload.get("target_dates")
    try:
        res = sync_historical_dates(target_dates=target_dates, max_days=max_days)
        return jsonify(res)
    except Exception as exc:
        logger.exception("Error syncing historical screener dates")
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.get("/api/screener/multi-day-analysis")
def api_screener_multi_day_analysis():
    max_days = int(request.args.get("max_days", 11))
    force = request.args.get("force", "").lower() in ("true", "1")
    try:
        res = analyze_multi_day_sequences(max_days=max_days, force_recompute=force)
        return jsonify(res)
    except Exception as exc:
        logger.exception("Error during multi-day sequence analysis")
        return jsonify({"ok": False, "error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Backup & Restore Endpoints (DATA_STORAGE_MIGRATION.md §6.3 - §6.4)
# ---------------------------------------------------------------------------

@bp.post("/api/backup/create")
def api_backup_create():
    """Trigger an immediate backup of stockmon.db."""
    from ..db.backup import create_backup, rotate_backups
    try:
        path = create_backup()
        rotate_backups()
        return jsonify({"ok": True, "filename": path.name, "message": "Backup created successfully."})
    except Exception as exc:
        logger.exception("Backup failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.get("/api/backup/list")
def api_backup_list():
    """List all available backups."""
    from ..db.backup import list_backups
    backups = list_backups()
    # Check for staleness warning (if newest backup > 7 days old)
    is_stale = False
    if backups:
        from datetime import datetime
        try:
            newest_ts = backups[-1].get("timestamp", "")
            if newest_ts:
                # Format: YYYY-MM-DD_HHMMSS
                dt = datetime.strptime(newest_ts, "%Y-%m-%d_%H%M%S")
                if (datetime.now() - dt).days > 7:
                    is_stale = True
        except Exception:
            pass
    return jsonify({"ok": True, "backups": backups, "is_stale": is_stale})


@bp.post("/api/backup/restore")
def api_backup_restore():
    """Restore durable DB from selected backup."""
    payload = request.get_json(silent=True) or {}
    filename = payload.get("filename", "").strip()
    if not filename:
        return jsonify({"ok": False, "error": "Filename is required"}), 400

    from ..db.backup import restore_backup
    try:
        restore_backup(filename)
        return jsonify({"ok": True, "message": f"Successfully restored {filename}."})
    except Exception as exc:
        logger.exception("Restore failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.post("/api/screener/rebuild")
def api_screener_rebuild():
    """Rebuild disposable screener cache history from API."""
    settings = load_settings()
    retention_days = int(settings.get("data", {}).get("screener_retention_days", 60))
    try:
        res = sync_historical_dates(max_days=retention_days)
        return jsonify({"ok": True, "result": res})
    except Exception as exc:
        logger.exception("Screener rebuild failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Portfolio Tracker API (§1-§8)
# ---------------------------------------------------------------------------

@bp.get("/api/portfolio-tracker/<portfolio>")
def api_portfolio_tracker_data(portfolio: str):
    """Fetch complete holdings, sold, dividends, totals, and summary for a portfolio."""
    port_name = portfolio.strip().upper()
    if port_name not in ("MADI", "BAPA", "LOAN"):
        return jsonify({"ok": False, "error": f"Invalid portfolio: {portfolio}"}), 400

    from ..db.repositories import dividends as div_repo
    from ..db.repositories import holdings as hold_repo
    from ..db.repositories import quotes as quote_repo
    from ..db.repositories import summary as sum_repo
    from ..portfolio_tracker import (
        compute_summary_panel,
        compute_totals,
        enrich_holding_row,
        enrich_sold_row,
    )

    quotes_cache = quote_repo.load_quotes_cache()

    # Open holdings with child buy lots
    open_raw = hold_repo.list_holdings(port_name, status="open")
    enriched_open = []
    for h in open_raw:
        lots = hold_repo.get_lots(h["id"])
        sym = h["symbol"]
        bare = sym.split(".")[0]
        quote = next(
            (
                quotes_cache[key]
                for key in (sym, bare, f"{bare}.NS", f"{bare}.BO")
                if key in quotes_cache
            ),
            None,
        )
        live_price = quote["price"] if quote and quote.get("price") else None
        enriched_open.append(enrich_holding_row(h, live_price=live_price, lots=lots))

    open_totals = compute_totals(enriched_open)

    # Sold holdings
    sold_raw = hold_repo.list_holdings(port_name, status="sold")
    enriched_sold = [enrich_sold_row(s) for s in sold_raw]
    sold_totals = compute_totals(enriched_sold)

    # Dividends
    dividends = div_repo.list_dividends(port_name)
    total_div = div_repo.total_dividends(port_name)

    # Summary panel
    summary_data = None
    if port_name == "LOAN":
        sum_vals = sum_repo.get_all()
        # Stock Profit in Block B reflects realized gains from sold positions: Earned total - Loss total
        loan_earned = sold_totals["earned"]
        loan_loss = sold_totals["loss"]
        loan_stock_invest = open_totals["invested_amount"]
        summary_data = compute_summary_panel(
            sum_vals,
            loan_earned=loan_earned,
            loan_loss=loan_loss,
            loan_dividends=total_div,
            loan_stock_invest=loan_stock_invest,
        )

    return jsonify({
        "ok": True,
        "portfolio": port_name,
        "open_holdings": enriched_open,
        "sold_holdings": enriched_sold,
        "open_totals": open_totals,
        "sold_totals": sold_totals,
        "dividends": dividends,
        "total_dividends": round(total_div, 2),
        "summary": summary_data,
    })


# Not every holding is an NSE stock, so a bare ticker is tried against both exchanges.
_TICKER_SUFFIXES = (".NS", ".BO")


def _resolve_ticker(raw_symbol: str) -> dict:
    """Resolve a ticker to the exchange-suffixed symbol that actually quotes.

    Returns ``{symbol, name, price, found}`` where ``found`` reports whether a real
    company name (not just the ticker) could be fetched — §3's confirmation trigger.
    """
    from ..db.repositories import quotes as quote_repo

    sym = (raw_symbol or "").strip().upper().replace(" ", "")
    if not sym:
        return {"symbol": "", "name": "", "price": None, "found": False}

    if "." in sym or sym.startswith("^"):
        candidates = [sym]
    else:
        candidates = [f"{sym}{suffix}" for suffix in _TICKER_SUFFIXES]

    for cand in [sym, *candidates]:
        cached = quote_repo.get_quote(cand)
        if cached and cached.get("price"):
            name = (cached.get("name") or "").strip()
            resolved_name = "" if name.upper() in ("", cand, sym) else name
            return {
                "symbol": cand,
                "name": resolved_name,
                "price": cached.get("price"),
                "found": bool(resolved_name),
            }

    from ..data_fetcher import fetch_ticker_quote

    for cand in candidates:
        try:
            res = fetch_ticker_quote(cand)
        except Exception as exc:
            logger.info("Ticker lookup failed for %s: %s", cand, exc)
            continue
        if not res.get("price"):
            continue
        name = (res.get("name") or "").strip()
        resolved_name = "" if name.upper() in ("", cand, sym) else name
        return {
            "symbol": cand,
            "name": resolved_name,
            "price": res.get("price"),
            "found": bool(resolved_name),
        }

    return {"symbol": candidates[0], "name": "", "price": None, "found": False}


@bp.get("/api/portfolio-tracker/lookup-ticker")
def api_portfolio_tracker_lookup_ticker():
    """Look up stock name and quote for a ticker symbol."""
    sym = (request.args.get("symbol") or "").strip().upper()
    if not sym:
        return jsonify({"ok": False, "error": "Symbol is required."}), 400

    res = _resolve_ticker(sym)
    return jsonify({
        "ok": True,
        "symbol": sym,
        "resolved_symbol": res["symbol"],
        "name": res["name"],
        "price": res["price"],
        "found": res["found"],
    })


@bp.post("/api/portfolio-tracker/holding")
def api_portfolio_tracker_add_holding():
    """Add a new open holding / buy lot."""
    payload = request.get_json(silent=True) or request.form
    portfolio = (payload.get("portfolio") or "").strip().upper()
    symbol = (payload.get("symbol") or "").strip().upper()
    invest_date = (payload.get("invest_date") or "").strip()
    quantity = float(payload.get("quantity") or 0.0)
    avg_price = float(payload.get("avg_price") or 0.0)

    if not portfolio or not symbol or quantity <= 0 or avg_price <= 0:
        return jsonify({"ok": False, "error": "portfolio, symbol, quantity (>0), and avg_price (>0) are required."}), 400

    from ..db.backup import create_backup
    from ..db.repositories import holdings as hold_repo

    resolved = _resolve_ticker(symbol)
    stored_symbol = resolved["symbol"] or symbol

    stock_name = (payload.get("stock_name") or payload.get("scheme_name") or "").strip()
    name_confirmed = bool(payload.get("name_confirmed"))

    if stock_name:
        name_confirmed = True
    elif resolved.get("found") and resolved.get("name"):
        stock_name = resolved["name"]
        name_confirmed = True
    else:
        # Sensible fallback: empty string fallback if ticker lookup fails, rather than crashing
        stock_name = ""
        name_confirmed = False

    scheme_name = stock_name or stored_symbol

    person = (payload.get("person") or "").strip().upper() if portfolio == "LOAN" else None
    remarks = (payload.get("remarks") or "").strip() or None
    bought_reason = (payload.get("bought_reason") or "").strip() or None

    holding_id, lot_id = hold_repo.add_holding(
        portfolio_name=portfolio,
        symbol=stored_symbol,
        scheme_name=scheme_name,
        stock_name=stock_name,
        invest_date=invest_date or datetime.now().strftime("%Y-%m-%d"),
        quantity=quantity,
        avg_price=avg_price,
        person=person,
        remarks=remarks,
        name_confirmed=name_confirmed,
        bought_reason=bought_reason,
    )

    try:
        create_backup()
    except Exception as exc:
        logger.warning("Auto backup after adding holding failed: %s", exc)

    return jsonify({
        "ok": True,
        "holding_id": holding_id,
        "lot_id": lot_id,
        "symbol": stored_symbol,
        "stock_name": stock_name,
        "message": f"Successfully added holding for {stored_symbol} in {portfolio}.",
    })


@bp.post("/api/portfolio-tracker/lot")
def api_portfolio_tracker_add_lot():
    """Add a child buy lot to an existing holding."""
    payload = request.get_json(silent=True) or request.form
    holding_id = int(payload.get("holding_id") or 0)
    invest_date = (payload.get("invest_date") or "").strip()
    quantity = float(payload.get("quantity") or 0.0)
    avg_price = float(payload.get("avg_price") or 0.0)
    remarks = (payload.get("remarks") or "").strip() or None

    if holding_id <= 0 or quantity <= 0 or avg_price <= 0:
        return jsonify({"ok": False, "error": "Valid holding_id, quantity, and avg_price required."}), 400

    from ..db.backup import create_backup
    from ..db.repositories import holdings as hold_repo

    lot_id = hold_repo.add_buy_lot(
        holding_id=holding_id,
        invest_date=invest_date or datetime.now().strftime("%Y-%m-%d"),
        quantity=quantity,
        avg_price=avg_price,
        remarks=remarks,
    )

    try:
        create_backup()
    except Exception:
        pass

    return jsonify({"ok": True, "lot_id": lot_id, "message": "Buy lot added successfully."})


@bp.delete("/api/portfolio-tracker/holding/<int:holding_id>")
def api_portfolio_tracker_delete_holding(holding_id: int):
    """Delete a holding and its associated buy lots."""
    from ..db.backup import create_backup
    from ..db.repositories import holdings as hold_repo

    deleted = hold_repo.delete_holding(holding_id)
    if not deleted:
        return jsonify({"ok": False, "error": f"Holding {holding_id} not found."}), 404

    try:
        create_backup()
    except Exception:
        pass

    return jsonify({"ok": True, "message": f"Holding {holding_id} deleted."})


@bp.delete("/api/portfolio-tracker/lot/<int:lot_id>")
def api_portfolio_tracker_delete_lot(lot_id: int):
    """Delete a single buy lot."""
    from ..db.backup import create_backup
    from ..db.repositories import holdings as hold_repo

    deleted = hold_repo.delete_lot(lot_id)
    if not deleted:
        return jsonify({"ok": False, "error": f"Lot {lot_id} not found."}), 404

    try:
        create_backup()
    except Exception:
        pass

    return jsonify({"ok": True, "message": f"Lot {lot_id} deleted."})


@bp.put("/api/portfolio-tracker/lot/<int:lot_id>")
def api_portfolio_tracker_update_lot(lot_id: int):
    """Update a buy lot's details (invest date, quantity, avg price, invested amount, buy charge, remarks)."""
    payload = request.get_json(silent=True) or request.form
    invest_date = (payload.get("invest_date") or "").strip()
    try:
        quantity = float(payload.get("quantity") or 0.0)
        avg_price = float(payload.get("avg_price") or 0.0)
    except (ValueError, TypeError):
        return jsonify({"ok": False, "error": "Invalid quantity or avg_price."}), 400

    if quantity <= 0 or avg_price <= 0:
        return jsonify({"ok": False, "error": "quantity and avg_price must be greater than 0."}), 400

    invested_amount = payload.get("invested_amount")
    if invested_amount is not None and str(invested_amount).strip() != "":
        try:
            invested_amount = float(invested_amount)
        except (ValueError, TypeError):
            invested_amount = None
    else:
        invested_amount = None

    buy_charge = payload.get("buy_charge")
    if buy_charge is not None and str(buy_charge).strip() != "":
        try:
            buy_charge = float(buy_charge)
        except (ValueError, TypeError):
            buy_charge = None
    else:
        buy_charge = None

    remarks = payload.get("remarks")
    if remarks is not None:
        remarks = str(remarks).strip()

    app = payload.get("app")
    if app is not None:
        app = str(app).strip()

    from ..db.backup import create_backup
    from ..db.repositories import holdings as hold_repo

    updated = hold_repo.update_lot(
        lot_id=lot_id,
        invest_date=invest_date or datetime.now().strftime("%Y-%m-%d"),
        quantity=quantity,
        avg_price=avg_price,
        invested_amount=invested_amount,
        buy_charge=buy_charge,
        remarks=remarks,
        app=app,
    )
    if not updated:
        return jsonify({"ok": False, "error": f"Lot {lot_id} not found."}), 404

    try:
        create_backup()
    except Exception:
        pass

    return jsonify({"ok": True, "message": f"Lot {lot_id} updated successfully."})


@bp.put("/api/portfolio-tracker/holding/<int:holding_id>")
def api_portfolio_tracker_update_holding(holding_id: int):
    """Update high-level holding details (symbol, scheme_name/stock_name, person, remarks)."""
    payload = request.get_json(silent=True) or request.form
    raw_symbol = payload.get("symbol")
    clean_symbol = raw_symbol.strip().upper() if raw_symbol and raw_symbol.strip() else None
    raw_stock_name = payload.get("stock_name") or payload.get("scheme_name")
    clean_stock_name = raw_stock_name.strip() if raw_stock_name and raw_stock_name.strip() else ""
    person = payload.get("person")
    remarks = payload.get("remarks")
    name_confirmed = payload.get("name_confirmed")

    if clean_symbol and (not clean_stock_name or clean_stock_name.upper() == clean_symbol):
        resolved = _resolve_ticker(clean_symbol)
        if resolved.get("found") and resolved.get("name"):
            clean_stock_name = resolved["name"]
            if name_confirmed is None:
                name_confirmed = True

    scheme_name = clean_stock_name or clean_symbol
    stock_name = clean_stock_name

    from ..db.backup import create_backup
    from ..db.repositories import holdings as hold_repo

    updated = hold_repo.update_holding(
        holding_id=holding_id,
        symbol=clean_symbol,
        scheme_name=scheme_name,
        stock_name=stock_name,
        person=person,
        remarks=remarks,
        name_confirmed=name_confirmed,
    )
    if not updated:
        return jsonify({"ok": False, "error": f"Holding {holding_id} not found."}), 404

    try:
        create_backup()
    except Exception:
        pass

    return jsonify({
        "ok": True,
        "message": f"Holding {holding_id} updated successfully.",
        "symbol": clean_symbol,
        "stock_name": stock_name,
    })


@bp.put("/api/portfolio-tracker/sold/<int:holding_id>")
def api_portfolio_tracker_update_sold(holding_id: int):
    """Update a sold position (invest_date, sell_date, quantity, avg_price, sell_price, invested_amount, buy_charge, sell_charge, remarks, person, stock_name)."""
    payload = request.get_json(silent=True) or request.form
    invest_date = (payload.get("invest_date") or "").strip()
    sell_date = (payload.get("sell_date") or "").strip()

    try:
        quantity = float(payload.get("quantity") or 0.0)
        avg_price = float(payload.get("avg_price") or 0.0)
        sell_price = float(payload.get("sell_price") or 0.0)
    except (ValueError, TypeError):
        return jsonify({"ok": False, "error": "Invalid quantity, avg_price, or sell_price."}), 400

    if quantity <= 0 or avg_price < 0 or sell_price < 0:
        return jsonify({"ok": False, "error": "quantity must be > 0 and prices must be >= 0."}), 400

    invested_amount = payload.get("invested_amount")
    if invested_amount is not None and str(invested_amount).strip() != "":
        try:
            invested_amount = float(invested_amount)
        except (ValueError, TypeError):
            invested_amount = None
    else:
        invested_amount = None

    buy_charge = payload.get("buy_charge")
    if buy_charge is not None and str(buy_charge).strip() != "":
        try:
            buy_charge = float(buy_charge)
        except (ValueError, TypeError):
            buy_charge = None
    else:
        buy_charge = None

    sell_charge = payload.get("sell_charge")
    if sell_charge is not None and str(sell_charge).strip() != "":
        try:
            sell_charge = float(sell_charge)
        except (ValueError, TypeError):
            sell_charge = None
    else:
        sell_charge = None

    remarks = payload.get("remarks")
    person = payload.get("person")
    raw_symbol = payload.get("symbol")
    clean_symbol = raw_symbol.strip().upper() if raw_symbol and raw_symbol.strip() else None
    raw_stock_name = payload.get("stock_name") or payload.get("scheme_name")
    clean_stock_name = raw_stock_name.strip() if raw_stock_name and raw_stock_name.strip() else ""
    name_confirmed = payload.get("name_confirmed")

    if clean_symbol and (not clean_stock_name or clean_stock_name.upper() == clean_symbol):
        resolved = _resolve_ticker(clean_symbol)
        if resolved.get("found") and resolved.get("name"):
            clean_stock_name = resolved["name"]
            if name_confirmed is None:
                name_confirmed = True

    scheme_name = clean_stock_name or clean_symbol
    stock_name = clean_stock_name

    from ..db.backup import create_backup
    from ..db.repositories import holdings as hold_repo

    updated = hold_repo.update_sold_position(
        holding_id=holding_id,
        invest_date=invest_date or datetime.now().strftime("%Y-%m-%d"),
        sell_date=sell_date or datetime.now().strftime("%Y-%m-%d"),
        quantity=quantity,
        avg_price=avg_price,
        sell_price=sell_price,
        invested_amount=invested_amount,
        buy_charge=buy_charge,
        sell_charge=sell_charge,
        remarks=remarks,
        person=person,
        symbol=clean_symbol,
        scheme_name=scheme_name,
        stock_name=stock_name,
        name_confirmed=name_confirmed,
    )
    if not updated:
        return jsonify({"ok": False, "error": f"Sold position {holding_id} not found."}), 404

    try:
        create_backup()
    except Exception:
        pass

    return jsonify({
        "ok": True,
        "message": f"Sold position {holding_id} updated successfully.",
        "symbol": clean_symbol,
        "stock_name": stock_name,
    })


@bp.post("/api/portfolio-tracker/sell")
def api_portfolio_tracker_sell():
    """Sell a holding, moving it to the Sold table."""
    payload = request.get_json(silent=True) or request.form
    holding_id = int(payload.get("holding_id") or 0)
    sell_date = (payload.get("sell_date") or "").strip() or datetime.now().strftime("%Y-%m-%d")
    sell_price = float(payload.get("sell_price") or 0.0)
    quantity = float(payload["quantity"]) if payload.get("quantity") else None
    remarks = (payload.get("remarks") or "").strip() or None
    sold_reason = (payload.get("sold_reason") or "").strip() or None
    mistake_learned = (payload.get("mistake_learned") or "").strip() or None

    if holding_id <= 0 or sell_price <= 0:
        return jsonify({"ok": False, "error": "holding_id and sell_price (>0) are required."}), 400

    from ..db.backup import create_backup
    from ..db.repositories import holdings as hold_repo

    try:
        sale_id = hold_repo.sell_holding(
            holding_id=holding_id,
            sell_date=sell_date,
            sell_price=sell_price,
            quantity=quantity,
            remarks=remarks,
            sold_reason=sold_reason,
            mistake_learned=mistake_learned,
        )
        try:
            create_backup()
        except Exception:
            pass

        return jsonify({"ok": True, "sale_id": sale_id, "message": "Holding sold successfully."})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.put("/api/portfolio-tracker/notes/<int:holding_id>")
def api_portfolio_tracker_update_notes(holding_id: int):
    """Update §6 note fields: bought_reason, sold_reason, mistake_learned."""
    payload = request.get_json(silent=True) or request.form
    from ..db.repositories import holdings as hold_repo

    updated = hold_repo.update_notes(
        holding_id=holding_id,
        bought_reason=payload.get("bought_reason"),
        sold_reason=payload.get("sold_reason"),
        mistake_learned=payload.get("mistake_learned"),
    )
    if not updated:
        return jsonify({"ok": False, "error": f"Holding {holding_id} not found."}), 404

    return jsonify({"ok": True, "message": "Notes updated successfully."})


@bp.get("/api/portfolio-tracker/mistakes")
def api_portfolio_tracker_list_mistakes():
    """List all holdings with lessons/mistakes recorded (§6 follow-up)."""
    from ..db.repositories import holdings as hold_repo
    mistakes = hold_repo.list_all_mistakes()
    return jsonify({"ok": True, "mistakes": mistakes})


@bp.post("/api/portfolio-tracker/dividend")
def api_portfolio_tracker_add_dividend():
    """Add a dividend record."""
    payload = request.get_json(silent=True) or request.form
    portfolio = (payload.get("portfolio") or "").strip().upper()
    symbol = (payload.get("symbol") or "").strip().upper()
    value = float(payload.get("value") or 0.0)
    received_date = (payload.get("received_date") or "").strip() or datetime.now().strftime("%Y-%m-%d")

    if not portfolio or not symbol or value <= 0:
        return jsonify({"ok": False, "error": "portfolio, symbol, and value (>0) are required."}), 400

    from ..db.repositories import dividends as div_repo
    div_id = div_repo.add_dividend(portfolio, symbol, value, received_date)
    return jsonify({"ok": True, "dividend_id": div_id, "message": f"Dividend recorded for {symbol}."})


@bp.delete("/api/portfolio-tracker/dividend/<int:dividend_id>")
def api_portfolio_tracker_delete_dividend(dividend_id: int):
    """Delete a dividend record."""
    from ..db.repositories import dividends as div_repo
    deleted = div_repo.delete_dividend(dividend_id)
    if not deleted:
        return jsonify({"ok": False, "error": "Dividend not found."}), 404
    return jsonify({"ok": True, "message": "Dividend deleted."})


@bp.get("/api/portfolio-tracker/summary")
def api_portfolio_tracker_get_summary():
    """Get Summary panel values."""
    from ..db.repositories import summary as sum_repo
    return jsonify({"ok": True, "values": sum_repo.get_all_rows()})


@bp.put("/api/portfolio-tracker/summary")
def api_portfolio_tracker_update_summary():
    """Update a fixed value in the Summary panel."""
    payload = request.get_json(silent=True) or request.form
    key = (payload.get("key") or "").strip()
    val = float(payload.get("value") or 0.0)
    label = payload.get("label")

    if not key:
        return jsonify({"ok": False, "error": "Key is required."}), 400

    from ..db.repositories import summary as sum_repo
    sum_repo.upsert(key, val, label)
    return jsonify({"ok": True, "message": f"Updated summary field {key}."})


@bp.post("/api/portfolio-tracker/import")
def api_portfolio_tracker_import():
    """Upload and import Excel workbook (Invest.xlsx) into Portfolio Tracker."""
    replace = request.args.get("replace", "false").lower() in ("true", "1", "yes")

    from ..paths import BASE_DIR
    from ..sheet_io import import_workbook

    file = request.files.get("file")
    if file:
        file_bytes = io.BytesIO(file.read())
        res = import_workbook(file_bytes, replace=replace)
    else:
        # Check if default Invest.xlsx exists in root directory
        default_file = BASE_DIR / "Invest.xlsx"
        if default_file.exists():
            res = import_workbook(default_file, replace=replace)
        else:
            return jsonify({"ok": False, "error": "No file uploaded and Invest.xlsx not found."}), 400

    return jsonify(res)


@bp.get("/api/portfolio-tracker/export")
def api_portfolio_tracker_export():
    """Export current Portfolio Tracker database into standard Invest.xlsx or CSV format."""
    from flask import send_file
    from ..sheet_io import export_csv, export_workbook

    portfolio = request.args.get("portfolio")
    fmt = (request.args.get("format") or "xlsx").strip().lower()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    port_label = portfolio.upper() if portfolio else "ALL"

    if fmt == "csv":
        # CSV is one sheet per file, so a portfolio must be named explicitly.
        if port_label not in ("MADI", "BAPA", "LOAN"):
            return jsonify({
                "ok": False,
                "error": "CSV export requires ?portfolio=MADI|BAPA|LOAN.",
            }), 400
        buf = io.BytesIO()
        export_csv(buf, portfolio=port_label)
        buf.seek(0)
        return send_file(
            buf,
            as_attachment=True,
            download_name=f"Portfolio_Tracker_{port_label}_{stamp}.csv",
            mimetype="text/csv",
        )

    buf = io.BytesIO()
    export_workbook(buf, portfolio=portfolio)
    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name=f"Portfolio_Tracker_{port_label}_{stamp}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )




