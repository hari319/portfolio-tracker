"""Export all SQLite tables back to JSON files matching the original formats.

Provides:
  - An emergency exit / escape hatch (DATA_STORAGE_MIGRATION.md §8.4)
  - Human-readable JSON inspection of the current database
  - An independent backup format

Usage:
    python scripts/export_to_json.py
    python scripts/export_to_json.py --output-dir /path/to/exported
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from stockmon import paths
from stockmon.db import connect
from stockmon.db.repositories.portfolios import load_portfolios
from stockmon.db.repositories.sync_state import read_status
from stockmon.db.repositories.snapshots import load_latest_snapshot
from stockmon.db.repositories.quotes import load_quotes_cache
from stockmon.db.repositories.stock_status import load_all as load_all_statuses
from stockmon.db.repositories.screener import list_saved_dates, load_screener_for_date

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("export")


def export_all(out_dir: Path) -> None:
    config_dir = out_dir / "config"
    data_dir = out_dir / "data"
    screener_dir = data_dir / "screener"

    config_dir.mkdir(parents=True, exist_ok=True)
    screener_dir.mkdir(parents=True, exist_ok=True)

    # 1. Portfolios
    portfolios = load_portfolios()
    (config_dir / "portfolios.json").write_text(
        json.dumps(portfolios, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info("Exported portfolios.json (%d portfolios)", len(portfolios))

    # 2. Status
    status = read_status()
    (data_dir / "status.json").write_text(
        json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info("Exported status.json (version=%s)", status.get("version"))

    # 3. Snapshot
    snapshot = load_latest_snapshot() or {}
    (data_dir / "snapshot.json").write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info("Exported snapshot.json")

    # 4. Quotes Cache
    quotes = load_quotes_cache()
    (data_dir / "quotes_cache.json").write_text(
        json.dumps(quotes, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info("Exported quotes_cache.json (%d symbols)", len(quotes))

    # 5. Stock Status
    statuses = load_all_statuses()
    (data_dir / "stock_status.json").write_text(
        json.dumps(statuses, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info("Exported stock_status.json (%d entries)", len(statuses))

    # 6. Screener cache index & day files
    saved_dates = list_saved_dates()
    history = {}
    for d in saved_dates:
        date_str = d["date"]
        screener_data = load_screener_for_date(date_str)
        if screener_data:
            day_file = screener_dir / f"screener_{date_str}.json"
            day_file.write_text(
                json.dumps(screener_data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            history[date_str] = {
                "total": d["total"],
                "fetched_at": d["fetched_at"],
                "file": day_file.name,
            }
    cache_meta = {
        "latest_date": saved_dates[0]["date"] if saved_dates else None,
        "history": history,
    }
    (data_dir / "screener_cache.json").write_text(
        json.dumps(cache_meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info("Exported %d screener day file(s) and screener_cache.json", len(saved_dates))

    logger.info("Export successfully completed to: %s", out_dir)


def main():
    parser = argparse.ArgumentParser(description="Export SQLite database to JSON files.")
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "exported_json"),
        help="Directory to write exported JSON files (default: exported_json/)",
    )
    args = parser.parse_args()
    export_all(Path(args.output_dir))


if __name__ == "__main__":
    main()
