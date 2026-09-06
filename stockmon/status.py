"""Shared status used to signal "new data available".

The scheduled task and the Flask app are separate processes, so they coordinate
through the ``sync_state`` table in ``stockmon.db``. Every successful refresh
increments ``version``; the browser watches that number over SSE (or polling)
and reloads the tables when it changes.

This module now delegates to ``stockmon.db.repositories.sync_state`` for
all persistence — SQLite WAL mode provides proper cross-process safety
that the old JSON-based approach lacked.
"""

from __future__ import annotations

from typing import Any

from .db.repositories import sync_state as _repo


def read_status() -> dict[str, Any]:
    return _repo.read_status()


def bump(source: str, message: str = "", summary: dict[str, Any] | None = None) -> dict[str, Any]:
    """Publish a new data version. Returns the written status document."""
    return _repo.bump(source, message, summary)
