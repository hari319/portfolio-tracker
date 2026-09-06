"""Repository for the ``tracker_snapshot`` table.

Replaces ``service.py``'s use of ``data/snapshot.json``.
The snapshot is stored as an opaque JSON blob — its shape is coupled
to ``_render_tables()`` and there is no benefit to normalizing it.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .. import get_connection

logger = logging.getLogger(__name__)


def load_latest_snapshot() -> dict[str, Any] | None:
    """Return the most recent snapshot payload, or None."""
    conn = get_connection()
    row = conn.execute(
        "SELECT payload FROM tracker_snapshot ORDER BY generated_at DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    try:
        return json.loads(row["payload"])
    except (json.JSONDecodeError, TypeError):
        return None


def save_snapshot(snapshot: dict[str, Any]) -> None:
    """Persist a new snapshot.  Keeps history (last N rows)."""
    conn = get_connection()
    generated_at = snapshot.get("generated_at", "")
    source = snapshot.get("source", "")
    payload = json.dumps(snapshot, ensure_ascii=False, default=str)
    conn.execute(
        "INSERT INTO tracker_snapshot(generated_at, source, payload) VALUES (?, ?, ?)",
        (generated_at, source, payload),
    )
    # Keep last 30 snapshots
    conn.execute(
        """DELETE FROM tracker_snapshot
           WHERE id NOT IN (
               SELECT id FROM tracker_snapshot ORDER BY generated_at DESC LIMIT 30
           )"""
    )
