"""Schema versioning and migrations for both databases.

Each database tracks its own version via ``PRAGMA user_version``.
Migrations are append-only — never edit a shipped migration.
Each migration runs inside a single IMMEDIATE transaction so a failure
leaves the version untouched and the database unchanged.

See docs/DATA_STORAGE_MIGRATION.md §5.6.

NOTE: ``executescript()`` auto-commits any pending transaction and then runs
each statement in its own implicit transaction.  Therefore, migrations that
use ``executescript`` handle transactions internally — we wrap the
``PRAGMA user_version`` update in its own small transaction afterward.
For migrations that use ``execute()`` (e.g. data-manipulation migrations),
we use explicit ``BEGIN IMMEDIATE … COMMIT``.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

_SCHEMA_DIR = Path(__file__).resolve().parent


def _read_sql(filename: str) -> str:
    """Read a .sql file from the db package directory."""
    return (_SCHEMA_DIR / filename).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Durable database (stockmon.db) migrations
# ---------------------------------------------------------------------------

def _v1_initial_schema(conn: sqlite3.Connection) -> None:
    """Create all Group 1 tables (§5.2) from the SQL file.

    Uses executescript which handles its own transactions internally.
    """
    conn.executescript(_read_sql("schema_v1.sql"))


def _v2_portfolio_tracker(conn: sqlite3.Connection) -> None:
    """Create Portfolio Tracker tables (schema_v2.sql)."""
    conn.executescript(_read_sql("schema_v2.sql"))


def _v3_invested_amount(conn: sqlite3.Connection) -> None:
    """Add invested_amount to buy_lot to support manual cost basis/demergers."""
    try:
        conn.execute("ALTER TABLE buy_lot ADD COLUMN invested_amount REAL")
    except Exception:
        pass


def _v4_stock_name(conn: sqlite3.Connection) -> None:
    """Add stock_name to holding table and backfill from scheme_name."""
    try:
        conn.execute("ALTER TABLE holding ADD COLUMN stock_name TEXT")
    except Exception:
        pass
    try:
        conn.execute(
            "UPDATE holding SET stock_name = scheme_name "
            "WHERE (stock_name IS NULL OR stock_name = '') AND scheme_name IS NOT NULL AND scheme_name != ''"
        )
    except Exception:
        pass


def _v5_swing_tracker(conn: sqlite3.Connection) -> None:
    """Create swing_tracker and swing_tracker_source tables (schema_v5.sql)."""
    conn.executescript(_read_sql("schema_v5.sql"))
    try:
        conn.execute("DELETE FROM swing_tracker_source WHERE name IN ('Big Breaking Wire', 'Breakout Master')")
    except Exception:
        pass


# Append-only list: (version_number, callable).
# NEVER edit or renumber a shipped migration.
MIGRATIONS: list[tuple[int, callable]] = [
    (1, _v1_initial_schema),
    (2, _v2_portfolio_tracker),
    (3, _v3_invested_amount),
    (4, _v4_stock_name),
    (5, _v5_swing_tracker),
]


def migrate(conn: sqlite3.Connection) -> None:
    """Run pending migrations on the durable database (stockmon.db).

    Each migration function runs its DDL (possibly via executescript which
    manages its own commits).  After the migration function completes
    successfully, we update user_version in a separate small transaction.
    """
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    for version, apply_fn in MIGRATIONS:
        if version > current:
            apply_fn(conn)
            # Update the version in its own transaction
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(f"PRAGMA user_version = {version}")
            conn.execute("COMMIT")
            logger.info("Applied durable-DB migration v%d", version)


# ---------------------------------------------------------------------------
# Screener cache database (screener_cache.db) migrations
# ---------------------------------------------------------------------------

def _screener_v1_initial_schema(conn: sqlite3.Connection) -> None:
    """Create the screener tables (§5.3) from the SQL file."""
    conn.executescript(_read_sql("schema_screener.sql"))


SCREENER_MIGRATIONS: list[tuple[int, callable]] = [
    (1, _screener_v1_initial_schema),
]


def migrate_screener(conn: sqlite3.Connection) -> None:
    """Run pending migrations on the screener cache database."""
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    for version, apply_fn in SCREENER_MIGRATIONS:
        if version > current:
            apply_fn(conn)
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(f"PRAGMA user_version = {version}")
            conn.execute("COMMIT")
            logger.info("Applied screener-DB migration v%d", version)
