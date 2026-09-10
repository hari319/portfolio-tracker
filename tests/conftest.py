"""Redirect every stockmon filesystem location into a throwaway directory.

``stockmon.paths`` resolves its directories from environment variables at import
time, so these must be set before any stockmon module is imported. pytest loads
conftest.py first, which makes this the only safe place for it.
"""

import os
import shutil
import tempfile
from pathlib import Path

_TMP_ROOT = Path(tempfile.mkdtemp(prefix="stockmon-tests-"))

os.environ["STOCKMON_DATA_DIR"] = str(_TMP_ROOT / "data")
os.environ["STOCKMON_CONFIG_DIR"] = str(_TMP_ROOT / "config")
os.environ["STOCKMON_LOG_DIR"] = str(_TMP_ROOT / "logs")
os.environ["STOCKMON_BACKUP_DIR"] = str(_TMP_ROOT / "backups")

import pytest  # noqa: E402

from stockmon import paths  # noqa: E402
from stockmon.db import open_database  # noqa: E402


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TMP_ROOT, ignore_errors=True)


@pytest.fixture(scope="session")
def db_conn():
    """A migrated, empty database living in the temp directory."""
    assert _TMP_ROOT in paths.DB_FILE.parents, "tests must never touch the real database"
    paths.ensure_directories()
    conn = open_database()
    for name in ("MADI", "BAPA", "LOAN"):
        conn.execute(
            "INSERT OR IGNORE INTO portfolio(name, kind, created_at) VALUES (?, 'personal', datetime('now'))",
            (name,),
        )
    yield conn
    conn.close()


@pytest.fixture
def clean_tracker(db_conn):
    """Empty every Portfolio Tracker table before and after a test."""
    def _wipe():
        for table in ("sale", "buy_lot", "holding", "dividend", "summary_value"):
            db_conn.execute(f"DELETE FROM {table}")

    _wipe()
    yield db_conn
    _wipe()
