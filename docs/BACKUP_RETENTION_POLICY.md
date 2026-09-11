# Backup Retention Policy & Architecture

## 1. Overview

The Daily Updater application implements automated and resilient backup routines to protect user portfolios, trade journals, technical statuses, and configurations against corruption or unintended modifications.

This document details:
- **The 5-Day Rolling Retention Policy**
- **Automated Backup Rotation & Manifest Synchronization**
- **Backup Scope Across Application Tabs**
- **Orphan / Phantom Entry Pruning**

---

## 2. 5-Day Rolling Retention & Max 5 Backups Policy

To prevent unbounded disk consumption while ensuring safe restore points across trading weeks, backups are governed by a strict **5-day retention & max 5 backups rule**:

1. **Retention Threshold**: Any backup older than **5 calendar days** relative to the current timestamp is automatically pruned.
2. **Strict Maximum Count**: At most **5 backup files** (`stockmon-*.db.gz`) are retained at any time. When more than 5 backups exist within the 5-day window, the oldest backups beyond the 5 most recent are automatically deleted.
3. **Settings Backup Removed**: Configuration (`config/settings.json`) only contains static preferences (EMA periods, run times) that can easily be adjusted; redundant `settings-*.json` snapshot files are disabled and automatically cleaned up to avoid folder clutter.
4. **Execution Timing**: Rotation executes automatically every time a new automated backup is created (e.g. during scheduled morning runs at 9:30 AM / 11:30 AM or manual portfolio updates).
5. **Deterministic Parsing**: Backup timestamps in filenames are parsed into ISO timestamps and verified against the cutoff date and sorted descending.
6. **Physical Removal & Manifest Sync**: Expired or excess database files are deleted from disk, and `manifest.json` is synchronized atomically.

---

## 3. Bidirectional Manifest Synchronization

All backup metadata is recorded in `backups/manifest.json`.

### 3.1 Orphan / Phantom Entry Resolution
Previously, file deletions or rotation could leave orphaned metadata entries in `manifest.json` pointing to non-existent files on disk. 

The enhanced rotation engine incorporates **`prune_manifest()`**:
- Inspects all entries in `manifest.json`.
- Compares each entry's file path against actual physical files on disk.
- Removes entries where:
  - The backup age exceeds the 5-day retention threshold, OR
  - The physical file no longer exists on disk (pruning phantom records).
- Re-writes the clean, synchronized manifest atomically.

---

## 4. Backup Scope Across Application Tabs

The application data is divided between two SQLite databases based on size and operational volatility:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                APPLICATION TABS                                 │
├───────────────────┬───────────────────────────┬───────────────┬─────────────────┤
│      Tracker      │     Portfolio Tracker     │    Status     │  Swing Tracker  │
├───────────────────┴───────────────────────────┴───────────────┴─────────────────┤
│                                  stockmon.db                                    │
│                       (~400 KB - 5 MB SQLite WAL database)                      │
│                                                                                 │
│  [ COVERED BY AUTOMATED 5-DAY BACKUP ROTATION & MANIFEST SYNCHRONIZATION ]      │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│                                  SCREENER TAB                                   │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                screener_cache.db                                │
│                     (~820 MB high-volume historical cache)                      │
│                                                                                 │
│               [ COVERED BY ON-DEMAND MANUAL BACKUP & DOWNLOAD ]                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 4.1 Durable Operational Database: `stockmon.db`
All primary transactional state across the four durable tabs resides in `stockmon.db`:
- **Tracker Tab**: `portfolio_rows`
- **Portfolio Tracker Tab**: `portfolio_history`, `portfolio_totals`
- **Status Tab**: `stock_status`
- **Swing Tracker Tab**: `swing_tracker`, `swing_tracker_source`

Every scheduled or manual backup of `stockmon.db` captures all four tabs simultaneously. A restoration of `stockmon.db` restores all portfolio rows, historical snapshots, swing trades, and trade sources in an atomic state.

### 4.2 High-Volume Historical Cache: `screener_cache.db`
The Screener tab stores tens of thousands of historical market indicators (~820MB). Because bundling an ~820MB database into multiple daily automated backups would rapidly consume gigabytes of disk space, Screener data is protected via **Dedicated On-Demand Snapshots** (see [Screener Manual Backup Guide](SCREENER_MANUAL_BACKUP.md)).

---

## 5. Manual Backup Operations

### 5.1 Triggering an On-Demand Backup
To force an immediate backup of `stockmon.db` outside scheduled runs:
```bash
python -c "from stockmon.db.backup import backup_database; backup_database()"
```

### 5.2 Inspecting Active Backups & Manifest
Inspect the list of valid, unexpired backups:
```bash
python -c "from stockmon.db.backup import list_backups; print(list_backups())"
```
Or view `backups/manifest.json`.

### 5.3 Restoring from a Backup
1. Stop the Daily Updater application.
2. Locate the desired backup file in `backups/` (e.g. `stockmon_backup_2026-09-10_09-30-00.db`).
3. Replace `data/stockmon.db` with the backup file.
4. Delete any stale WAL files (`data/stockmon.db-wal`, `data/stockmon.db-shm`) if present.
5. Restart the application.
