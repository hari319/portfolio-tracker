"""SQLite database layer for the Daily Updater application.

Two database files, split by replaceability (see docs/DATA_STORAGE_MIGRATION.md §0.1):

- ``data/stockmon.db`` — durable, backed up, tiny (portfolios, holdings, status, etc.)
- ``data/screener_cache.db`` — disposable, never backed up, large (screener history)

Every connection is configured with WAL mode, busy_timeout=30s, foreign keys ON,
and synchronous=NORMAL. See §4.1 for rationale.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from .. import paths

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thread-local connection storage
# ---------------------------------------------------------------------------

_local = threading.local()


def connect(db_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection with the project's standard pragmas.

    Settings applied (in order):
      - ``journal_mode = WAL`` — readers never block the writer
      - ``busy_timeout = 30000`` — wait up to 30 s instead of raising SQLITE_BUSY
      - ``foreign_keys = ON`` — must be set every connection (SQLite default is OFF)
      - ``synchronous = NORMAL`` — safe with WAL; much faster than FULL
      - ``isolation_level = None`` — explicit transaction control (BEGIN/COMMIT)
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


# ---------------------------------------------------------------------------
# Thread-local getters (Flask is threaded=True)
# ---------------------------------------------------------------------------

def get_connection() -> sqlite3.Connection:
    """Return the thread-local connection to the durable database."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = connect(paths.DB_FILE)
        _local.conn = conn
    return conn


def get_screener_connection() -> sqlite3.Connection:
    """Return the thread-local connection to the disposable screener cache."""
    conn = getattr(_local, "screener_conn", None)
    if conn is None:
        conn = connect(paths.SCREENER_DB_FILE)
        _local.screener_conn = conn
    return conn


def close_connections() -> None:
    """Close any thread-local connections (call at thread/process shutdown)."""
    for attr in ("conn", "screener_conn"):
        conn = getattr(_local, attr, None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
            setattr(_local, attr, None)


# ---------------------------------------------------------------------------
# Database lifecycle — startup health checks
# ---------------------------------------------------------------------------

class DatabaseMissingError(Exception):
    """The durable database file is missing and backups are available."""


class DatabaseCorruptError(Exception):
    """The durable database file failed integrity checks."""


def _quarantine(db_path: Path) -> None:
    """Rename a corrupt database aside, preserving it for possible recovery."""
    import datetime as _dt
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = db_path.with_suffix(f".corrupt-{stamp}")
    try:
        db_path.rename(dest)
        logger.warning("Quarantined corrupt database to %s", dest)
    except OSError as exc:
        logger.error("Could not quarantine %s: %s", db_path, exc)


def _backups_available() -> bool:
    """Check whether any backup files exist in the backup directory."""
    backup_dir = paths.BACKUP_DIR
    if not backup_dir.exists():
        return False
    return any(backup_dir.glob("stockmon-*.db.gz"))


def open_database(db_path: Path | None = None) -> sqlite3.Connection:
    """Open the durable database with health checks and migrations.

    - If the file is missing and backups exist → raise ``DatabaseMissingError``
      so the UI can offer a restore.
    - If the file is missing and no backups → create a fresh database (first run).
    - If the file exists but is corrupt → quarantine and raise ``DatabaseCorruptError``.
    - Otherwise → run pending migrations and return.
    """
    from .migrations import migrate

    db_path = db_path or paths.DB_FILE
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if not db_path.exists():
        if _backups_available():
            raise DatabaseMissingError(
                f"Database {db_path} is missing but backups are available. "
                "Please restore from a backup."
            )
        # Genuine first run
        conn = connect(db_path)
        migrate(conn)
        logger.info("Created new durable database at %s", db_path)
        return conn

    conn = connect(db_path)
    result = conn.execute("PRAGMA quick_check").fetchone()[0]
    if result != "ok":
        conn.close()
        _quarantine(db_path)
        raise DatabaseCorruptError(
            f"Database {db_path} failed integrity check: {result}. "
            "The corrupt file has been preserved."
        )
    migrate(conn)
    return conn


def open_screener_cache(db_path: Path | None = None) -> sqlite3.Connection:
    """Open the disposable screener cache — missing or corrupt is a non-event.

    A corrupt cache is silently discarded and recreated. This database is
    never backed up; recovery is a re-fetch from the upstream API.
    """
    from .migrations import migrate_screener

    db_path = db_path or paths.SCREENER_DB_FILE
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if db_path.exists():
        conn = connect(db_path)
        result = conn.execute("PRAGMA quick_check").fetchone()[0]
        if result == "ok":
            migrate_screener(conn)
            return conn
        conn.close()
        logger.warning("Screener cache corrupt — discarding and rebuilding")
        db_path.unlink(missing_ok=True)
        # Also remove WAL/SHM sidecars
        for suffix in (".db-wal", ".db-shm"):
            sidecar = db_path.with_suffix(suffix)
            sidecar.unlink(missing_ok=True)

    conn = connect(db_path)
    migrate_screener(conn)
    logger.info("Created new screener cache at %s", db_path)
    return conn
