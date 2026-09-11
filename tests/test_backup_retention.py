"""Tests for backup retention (5-day rolling policy) and Screener manual backup."""

import gzip
import json
import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from stockmon.db.backup import (
    create_screener_backup,
    parse_backup_timestamp,
    prune_manifest,
    rotate_backups,
)


def test_parse_backup_timestamp():
    # 1. Standard format: stockmon-YYYY-MM-DD_HHMMSS.db.gz
    dt1 = parse_backup_timestamp("stockmon-2026-09-10_114500.db.gz")
    assert dt1 == datetime(2026, 9, 10, 11, 45, 0)

    # 2. Settings standard format: settings-YYYY-MM-DD_HHMMSS.json
    dt2 = parse_backup_timestamp("settings-2026-09-09_143008.json")
    assert dt2 == datetime(2026, 9, 9, 14, 30, 8)

    # 3. Legacy safety format: stockmon_pre_ticker_update_20260908_163436.db
    dt3 = parse_backup_timestamp("stockmon_pre_ticker_update_20260908_163436.db")
    assert dt3 == datetime(2026, 9, 8, 16, 34, 36)

    # 4. Screener backup format: screener-2026-09-11_095500.db.gz
    dt4 = parse_backup_timestamp("screener-2026-09-11_095500.db.gz")
    assert dt4 == datetime(2026, 9, 11, 9, 55, 0)

    # 5. Invalid format
    assert parse_backup_timestamp("random_file.txt") is None


def test_backup_retention_5_days():
    """Verify backups older than 5 days are deleted while newer backups are retained."""
    with tempfile.TemporaryDirectory() as tmp:
        bk_dir = Path(tmp) / "backups"
        bk_dir.mkdir()

        now = datetime.now()
        # 1. File from today (day 0) -> keep
        f_today = bk_dir / f"stockmon-{now.strftime('%Y-%m-%d_%H%M%S')}.db.gz"
        f_today.write_text("today")
        s_today = bk_dir / f"settings-{now.strftime('%Y-%m-%d_%H%M%S')}.json"
        s_today.write_text("{}")

        # 2. File from 3 days ago -> keep
        d_3days = (now - timedelta(days=3)).strftime("%Y-%m-%d_%H%M%S")
        f_3days = bk_dir / f"stockmon-{d_3days}.db.gz"
        f_3days.write_text("3days")
        s_3days = bk_dir / f"settings-{d_3days}.json"
        s_3days.write_text("{}")

        # 3. File from 6 days ago -> delete
        d_6days = (now - timedelta(days=6)).strftime("%Y-%m-%d_%H%M%S")
        f_6days = bk_dir / f"stockmon-{d_6days}.db.gz"
        f_6days.write_text("6days")
        s_6days = bk_dir / f"settings-{d_6days}.json"
        s_6days.write_text("{}")

        # 4. Legacy safety backup from 10 days ago -> delete
        d_10days_legacy = (now - timedelta(days=10)).strftime("%Y%m%d_%H%M%S")
        f_legacy = bk_dir / f"stockmon_pre_ticker_update_{d_10days_legacy}.db"
        f_legacy.write_text("legacy")

        # Manifest with all 4 plus 1 phantom (already missing) entry
        manifest_file = bk_dir / "manifest.json"
        manifest_entries = [
            {"filename": f_today.name, "timestamp": now.strftime("%Y-%m-%d_%H%M%S")},
            {"filename": f_3days.name, "timestamp": d_3days},
            {"filename": f_6days.name, "timestamp": d_6days},
            {"filename": "missing-file-from-past.db.gz", "timestamp": d_6days},
        ]
        manifest_file.write_text(json.dumps(manifest_entries))

        # Run rotation with retention_days=5
        deleted = rotate_backups(backup_dir=bk_dir, retention_days=5)

        # 6-day stockmon .db.gz + legacy + all settings files purged
        assert f_today.exists()
        assert f_3days.exists()
        assert not f_6days.exists()
        assert not f_legacy.exists()

        # All settings-*.json files are deleted (settings backup disabled)
        assert not s_today.exists()
        assert not s_3days.exists()
        assert not s_6days.exists()

        # Manifest should be pruned of 6-day file and missing file
        pruned_manifest = json.loads(manifest_file.read_text())
        retained_names = [e["filename"] for e in pruned_manifest]
        assert f_today.name in retained_names
        assert f_3days.name in retained_names
        assert f_6days.name not in retained_names
        assert "missing-file-from-past.db.gz" not in retained_names
        assert len(pruned_manifest) == 2


def test_backup_max_5_files():
    """Verify max_backups=5 strictly caps the number of stockmon files even within 5 days."""
    with tempfile.TemporaryDirectory() as tmp:
        bk_dir = Path(tmp) / "backups"
        bk_dir.mkdir()

        now = datetime.now()
        created_files = []
        # Create 8 backups from today and yesterday (all within 5 days)
        for i in range(8):
            dt = now - timedelta(hours=i * 2)
            fname = f"stockmon-{dt.strftime('%Y-%m-%d_%H%M%S')}.db.gz"
            f = bk_dir / fname
            f.write_text(f"backup {i}")
            created_files.append(f)

        manifest_file = bk_dir / "manifest.json"
        manifest_entries = [
            {"filename": f.name, "timestamp": f.name}
            for f in created_files
        ]
        manifest_file.write_text(json.dumps(manifest_entries))

        # Rotate with max_backups=5
        deleted = rotate_backups(backup_dir=bk_dir, retention_days=5, max_backups=5)
        assert deleted == 3

        remaining_files = list(bk_dir.glob("stockmon-*.db.gz"))
        assert len(remaining_files) == 5

        # The 5 newest should exist; the 3 oldest should be deleted
        for f in created_files[:5]:
            assert f.exists()
        for f in created_files[5:]:
            assert not f.exists()

        # Manifest should also have exactly 5 entries
        pruned_manifest = json.loads(manifest_file.read_text())
        assert len(pruned_manifest) == 5


def test_screener_manual_backup_creation():
    """Verify create_screener_backup creates a consistent .db.gz snapshot and copies json."""
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp) / "data"
        data_dir.mkdir()
        screener_db = data_dir / "screener_cache.db"
        screener_json = data_dir / "screener_cache.json"

        # Create dummy screener sqlite DB with tables
        conn = sqlite3.connect(str(screener_db))
        conn.execute("CREATE TABLE screener_day (trade_date TEXT PRIMARY KEY, total_items INTEGER)")
        conn.execute("INSERT INTO screener_day VALUES ('2026-09-11', 3450)")
        conn.commit()
        conn.close()

        screener_json.write_text(json.dumps({"nonce_info": {"nonce": "test1234"}}))

        bk_dir = Path(tmp) / "backups"

        with patch("stockmon.paths.SCREENER_DB_FILE", screener_db), \
             patch("stockmon.paths.SCREENER_CACHE_FILE", screener_json), \
             patch("stockmon.paths.BACKUP_DIR", bk_dir):

            res = create_screener_backup(screener_db_path=screener_db, backup_dir=bk_dir)
            assert res["filename"].startswith("screener-")
            assert res["filename"].endswith(".db.gz")
            assert res["size_bytes"] > 0
            assert Path(res["path"]).exists()

            # Verify decompressed DB integrity
            with gzip.open(res["path"], "rb") as gz_in:
                header = gz_in.read(16)
                assert header.startswith(b"SQLite format 3")

            # Verify screener_cache json was copied
            copied_json = bk_dir / "screener" / f"screener_cache-{res['timestamp']}.json"
            assert copied_json.exists()


def test_screener_backup_flask_routes():
    """Verify /api/screener/backup and download endpoints."""
    from stockmon.web import create_app
    app = create_app()
    client = app.test_client()

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        bk_dir = Path(tmp) / "backups"
        screener_dir = bk_dir / "screener"
        screener_dir.mkdir(parents=True)

        mock_file = screener_dir / "screener-2026-09-11_120000.db.gz"
        mock_file.write_bytes(b"mock compressed data")

        mock_info = {
            "filename": mock_file.name,
            "path": str(mock_file.resolve()),
            "directory": str(screener_dir.resolve()),
            "size_bytes": 20,
            "size_mb": 0.01,
            "timestamp": "2026-09-11_120000",
        }

        with patch("stockmon.db.backup.create_screener_backup", return_value=mock_info), \
             patch("stockmon.paths.BACKUP_DIR", bk_dir):

            # 1. POST /api/screener/backup
            res = client.post("/api/screener/backup")
            assert res.status_code == 200
            data = res.get_json()
            assert data["ok"] is True
            assert data["backup"]["filename"] == mock_file.name

            # 2. GET /api/screener/backup/download/<filename>
            res_dl = client.get(f"/api/screener/backup/download/{mock_file.name}")
            assert res_dl.status_code == 200
            assert res_dl.data == b"mock compressed data"
            res_dl.close()

            # 3. GET non-existent
            res_404 = client.get("/api/screener/backup/download/nonexistent.db.gz")
            assert res_404.status_code == 404
            res_404.close()
