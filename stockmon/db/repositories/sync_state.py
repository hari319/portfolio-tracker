"""Repository for the ``sync_state`` single-row table.

Replaces ``status.py``'s use of ``data/status.json``.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from .. import get_connection

logger = logging.getLogger(__name__)

_EMPTY_STATUS: dict[str, Any] = {
    "version": 0,
    "updated_at": None,
    "source": None,
    "message": "No refresh has run yet.",
    "summary": {},
}


def read_status() -> dict[str, Any]:
    """Return the current sync state as a dict matching the old JSON shape."""
    conn = get_connection()
    row = conn.execute(
        "SELECT version, updated_at, source, message, summary FROM sync_state WHERE id = 1"
    ).fetchone()
    if row is None:
        return dict(_EMPTY_STATUS)
    summary = row["summary"]
    if isinstance(summary, str):
        try:
            summary = json.loads(summary)
        except (json.JSONDecodeError, TypeError):
            summary = {}
    return {
        "version": row["version"] or 0,
        "updated_at": row["updated_at"],
        "source": row["source"],
        "message": row["message"] or "No refresh has run yet.",
        "summary": summary or {},
    }


def bump(source: str, message: str = "", summary: dict[str, Any] | None = None) -> dict[str, Any]:
    """Atomically increment the version and publish a new status.

    Uses ``version = version + 1`` — atomic at the DB level, so two
    concurrent bumps can never produce the same version number.
    """
    conn = get_connection()
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    summary_json = json.dumps(summary or {})

    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            """UPDATE sync_state
               SET version = version + 1,
                   updated_at = ?,
                   source = ?,
                   message = ?,
                   summary = ?
               WHERE id = 1""",
            (now, source, message, summary_json),
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    status = read_status()
    logger.info("Status v%s published (source=%s) %s", status["version"], source, message)
    return status
