"""Audit and update existing holdings in data/stockmon.db to use correct tickers and fetched stock names.

1. Automatically creates a timestamped safety backup of data/stockmon.db.
2. Fixes known typo tickers across Open Holdings and Sold Positions.
3. Looks up each ticker and populates stock_name and scheme_name with official company names.
4. Reports all successfully updated records and any unresolvable tickers for user manual review.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from stockmon import paths
from stockmon.web.routes import _resolve_ticker

# Known typo corrections identified from audit
TYPO_CORRECTIONS: dict[str, str] = {
    "AJANTAPHARMA": "AJANTPHARM",
    "BAJAJFINACE": "BAJFINANCE",
    "CENTRALBANK": "CENTRALBK",
    "DATAPATTERN": "DATAPATTNS",
    "IDFCFIRST": "IDFCFIRSTB",
    "KARURVYSA": "KARURVYSYA",
    "OLAELC": "OLAELEC",
    "TVSSCS_BE": "TVSSCS",
    "WAAREENER": "WAAREEENER",
}


def backup_database(db_path: Path) -> Path:
    """Create a dated safety copy before running updates."""
    backups_dir = db_path.parent.parent / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = backups_dir / f"stockmon_pre_ticker_update_{ts}.db"
    shutil.copy2(db_path, dest)
    print(f"[BACKUP] Created safety backup: {dest}")
    return dest


def update_holdings() -> None:
    db_path = paths.DB_FILE
    if not db_path.exists():
        print(f"[ERROR] Database not found at {db_path}")
        return

    backup_database(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    holdings = conn.execute(
        "SELECT id, portfolio_name, symbol, stock_name, scheme_name, status FROM holding ORDER BY id"
    ).fetchall()

    print(f"\n[INFO] Total holdings in database: {len(holdings)}")

    typo_fixed_count = 0
    names_updated_count = 0
    unresolved = []
    updated_records = []

    # Resolution cache to prevent duplicate external network queries
    cache: dict[str, dict] = {}

    conn.execute("BEGIN IMMEDIATE")
    try:
        now = datetime.now().isoformat(timespec="seconds")
        for h in holdings:
            hid = h["id"]
            raw_sym = (h["symbol"] or "").strip()
            upper_sym = raw_sym.upper()

            # Check if known typo exists
            target_sym = TYPO_CORRECTIONS.get(upper_sym, upper_sym)
            ticker_was_corrected = (target_sym != raw_sym)

            if target_sym not in cache:
                cache[target_sym] = _resolve_ticker(target_sym)
            res = cache[target_sym]

            curr_name = (h["stock_name"] or h["scheme_name"] or "").strip()

            if res.get("found") and res.get("name"):
                official_name = res["name"]
                # Update if typo was fixed, or if current name was equal to symbol / empty / outdated
                name_needs_update = (
                    ticker_was_corrected
                    or curr_name.upper() in (upper_sym, target_sym, "")
                    or not h["stock_name"]
                )

                if ticker_was_corrected or name_needs_update:
                    conn.execute(
                        """
                        UPDATE holding
                        SET symbol = ?, stock_name = ?, scheme_name = ?, name_confirmed = 1, updated_at = ?
                        WHERE id = ?
                        """,
                        (target_sym, official_name, official_name, now, hid),
                    )
                    if ticker_was_corrected:
                        typo_fixed_count += 1
                    names_updated_count += 1
                    updated_records.append({
                        "id": hid,
                        "portfolio": h["portfolio_name"],
                        "status": h["status"],
                        "old_symbol": raw_sym,
                        "new_symbol": target_sym,
                        "old_name": curr_name,
                        "new_name": official_name,
                    })
            else:
                # If ticker could not be resolved automatically
                unresolved.append({
                    "id": hid,
                    "portfolio": h["portfolio_name"],
                    "status": h["status"],
                    "symbol": raw_sym,
                    "current_name": curr_name,
                })

        conn.execute("COMMIT")
        print("[SUCCESS] Transaction committed.")
    except Exception as exc:
        conn.execute("ROLLBACK")
        print(f"[ERROR] Transaction rolled back due to error: {exc}")
        raise

    print(f"\n==================== SUMMARY ====================")
    print(f"Total holdings processed: {len(holdings)}")
    print(f"Typo tickers corrected:   {typo_fixed_count}")
    print(f"Stock names updated:      {names_updated_count}")
    print(f"Unresolved entries:       {len(unresolved)}")
    print(f"=================================================\n")

    if unresolved:
        print("---------------- UNRESOLVED TICKERS ----------------")
        print("The following tickers could not be fetched via auto-lookup and require user review:\n")
        # Group by unique symbol
        grouped_unresolved: dict[str, list[dict]] = {}
        for item in unresolved:
            grouped_unresolved.setdefault(item["symbol"], []).append(item)

        for sym, items in sorted(grouped_unresolved.items()):
            statuses = list(set(it["status"] for it in items))
            ports = list(set(it["portfolio"] for it in items))
            names = list(set(it["current_name"] for it in items))
            print(f"• Ticker: '{sym}'")
            print(f"  Rows: {len(items)} | Status: {statuses} | Portfolios: {ports}")
            print(f"  Current Name in DB: {names}\n")


if __name__ == "__main__":
    update_holdings()
