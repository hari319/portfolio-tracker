"""HTTP routes for Stock Status tracking."""

import logging
from flask import Blueprint, jsonify, request

from ...errors import ValidationError
from ...stock_status import (
    add_stock_status,
    delete_stock_status,
    load_stock_statuses,
    update_stock_status,
)

logger = logging.getLogger(__name__)
stock_status_bp = Blueprint("stock_status", __name__)

@stock_status_bp.get("/api/stock-status")
def api_get_stock_status():
    items = load_stock_statuses()
    return jsonify({"ok": True, "items": items})


@stock_status_bp.post("/api/stock-status")
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


@stock_status_bp.delete("/api/stock-status/<item_id>")
def api_delete_stock_status(item_id: str):
    try:
        items = delete_stock_status(item_id)
        return jsonify({"ok": True, "items": items, "message": "Stock status removed."})
    except Exception as exc:
        logger.exception("Failed to delete stock status %s", item_id)
        return jsonify({"ok": False, "error": f"Failed to delete stock status: {exc}"}), 500


@stock_status_bp.put("/api/stock-status/<item_id>")
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
