"""HTTP routes for Backup & Restore."""

import logging
from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)
backup_bp = Blueprint("backup", __name__)

@backup_bp.post("/api/backup/create")
def api_backup_create():
    """Trigger an immediate backup of stockmon.db."""
    from ...db.backup import create_backup, rotate_backups
    try:
        path = create_backup()
        rotate_backups()
        return jsonify({"ok": True, "filename": path.name, "message": "Backup created successfully."})
    except Exception as exc:
        logger.exception("Backup failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@backup_bp.get("/api/backup/list")
def api_backup_list():
    """List all available backups."""
    from ...db.backup import list_backups
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


@backup_bp.post("/api/backup/restore")
def api_backup_restore():
    """Restore durable DB from selected backup."""
    payload = request.get_json(silent=True) or {}
    filename = payload.get("filename", "").strip()
    if not filename:
        return jsonify({"ok": False, "error": "Filename is required"}), 400

    from ...db.backup import restore_backup
    try:
        restore_backup(filename)
        return jsonify({"ok": True, "message": f"Successfully restored {filename}."})
    except Exception as exc:
        logger.exception("Restore failed")
        return jsonify({"ok": False, "error": str(exc)}), 500
