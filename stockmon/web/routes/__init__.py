from flask import Blueprint, jsonify
from ...errors import DataFetchError, ValidationError

bp = Blueprint("main", __name__)

@bp.app_errorhandler(ValidationError)
def _handle_validation_error(exc: ValidationError):
    return jsonify({"ok": False, "error": str(exc)}), 400

@bp.app_errorhandler(DataFetchError)
def _handle_data_fetch_error(exc: DataFetchError):
    return jsonify({"ok": False, "error": str(exc)}), 502

from .tracker import tracker_bp
from .stock_status import stock_status_bp
from .screener import screener_bp
from .backup import backup_bp
from .portfolio_tracker import portfolio_tracker_bp
from .swing_tracker import swing_tracker_bp

bp.register_blueprint(tracker_bp)
bp.register_blueprint(stock_status_bp)
bp.register_blueprint(screener_bp)
bp.register_blueprint(backup_bp)
bp.register_blueprint(portfolio_tracker_bp)
bp.register_blueprint(swing_tracker_bp)
