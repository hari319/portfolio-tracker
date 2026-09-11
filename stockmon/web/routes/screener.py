"""HTTP routes for the Screener."""

import logging
from flask import Blueprint, jsonify, request

from ...config_manager import load_settings
from ...errors import DataFetchError, ValidationError
from ...screener import (
    auto_detect_nonce,
    fetch_screener_data,
    list_saved_screener_dates,
    load_cached_screener,
)
from ...multi_day_analyzer import (
    analyze_multi_day_sequences,
    sync_historical_dates,
)
from ...backtester import backtest_strategy

logger = logging.getLogger(__name__)
screener_bp = Blueprint("screener", __name__)

@screener_bp.get("/api/screener/data")
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


@screener_bp.post("/api/screener/fetch")
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


@screener_bp.get("/api/screener/detect-nonce")
def api_screener_detect_nonce():
    nonce = auto_detect_nonce()
    if nonce:
        return jsonify({"ok": True, "nonce": nonce})
    return jsonify({"ok": False, "error": "Could not auto-detect nonce from website."}), 404


@screener_bp.post("/api/screener/sync-history")
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


@screener_bp.get("/api/screener/multi-day-analysis")
def api_screener_multi_day_analysis():
    max_days = int(request.args.get("max_days", 11))
    force = request.args.get("force", "").lower() in ("true", "1")
    try:
        res = analyze_multi_day_sequences(max_days=max_days, force_recompute=force)
        return jsonify(res)
    except Exception as exc:
        logger.exception("Error during multi-day sequence analysis")
        return jsonify({"ok": False, "error": str(exc)}), 500


@screener_bp.post("/api/screener/backtest")
def screener_backtest():
    """Run a backtest for given strategy rules."""
    data = request.get_json() or {}
    rules = data.get("rules", [])
    hold_days = data.get("hold_days", [1, 2, 3, 5])
    if not rules:
        return jsonify({"ok": False, "error": "No rules provided"}), 400
    result = backtest_strategy(rules, hold_days=hold_days)
    return jsonify(result)


@screener_bp.post("/api/screener/rebuild")
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
