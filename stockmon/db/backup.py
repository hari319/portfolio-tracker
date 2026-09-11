"""Consistent backup of the durable database (stockmon.db).

Uses ``sqlite3.Connection.backup()`` — the Online Backup API — to produce
a transactionally consistent snapshot while the database is in use.

See docs/DATA_STORAGE_MIGRATION.md §6.2.

IMPORTANT: Only ``stockmon.db`` is ever backed up.  The screener cache is
disposable and recovered via re-fetch from the upstream API (§0.1).
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import re
import shutil
import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .. import paths

logger = logging.getLogger(__name__)


def create_backup(
    db_path: Path | None = None,
    backup_dir: Path | None = None,
) -> Path:
    """Create a verified, compressed backup of the durable database.

    Returns the path to the ``.db.gz`` file.

    Steps:
      1. ``Connection.backup()`` → consistent page-by-page copy
      2. ``PRAGMA integrity_check`` on the snapshot (not the live DB)
      3. ``gzip`` compress
      4. Append to ``manifest.json``
    """
    db_path = db_path or paths.DB_FILE
    backup_dir = backup_dir or paths.BACKUP_DIR

    # Only the durable database is backed up — never the screener cache.
    if db_path != paths.DB_FILE:
        raise ValueError(f"Only the durable database is backed up, not {db_path}")

    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")

    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "snapshot.db"

        # 1. Online backup (safe while Flask/scheduler are running)
        src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        dst = sqlite3.connect(str(raw))
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()

        # 2. Verify the SNAPSHOT, not the live DB
        check = sqlite3.connect(str(raw))
        result = check.execute("PRAGMA integrity_check").fetchone()[0]
        check.close()
        if result != "ok":
            raise RuntimeError(f"Backup failed integrity check: {result}")

        # 3. Compress
        final = backup_dir / f"stockmon-{stamp}.db.gz"
        with open(raw, "rb") as f_in, gzip.open(final, "wb", compresslevel=6) as f_out:
            shutil.copyfileobj(f_in, f_out)

        # Compute checksum and sizes for the manifest
        uncompressed_size = raw.stat().st_size
        sha256 = hashlib.sha256(final.read_bytes()).hexdigest()

        # Get schema version and row counts
        check = sqlite3.connect(str(raw))
        user_version = check.execute("PRAGMA user_version").fetchone()[0]
        counts: dict[str, int] = {}
        for table in ("portfolio", "portfolio_ticker", "stock_status", "quote_cache",
                       "sync_state", "tracker_snapshot", "pending_addition"):
            try:
                cnt = check.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                counts[table] = cnt
            except sqlite3.OperationalError:
                pass
        check.close()

    # 4. Append to manifest
    _append_manifest(backup_dir, final, db_path, stamp,
                     uncompressed_size, sha256, user_version, counts)

    logger.info("Backup created: %s (%.1f KB compressed)", final.name,
                final.stat().st_size / 1024)
    return final


def _append_manifest(
    backup_dir: Path,
    backup_file: Path,
    db_path: Path,
    stamp: str,
    uncompressed_size: int,
    sha256: str,
    user_version: int,
    row_counts: dict[str, int],
) -> None:
    """Record this backup in manifest.json."""
    manifest_path = backup_dir / "manifest.json"
    entries: list[dict[str, Any]] = []
    if manifest_path.exists():
        try:
            entries = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            entries = []

    entries.append({
        "filename": backup_file.name,
        "timestamp": stamp,
        "source_db": str(db_path),
        "compressed_size": backup_file.stat().st_size,
        "uncompressed_size": uncompressed_size,
        "sha256": sha256,
        "schema_version": user_version,
        "row_counts": row_counts,
    })

    manifest_path.write_text(
        json.dumps(entries, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def parse_backup_timestamp(filename: str) -> datetime | None:
    """Extract datetime from backup filename (supports standard, legacy, and date-only formats)."""
    # 1. Standard format: YYYY-MM-DD_HHMMSS
    m = re.search(r"(\d{4}-\d{2}-\d{2})_(\d{2})(\d{2})(\d{2})", filename)
    if m:
        try:
            return datetime.strptime(f"{m.group(1)}_{m.group(2)}{m.group(3)}{m.group(4)}", "%Y-%m-%d_%H%M%S")
        except ValueError:
            pass
    # 2. Legacy format: YYYYMMDD_HHMMSS
    m2 = re.search(r"(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})", filename)
    if m2:
        try:
            return datetime.strptime(f"{m2.group(1)}-{m2.group(2)}-{m2.group(3)}_{m2.group(4)}{m2.group(5)}{m2.group(6)}", "%Y-%m-%d_%H%M%S")
        except ValueError:
            pass
    # 3. Date only: YYYY-MM-DD
    m3 = re.search(r"(\d{4}-\d{2}-\d{2})", filename)
    if m3:
        try:
            return datetime.strptime(m3.group(1), "%Y-%m-%d")
        except ValueError:
            pass
    return None


def prune_manifest(backup_dir: Path, cutoff: datetime | None = None) -> int:
    """Prune manifest entries that are older than cutoff or whose files no longer exist on disk."""
    manifest_path = backup_dir / "manifest.json"
    if not manifest_path.exists():
        return 0

    try:
        entries = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(entries, list):
            return 0
    except (json.JSONDecodeError, OSError):
        return 0

    retained = []
    removed = 0
    for e in entries:
        fname = e.get("filename")
        if not fname:
            removed += 1
            continue
        file_path = backup_dir / fname
        if not file_path.exists():
            removed += 1
            continue
        if cutoff:
            ts_str = e.get("timestamp")
            dt = parse_backup_timestamp(ts_str or fname)
            if dt and dt < cutoff:
                removed += 1
                continue
        retained.append(e)

    if removed > 0 or len(retained) != len(entries):
        manifest_path.write_text(
            json.dumps(retained, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    return removed


def rotate_backups(
    backup_dir: Path | None = None,
    retention_days: int = 5,
    max_backups: int = 5,
    *args: Any,
    **kwargs: Any,
) -> int:
    """Apply retention policy to backup files.

    1. Removes all settings-*.json files (settings backups are disabled).
    2. Removes backups older than ``retention_days`` (default: 5 days).
    3. Strictly enforces ``max_backups`` (default: 5 files) so there are never more than 5 stockmon files.
    4. Synchronizes manifest.json with retained backups on disk.

    Returns the number of files deleted.
    """
    backup_dir = backup_dir or paths.BACKUP_DIR
    if not backup_dir.exists():
        return 0

    deleted = 0

    # 1. Purge all settings-*.json files (settings backups are disabled)
    for sf in backup_dir.glob("settings-*.json"):
        try:
            sf.unlink()
            deleted += 1
        except OSError as exc:
            logger.warning("Could not delete settings file %s: %s", sf, exc)

    # 2. Gather stockmon backup files
    patterns = [
        "stockmon-*.db.gz",
        "stockmon_pre_ticker_update_*.db",
        "*.db.gz",
    ]
    seen_files = set()
    stockmon_files = []
    for pat in patterns:
        for f in backup_dir.glob(pat):
            if f.name != "manifest.json" and f not in seen_files:
                seen_files.add(f)
                stockmon_files.append(f)

    # Parse timestamps and sort newest first
    file_dt_pairs = []
    for f in stockmon_files:
        dt = parse_backup_timestamp(f.name)
        if dt is None:
            try:
                dt = datetime.fromtimestamp(f.stat().st_mtime)
            except OSError:
                dt = datetime.min
        file_dt_pairs.append((f, dt))

    # Sort descending (newest first)
    file_dt_pairs.sort(key=lambda pair: pair[1], reverse=True)

    cutoff = datetime.now() - timedelta(days=retention_days)

    # 3. Retain at most max_backups that are within the retention window
    retained_count = 0
    for f, dt in file_dt_pairs:
        # If older than retention cutoff OR already reached max_backups limit:
        if (dt and dt < cutoff) or retained_count >= max_backups:
            try:
                f.unlink()
                deleted += 1
            except OSError as exc:
                logger.warning("Could not delete old backup %s: %s", f, exc)
        else:
            retained_count += 1

    # 4. Prune screener subfolder if it exists
    screener_dir = backup_dir / "screener"
    if screener_dir.exists():
        for sf in screener_dir.glob("*"):
            s_dt = parse_backup_timestamp(sf.name)
            if s_dt is None:
                try:
                    s_dt = datetime.fromtimestamp(sf.stat().st_mtime)
                except OSError:
                    s_dt = None
            if s_dt and s_dt < cutoff:
                try:
                    sf.unlink()
                    deleted += 1
                except OSError:
                    pass

    # 5. Synchronize manifest.json with the files that actually remain
    prune_manifest(backup_dir, cutoff=cutoff)

    if deleted:
        logger.info("Rotated %d old backup file(s); retained %d", deleted, retained_count)
    return deleted


def create_screener_backup(
    screener_db_path: Path | None = None,
    backup_dir: Path | None = None,
) -> dict[str, Any]:
    """Create a verified, compressed backup of the Screener database (screener_cache.db).

    Returns metadata dictionary including path, filename, size, and timestamp.
    """
    screener_db_path = screener_db_path or paths.SCREENER_DB_FILE
    if not screener_db_path.exists():
        raise FileNotFoundError(f"Screener database not found at {screener_db_path}")

    base_backup_dir = backup_dir or paths.BACKUP_DIR
    screener_backup_dir = base_backup_dir / "screener"
    screener_backup_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    final_gz = screener_backup_dir / f"screener-{stamp}.db.gz"

    with tempfile.TemporaryDirectory() as tmp:
        temp_db = Path(tmp) / "screener_snapshot.db"
        # 1. Use SQLite Online Backup API
        src_conn = sqlite3.connect(str(screener_db_path))
        dst_conn = sqlite3.connect(str(temp_db))
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
            src_conn.close()

        # 2. Check integrity
        chk = sqlite3.connect(str(temp_db))
        res = chk.execute("PRAGMA integrity_check").fetchone()[0]
        chk.close()
        if res != "ok":
            raise RuntimeError(f"Screener backup failed integrity check: {res}")

        uncompressed_size = temp_db.stat().st_size

        # 3. Compress with gzip
        with open(temp_db, "rb") as f_in, gzip.open(final_gz, "wb", compresslevel=6) as f_out:
            shutil.copyfileobj(f_in, f_out)

    # 4. Also copy screener_cache.json if present
    if paths.SCREENER_CACHE_FILE.exists():
        settings_dst = screener_backup_dir / f"screener_cache-{stamp}.json"
        shutil.copy2(paths.SCREENER_CACHE_FILE, settings_dst)

    # 5. Apply 5-day retention
    rotate_backups(backup_dir=base_backup_dir, retention_days=5)

    compressed_size = final_gz.stat().st_size
    size_mb = round(compressed_size / (1024 * 1024), 2)
    logger.info("Screener backup created: %s (%.2f MB compressed)", final_gz.name, size_mb)

    return {
        "filename": final_gz.name,
        "path": str(final_gz.resolve()),
        "directory": str(screener_backup_dir.resolve()),
        "size_bytes": compressed_size,
        "size_mb": size_mb,
        "uncompressed_size_bytes": uncompressed_size,
        "timestamp": stamp,
    }


def list_backups(backup_dir: Path | None = None) -> list[dict[str, Any]]:
    """List available backups from the manifest."""
    backup_dir = backup_dir or paths.BACKUP_DIR
    manifest_path = backup_dir / "manifest.json"
    if not manifest_path.exists():
        return []
    try:
        entries = json.loads(manifest_path.read_text(encoding="utf-8"))
        return entries if isinstance(entries, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def restore_backup(
    backup_filename: str,
    backup_dir: Path | None = None,
    target_db_path: Path | None = None,
) -> bool:
    """Restore database from a given .db.gz backup file.

    1. Verify SHA-256 against manifest (if present)
    2. Decompress to temp location
    3. Run PRAGMA integrity_check on the decompressed DB
    4. Quarantine existing DB if present
    5. Move decompressed DB into place
    6. Run migrations
    """
    backup_dir = backup_dir or paths.BACKUP_DIR
    target_db_path = target_db_path or paths.DB_FILE

    backup_file = backup_dir / backup_filename
    if not backup_file.exists():
        raise FileNotFoundError(f"Backup file not found: {backup_file}")

    # 1. Verify SHA-256 against manifest
    manifest_entries = list_backups(backup_dir)
    manifest_match = next((e for e in manifest_entries if e.get("filename") == backup_filename), None)
    if manifest_match and "sha256" in manifest_match:
        actual_sha = hashlib.sha256(backup_file.read_bytes()).hexdigest()
        if actual_sha != manifest_match["sha256"]:
            raise ValueError(f"Checksum mismatch for {backup_filename}: expected {manifest_match['sha256']}, got {actual_sha}")

    with tempfile.TemporaryDirectory() as tmp:
        temp_db = Path(tmp) / "restored.db"
        with gzip.open(backup_file, "rb") as f_in, open(temp_db, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)

        # 2. Check integrity
        check = sqlite3.connect(str(temp_db))
        res = check.execute("PRAGMA integrity_check").fetchone()[0]
        check.close()
        if res != "ok":
            raise RuntimeError(f"Restored DB failed integrity check: {res}")

        # 3. Close any active thread-local connections to release Windows file locks
        from . import close_connections, connect
        close_connections()

        # 4. Safely restore into target_db_path
        # Using SQLite Online Backup API into target restores transactionally without lock collisions
        dst_conn = connect(target_db_path)
        src_conn = sqlite3.connect(str(temp_db))
        try:
            src_conn.backup(dst_conn)
        finally:
            src_conn.close()
            dst_conn.close()
            close_connections()

    # 5. Restore settings if present
    settings_stamp = backup_filename.replace("stockmon-", "settings-").replace(".db.gz", ".json")
    backup_settings = backup_dir / settings_stamp
    if backup_settings.exists():
        shutil.copy2(backup_settings, paths.SETTINGS_FILE)

    # 6. Apply any pending migrations
    from .migrations import migrate
    from . import connect
    conn = connect(target_db_path)
    migrate(conn)
    conn.close()

    logger.info("Successfully restored %s to %s", backup_filename, target_db_path)
    return True
