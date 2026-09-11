"""HTTP routes for Swing Tracker."""

import logging
from flask import Blueprint, jsonify, request

from ...errors import ValidationError
from ...data_fetcher import fetch_ticker_quote
from ...portfolio import normalize_symbol

logger = logging.getLogger(__name__)
swing_tracker_bp = Blueprint("swing_tracker", __name__)

@swing_tracker_bp.get("/api/swing-tracker")
def api_get_swing_tracker():
    """Retrieve all swing trades and available trade sources."""
    from ...swing_tracker import load_swing_trades
    data = load_swing_trades()
    return jsonify({"ok": True, **data})


@swing_tracker_bp.post("/api/swing-tracker")
def api_add_swing_trade():
    """Add a new swing trade."""
    from ...swing_tracker import add_swing_trade, load_swing_trades
    payload = request.get_json(silent=True) or request.form
    if not payload:
        return jsonify({"ok": False, "error": "Invalid request payload."}), 400

    try:
        trade = add_swing_trade(payload)
        data = load_swing_trades()
        return jsonify({
            "ok": True,
            "trade": trade,
            **data,
            "message": f"Swing trade for {trade['symbol']} saved successfully.",
        })
    except ValidationError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        logger.exception("Failed to add swing trade")
        return jsonify({"ok": False, "error": f"Failed to add swing trade: {exc}"}), 500


@swing_tracker_bp.put("/api/swing-tracker/<int:trade_id>")
def api_update_swing_trade(trade_id: int):
    """Update an existing swing trade."""
    from ...swing_tracker import load_swing_trades, update_swing_trade
    payload = request.get_json(silent=True) or request.form
    if not payload:
        return jsonify({"ok": False, "error": "Invalid request payload."}), 400

    try:
        trade = update_swing_trade(trade_id, payload)
        data = load_swing_trades()
        return jsonify({
            "ok": True,
            "trade": trade,
            **data,
            "message": f"Swing trade #{trade_id} updated successfully.",
        })
    except ValidationError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        logger.exception("Failed to update swing trade %s", trade_id)
        return jsonify({"ok": False, "error": f"Failed to update swing trade: {exc}"}), 500


@swing_tracker_bp.delete("/api/swing-tracker/<int:trade_id>")
def api_delete_swing_trade(trade_id: int):
    """Delete a swing trade."""
    from ...swing_tracker import delete_swing_trade, load_swing_trades
    try:
        deleted = delete_swing_trade(trade_id)
        if not deleted:
            return jsonify({"ok": False, "error": f"Swing trade #{trade_id} not found."}), 404
        data = load_swing_trades()
        return jsonify({
            "ok": True,
            **data,
            "message": f"Swing trade #{trade_id} deleted successfully.",
        })
    except Exception as exc:
        logger.exception("Failed to delete swing trade %s", trade_id)
        return jsonify({"ok": False, "error": f"Failed to delete swing trade: {exc}"}), 500


@swing_tracker_bp.post("/api/swing-tracker/<int:trade_id>/refresh-price")
def api_refresh_swing_trade_price(trade_id: int):
    """Manually force an update of current price for a specific row."""
    from ...swing_tracker import load_swing_trades, refresh_swing_trade_price
    try:
        trade = refresh_swing_trade_price(trade_id)
        data = load_swing_trades()
        return jsonify({
            "ok": True,
            "trade": trade,
            **data,
            "message": f"Price updated for {trade['symbol']}.",
        })
    except ValidationError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        logger.exception("Failed to refresh price for swing trade %s", trade_id)
        return jsonify({"ok": False, "error": f"Failed to refresh price: {exc}"}), 500


@swing_tracker_bp.post("/api/swing-tracker/refresh-all")
def api_refresh_all_swing_trade_prices():
    """Manually refresh prices for all swing trades."""
    from ...swing_tracker import load_swing_trades, refresh_all_swing_trade_prices
    try:
        stats = refresh_all_swing_trade_prices()
        data = load_swing_trades()
        return jsonify({
            "ok": True,
            "stats": stats,
            **data,
            "message": f"Refreshed {stats['updated']}/{stats['total']} swing trade prices.",
        })
    except Exception as exc:
        logger.exception("Failed to refresh swing trade prices")
        return jsonify({"ok": False, "error": f"Failed to refresh prices: {exc}"}), 500


@swing_tracker_bp.get("/api/swing-tracker/sources")
def api_get_swing_sources():
    """List all persisted trade sources."""
    from ...db.repositories.swing_tracker import list_sources
    sources = list_sources()
    return jsonify({"ok": True, "sources": sources})


@swing_tracker_bp.post("/api/swing-tracker/sources")
def api_add_swing_source():
    """Create and persist a new trade source option on the fly."""
    from ...db.repositories.swing_tracker import add_source, list_sources
    payload = request.get_json(silent=True) or request.form
    name = (payload.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "Source name is required."}), 400

    add_source(name)
    return jsonify({"ok": True, "sources": list_sources(), "created": name})


@swing_tracker_bp.get("/api/swing-tracker/lookup-ticker")
def api_swing_lookup_ticker():
    """Check ticker and resolve price (checks Portfolio table first, then live quote)."""
    from ...swing_tracker import check_portfolio_table_price, resolve_ticker_price
    symbol = request.args.get("symbol", "").strip()
    if not symbol:
        return jsonify({"ok": False, "error": "Symbol query parameter is required."}), 400

    try:
        normalized = normalize_symbol(symbol)
        cached_price = check_portfolio_table_price(normalized)
        if cached_price is not None and cached_price > 0:
            return jsonify({
                "ok": True,
                "symbol": normalized,
                "price": round(cached_price, 2),
                "source": "portfolio",
                "message": f"Found in Portfolio table with price ₹{cached_price:.2f}.",
            })

        quote = fetch_ticker_quote(normalized)
        price = quote.get("price") if quote else None
        return jsonify({
            "ok": True,
            "symbol": normalized,
            "price": price,
            "name": quote.get("name", "") if quote else "",
            "source": "live",
            "message": f"Fetched live quote: ₹{price:.2f}." if price else "Quote fetched.",
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400





