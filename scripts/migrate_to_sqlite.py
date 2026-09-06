"""Migrate existing JSON data stores into the new SQLite databases.

This script is idempotent and re-runnable. It NEVER modifies or deletes
source JSON files.  See docs/DATA_STORAGE_MIGRATION.md §8 Step 3.

Usage:
    python scripts/migrate_to_sqlite.py            # full migration
    python scripts/migrate_to_sqlite.py --dry-run   # do everything then roll back
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from stockmon import paths
from stockmon.db import connect, open_database, open_screener_cache
from stockmon.jsonstore import read_json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("migrate")

# Track import stats
stats: dict[str, dict[str, int]] = {}


def _stat(store: str, imported: int = 0, skipped: int = 0, source: int = 0) -> None:
    """Record import statistics for the reconciliation table."""
    if store not in stats:
        stats[store] = {"source": 0, "imported": 0, "skipped": 0}
    stats[store]["source"] += source
    stats[store]["imported"] += imported
    stats[store]["skipped"] += skipped


def _safe_float(val) -> float | None:
    if val is None or val == "" or val == "None":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Importers for each JSON store → stockmon.db
# ---------------------------------------------------------------------------

def import_portfolios(conn):
    """config/portfolios.json → portfolio + portfolio_ticker tables."""
    data = read_json(paths.PORTFOLIOS_FILE, default=None)
    if data is None or not isinstance(data, dict):
        logger.warning("No portfolios.json found or invalid — skipping")
        _stat("portfolios", source=0, skipped=1)
        return

    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    total_tickers = 0

    for name, symbols in data.items():
        conn.execute(
            "INSERT OR IGNORE INTO portfolio(name, kind, created_at) VALUES (?, ?, ?)",
            (name, "personal", now),
        )
        if not isinstance(symbols, list):
            continue
        for symbol in symbols:
            symbol = str(symbol).strip()
            if not symbol:
                continue
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO portfolio_ticker(portfolio_name, symbol, added_at) VALUES (?, ?, ?)",
                    (name, symbol, now),
                )
                total_tickers += 1
            except Exception as exc:
                logger.warning("  Skipped ticker %s in %s: %s", symbol, name, exc)
                _stat("portfolios", skipped=1)

    # Also seed the LOAN portfolio for the upcoming Portfolio Tracker feature
    conn.execute(
        "INSERT OR IGNORE INTO portfolio(name, kind, created_at) VALUES (?, ?, ?)",
        ("LOAN", "loan", now),
    )

    _stat("portfolios", source=sum(len(v) for v in data.values() if isinstance(v, list)),
          imported=total_tickers)
    logger.info("Imported %d portfolios with %d tickers", len(data), total_tickers)


def import_pending_additions(conn):
    """data/pending_additions.json → pending_addition table."""
    data = read_json(paths.PENDING_ADDITIONS_FILE, default=[])
    if not isinstance(data, list):
        data = []

    imported = 0
    for entry in data:
        portfolio = entry.get("portfolio", "")
        symbol = entry.get("symbol", "")
        added_at = entry.get("added_at", datetime.now().isoformat())
        if not portfolio or not symbol:
            _stat("pending_additions", skipped=1)
            continue
        conn.execute(
            "INSERT INTO pending_addition(portfolio_name, symbol, added_at) VALUES (?, ?, ?)",
            (portfolio, symbol, added_at),
        )
        imported += 1

    _stat("pending_additions", source=len(data), imported=imported)
    logger.info("Imported %d pending additions", imported)


def import_status(conn):
    """data/status.json → sync_state table (single row, id=1).

    IMPORTANT: Preserve the current version number so SSE clients
    don't think data went backwards.
    """
    data = read_json(paths.STATUS_FILE, default=None)
    if not isinstance(data, dict):
        logger.info("No status.json found — keeping default seed")
        _stat("status", source=0, skipped=0, imported=0)
        return

    version = int(data.get("version", 0))
    summary = data.get("summary", {})
    summary_json = json.dumps(summary) if summary else "{}"

    conn.execute(
        """UPDATE sync_state
           SET version = ?, updated_at = ?, source = ?, message = ?, summary = ?
           WHERE id = 1""",
        (
            version,
            data.get("updated_at"),
            data.get("source"),
            data.get("message", ""),
            summary_json,
        ),
    )

    _stat("status", source=1, imported=1)
    logger.info("Imported status: version=%d", version)


def import_snapshot(conn):
    """data/snapshot.json → tracker_snapshot table (one row, whole JSON)."""
    data = read_json(paths.SNAPSHOT_FILE, default=None)
    if not isinstance(data, dict):
        logger.info("No snapshot.json found — skipping")
        _stat("snapshot", source=0)
        return

    generated_at = data.get("generated_at", datetime.now().isoformat())
    source = data.get("source", "import")
    payload = json.dumps(data, ensure_ascii=False, default=str)

    conn.execute(
        "INSERT INTO tracker_snapshot(generated_at, source, payload) VALUES (?, ?, ?)",
        (generated_at, source, payload),
    )

    _stat("snapshot", source=1, imported=1)
    logger.info("Imported snapshot (generated_at=%s)", generated_at)


def import_quotes_cache(conn):
    """data/quotes_cache.json → quote_cache table."""
    data = read_json(paths.QUOTES_CACHE_FILE, default={})
    if not isinstance(data, dict):
        data = {}

    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    imported = 0

    for symbol, quote in data.items():
        if not isinstance(quote, dict):
            _stat("quotes_cache", skipped=1)
            continue
        conn.execute(
            """INSERT OR REPLACE INTO quote_cache(symbol, price, currency, name, fetched_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                symbol,
                _safe_float(quote.get("price")),
                quote.get("currency"),
                quote.get("name"),
                quote.get("fetched_at", now),
            ),
        )
        imported += 1

    _stat("quotes_cache", source=len(data), imported=imported)
    logger.info("Imported %d quote cache entries", imported)


def import_stock_status(conn):
    """data/stock_status.json → stock_status table.

    Splits base/bull/bear two-element arrays into _low/_high columns.
    """
    data = read_json(paths.STOCK_STATUS_FILE, default=[])
    if not isinstance(data, list):
        data = []

    imported = 0
    for item in data:
        item_id = item.get("id", "")
        symbol = item.get("symbol", "")
        if not item_id or not symbol:
            _stat("stock_status", skipped=1)
            logger.warning("  Skipped stock status with missing id or symbol")
            continue

        base = item.get("base", ["", ""])
        bull = item.get("bull", ["", ""])
        bear = item.get("bear", ["", ""])
        if not isinstance(base, list):
            base = [str(base), ""]
        if not isinstance(bull, list):
            bull = [str(bull), ""]
        if not isinstance(bear, list):
            bear = [str(bear), ""]

        now = datetime.now().isoformat()
        conn.execute(
            """INSERT OR REPLACE INTO stock_status(
                   id, symbol, name, date_of_analysis, price_of_analysis,
                   best_entry, status, base_low, base_high,
                   bull_low, bull_high, bear_low, bear_high,
                   remarks, created_at, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                item_id,
                symbol,
                item.get("name", ""),
                item.get("date_of_analysis", now[:10]),
                _safe_float(item.get("price_of_analysis")),
                _safe_float(item.get("best_entry")),
                item.get("status", ""),
                _safe_float(base[0]) if len(base) > 0 else None,
                _safe_float(base[1]) if len(base) > 1 else None,
                _safe_float(bull[0]) if len(bull) > 0 else None,
                _safe_float(bull[1]) if len(bull) > 1 else None,
                _safe_float(bear[0]) if len(bear) > 0 else None,
                _safe_float(bear[1]) if len(bear) > 1 else None,
                item.get("remarks", ""),
                item.get("created_at", now),
                item.get("updated_at", now),
            ),
        )
        imported += 1

    _stat("stock_status", source=len(data), imported=imported)
    logger.info("Imported %d stock status entries", imported)


# ---------------------------------------------------------------------------
# Importer for screener data → screener_cache.db
# ---------------------------------------------------------------------------

# The 15 hot fields that get promoted to real columns
HOT_FIELDS = (
    "close", "open", "high", "low", "prev_close", "pct_change",
    "volume", "delivery_qty", "delivery_percent", "supertrend_dir",
    "sma_20", "close_near_high_pct", "volume_ratio_20", "range_pct_5",
    "series",
)


def import_screener_data(sconn):
    """data/screener/screener_*.json → screener_day + screener_row tables.

    Commits per day (not per row) for performance.
    """
    screener_dir = paths.SCREENER_DIR
    if not screener_dir.exists():
        logger.info("No screener directory found — skipping")
        _stat("screener", source=0)
        return

    json_files = sorted(screener_dir.glob("screener_*.json"))
    # Skip the multi_day_analysis_cache.json (derived data, will be recomputed)
    json_files = [f for f in json_files if "multi_day" not in f.name]

    if not json_files:
        logger.info("No screener files found — skipping")
        _stat("screener", source=0)
        return

    total_days = 0
    total_rows = 0
    t0 = time.time()

    for fpath in json_files:
        date_key = fpath.stem.replace("screener_", "")
        try:
            with open(fpath, "r", encoding="utf-8") as fp:
                data = json.load(fp)
        except Exception as exc:
            logger.warning("  Could not parse %s: %s — skipping", fpath.name, exc)
            _stat("screener", skipped=1)
            continue

        if not isinstance(data, dict):
            _stat("screener", skipped=1)
            continue

        items = data.get("items", [])
        if not items:
            _stat("screener", skipped=1)
            continue

        # Extract trade_date from the data or filename
        trade_date = data.get("date", date_key)
        total_items = data.get("total", len(items))
        timeframe = data.get("timeframe", "daily")
        source = data.get("source", "")

        # Build envelope (non-item top-level keys)
        envelope = {k: v for k, v in data.items() if k != "items"}
        envelope_json = json.dumps(envelope, ensure_ascii=False, default=str)

        now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

        sconn.execute("BEGIN IMMEDIATE")
        try:
            # Upsert the day row
            sconn.execute(
                """INSERT INTO screener_day(trade_date, fetched_at, total_items, timeframe, source, envelope)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(trade_date) DO UPDATE SET
                       fetched_at = excluded.fetched_at,
                       total_items = excluded.total_items,
                       envelope = excluded.envelope""",
                (trade_date, now, total_items, timeframe, source, envelope_json),
            )

            # Delete existing rows for this date
            sconn.execute("DELETE FROM screener_row WHERE trade_date = ?", (trade_date,))

            # Batch insert rows
            row_data = []
            for item in items:
                symbol = item.get("symbol")
                if not symbol:
                    continue

                # Build payload: everything NOT in hot fields or symbol
                payload = {k: v for k, v in item.items() if k not in HOT_FIELDS and k != "symbol"}
                payload_json = json.dumps(payload, ensure_ascii=False, default=str)

                row_data.append((
                    trade_date,
                    symbol,
                    _safe_float(item.get("close")),
                    _safe_float(item.get("open")),
                    _safe_float(item.get("high")),
                    _safe_float(item.get("low")),
                    _safe_float(item.get("prev_close")),
                    _safe_float(item.get("pct_change")),
                    _safe_float(item.get("volume")),
                    _safe_float(item.get("delivery_qty")),
                    _safe_float(item.get("delivery_percent")),
                    str(item.get("supertrend_dir", "")) if item.get("supertrend_dir") is not None else None,
                    _safe_float(item.get("sma_20")),
                    _safe_float(item.get("close_near_high_pct")),
                    _safe_float(item.get("volume_ratio_20")),
                    _safe_float(item.get("range_pct_5")),
                    str(item.get("series", "")) if item.get("series") is not None else None,
                    payload_json,
                ))

            sconn.executemany(
                """INSERT INTO screener_row(
                       trade_date, symbol, close, open, high, low, prev_close,
                       pct_change, volume, delivery_qty, delivery_percent,
                       supertrend_dir, sma_20, close_near_high_pct,
                       volume_ratio_20, range_pct_5, series, payload
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                row_data,
            )

            sconn.execute("COMMIT")
            total_days += 1
            total_rows += len(row_data)
            logger.info("  Imported %s: %d stocks", trade_date, len(row_data))

        except Exception as exc:
            sconn.execute("ROLLBACK")
            logger.error("  Failed importing %s: %s", trade_date, exc)
            _stat("screener", skipped=1)

    elapsed = time.time() - t0
    _stat("screener", source=len(json_files), imported=total_days)

    # Report screener DB size
    db_path = paths.SCREENER_DB_FILE
    if db_path.exists():
        size_mb = db_path.stat().st_size / (1024 * 1024)
        json_size_mb = sum(f.stat().st_size for f in json_files) / (1024 * 1024)
        logger.info(
            "Screener import complete: %d days, %d total rows in %.1fs",
            total_days, total_rows, elapsed,
        )
        logger.info(
            "Size comparison: JSON files = %.1f MB → SQLite DB = %.1f MB (%.0f%% reduction)",
            json_size_mb, size_mb, (1 - size_mb / json_size_mb) * 100 if json_size_mb > 0 else 0,
        )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def print_reconciliation():
    """Print the final reconciliation table."""
    print()
    print("=" * 70)
    print("RECONCILIATION TABLE")
    print("=" * 70)
    print(f"{'Store':<25} {'Source':>8} {'Imported':>8} {'Skipped':>8}")
    print("-" * 70)
    for store, counts in stats.items():
        print(f"{store:<25} {counts['source']:>8} {counts['imported']:>8} {counts['skipped']:>8}")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Migrate JSON data to SQLite databases.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Do all work, then roll back at the end.")
    args = parser.parse_args()

    if args.dry_run:
        logger.info("=== DRY RUN MODE — all changes will be rolled back ===")

    # Clean slate for databases (delete if they exist for fresh import)
    for db_path in (paths.DB_FILE, paths.SCREENER_DB_FILE):
        if db_path.exists():
            logger.info("Removing existing %s for fresh import", db_path.name)
            db_path.unlink(missing_ok=True)
            # Also remove WAL/SHM sidecars
            for suffix in ("-wal", "-shm"):
                sidecar = db_path.parent / (db_path.name + suffix)
                sidecar.unlink(missing_ok=True)

    # Create and migrate databases
    logger.info("Creating durable database (stockmon.db)...")
    conn = open_database(paths.DB_FILE)

    logger.info("Creating screener cache database (screener_cache.db)...")
    sconn = open_screener_cache(paths.SCREENER_DB_FILE)

    # Import into durable DB (one big transaction for atomicity)
    logger.info("")
    logger.info("=== Importing into stockmon.db ===")
    conn.execute("BEGIN IMMEDIATE")
    try:
        import_portfolios(conn)
        import_pending_additions(conn)
        import_status(conn)
        import_snapshot(conn)
        import_quotes_cache(conn)
        import_stock_status(conn)

        if args.dry_run:
            conn.execute("ROLLBACK")
            logger.info("DRY RUN: Rolled back all durable DB changes")
        else:
            conn.execute("COMMIT")
            logger.info("Committed all durable DB imports")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    # Import screener data (each day is its own transaction)
    logger.info("")
    logger.info("=== Importing into screener_cache.db ===")
    import_screener_data(sconn)

    if args.dry_run:
        # For screener, the data was committed per-day, so we'd need to
        # delete it all to simulate a dry run
        sconn.execute("DELETE FROM screener_row")
        sconn.execute("DELETE FROM screener_day")
        logger.info("DRY RUN: Cleaned up screener DB changes")

    conn.close()
    sconn.close()

    print_reconciliation()

    # Final verification: reopen and check
    if not args.dry_run:
        print()
        logger.info("=== Final Verification ===")
        vconn = connect(paths.DB_FILE)
        for table in ("portfolio", "portfolio_ticker", "pending_addition",
                       "sync_state", "tracker_snapshot", "quote_cache", "stock_status"):
            count = vconn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            logger.info("  %s: %d rows", table, count)
        vconn.close()

        vsconn = connect(paths.SCREENER_DB_FILE)
        for table in ("screener_day", "screener_row"):
            count = vsconn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            logger.info("  %s: %d rows", table, count)
        vsconn.close()

        print()
        logger.info("=== Migration Complete ===")


if __name__ == "__main__":
    main()
