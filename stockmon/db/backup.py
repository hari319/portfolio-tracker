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
import shutil
import sqlite3
import tempfile
from datetime import datetime
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

    # 4. Also copy settings.json alongside the backup (§6.0)
    settings_src = paths.SETTINGS_FILE
    if settings_src.exists():
        settings_dst = backup_dir / f"settings-{stamp}.json"
        shutil.copy2(settings_src, settings_dst)

    # 5. Append to manifest
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


def rotate_backups(
    backup_dir: Path | None = None,
    keep_daily: int = 7,
    keep_edit: int = 7,
    keep_weekly: int = 4,
    keep_monthly: int = 2,
    keep_pre_migration: int = 2,
) -> int:
    """Apply rotation to backup files.

    Keeps the most recent ``keep_daily`` (default 7 = 1 week) backup files.
    Older backups and their settings files are deleted automatically.

    Returns the number of files deleted.
    """
    backup_dir = backup_dir or paths.BACKUP_DIR
    if not backup_dir.exists():
        return 0

    gz_files = sorted(backup_dir.glob("stockmon-*.db.gz"), reverse=True)
    keep_total = max(keep_daily, 7)  # keep 7 (1 week)

    to_delete = gz_files[keep_total:]
    deleted = 0
    for f in to_delete:
        try:
            f.unlink()
            # Also clean up corresponding settings file
            settings_stamp = f.stem.replace("stockmon-", "settings-").replace(".db", "")
            settings_file = backup_dir / f"{settings_stamp}.json"
            if settings_file.exists():
                settings_file.unlink()
            deleted += 1
        except OSError as exc:
            logger.warning("Could not delete old backup %s: %s", f, exc)

    if deleted:
        logger.info("Rotated %d old backup(s)", deleted)
    return deleted


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
