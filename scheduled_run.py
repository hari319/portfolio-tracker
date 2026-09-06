"""Batch refresh executed by Windows Task Scheduler.

Fetches every ticker in both portfolios, writes ``data/snapshot.json`` and bumps
``data/status.json`` so any open browser reloads its tables automatically.

Exit codes: 0 = success, 1 = every ticker failed, 2 = unexpected fatal error.
"""

from __future__ import annotations

import argparse
import logging
import sys

from stockmon.config_manager import get_run_times, load_settings
from stockmon.logging_config import configure_logging
from stockmon.paths import SCHEDULER_LOG_FILE, ensure_directories
from stockmon.portfolio import consume_pending_additions, load_portfolios
from stockmon.service import refresh_portfolios
from stockmon.db import open_database, open_screener_cache
from stockmon.db.backup import create_backup, rotate_backups
from stockmon.db.repositories.screener import prune_old_dates

logger = logging.getLogger("stockmon.scheduled_run")


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh all portfolio data (scheduled run).")
    parser.add_argument(
        "--source",
        default="scheduled",
        help="Label recorded in the status file (default: scheduled)",
    )
    parser.add_argument("--quiet", action="store_true", help="Do not echo log lines to stdout")
    args = parser.parse_args()

    ensure_directories()
    configure_logging(SCHEDULER_LOG_FILE, console=not args.quiet)

    # Initialize / migrate databases at start
    open_database()
    open_screener_cache()

    from datetime import datetime
    today = datetime.now()
    if args.source == "scheduled" and today.weekday() >= 5:
        logger.info("Today is %s (weekend). Skipping scheduled market run.", today.strftime("%A"))
        return 0

    logger.info("=" * 72)
    logger.info("Scheduled run starting (configured times: %s)", ", ".join(get_run_times()))

    try:
        pending = consume_pending_additions()
        if pending:
            logger.info(
                "Picked up %s newly added ticker(s) since the last run: %s",
                len(pending),
                ", ".join(f"{item.get('symbol')} -> {item.get('portfolio')}" for item in pending),
            )
        else:
            logger.info("No new tickers were added since the last run.")

        portfolios = load_portfolios()
        for name, tickers in portfolios.items():
            logger.info("Portfolio %s: %s ticker(s)", name, len(tickers))

        snapshot = refresh_portfolios(source=args.source, portfolios=portfolios)
    except Exception:
        logger.exception("Scheduled run failed with an unexpected error")
        return 2

    stats = snapshot["stats"]
    for failure in snapshot["errors"]:
        logger.error("FAILED %s - %s", failure["symbol"], failure["message"])

    logger.info(
        "Scheduled run finished: %s fetched, %s failed, %s total. Status published for the UI.",
        stats["ok"],
        stats["failed"],
        stats["total"],
    )

    # 1. Prune screener data older than retention setting (§5.3)
    try:
        settings = load_settings()
        retention_days = int(settings.get("data", {}).get("screener_retention_days", 60))
        prune_old_dates(keep_days=retention_days)
    except Exception as exc:
        logger.warning("Could not prune old screener dates: %s", exc)

    # 2. Consistent backup of stockmon.db after scheduled run (§6.2 - §6.3)
    try:
        bk_path = create_backup()
        rotate_backups(keep_daily=7)
        logger.info("Automatic backup created: %s", bk_path.name)
    except Exception as exc:
        logger.error("Automatic backup failed: %s", exc)

    # 3. Clean logs older than 1 day
    try:
        from stockmon.logging_config import clean_old_logs
        cleaned = clean_old_logs(max_age_days=1)
        if cleaned:
            logger.info("Cleaned %d stale log file(s) older than 1 day", cleaned)
    except Exception as exc:
        logger.warning("Could not clean old logs: %s", exc)

    if stats["total"] and stats["ok"] == 0:
        logger.error("Every ticker failed - check network connectivity and symbols.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
