# Screener Manual Backup & Recovery Guide

## 1. Overview

The **Prime Market Screener** tab maintains a comprehensive offline cache of Indian market indicators, multi-day historical candles, and computed technical setups in `data/screener_cache.db`. Due to its significant size (~820 MB), it is managed separately from the lightweight transactional database (`stockmon.db`).

This guide details:
- **On-Demand Manual Backup Workflow**
- **Downloading and File Path Management**
- **REST API Endpoints**
- **Step-by-Step Database Restoration Instructions**

---

## 2. On-Demand Backup Workflow

### 2.1 Triggering from the User Interface
1. Navigate to the **Screener** tab in the top navigation bar.
2. In the top fetch control card (next to the **Nonce Settings** button), locate the **"Backup"** button with a hard-drive icon.
3. Click **"Backup"**.
4. While the snapshot is being generated, the button shows a spinning indicator (`Backing up...`).
5. Upon completion:
   - A success toast notification appears: `Screener backup created: screener_cache_YYYY-MM-DD_HH-MM-SS.db (X MB)`.
   - A modal dialog appears displaying complete backup details.

### 2.2 Backup Details Modal
The modal displays:
- **Filename**: The unique timestamped backup filename (e.g. `screener_cache_2026-09-11_08-30-00.db`).
- **File Size**: Size formatted in megabytes (e.g. `820.4 MB`).
- **Full Path**: The absolute filesystem path on the host machine.
- **"Copy" Button**: 1-click button to copy the full path to your clipboard (with temporary `Copied!` confirmation).
- **"Download Backup" Button**: Directly downloads the database file through your browser via HTTP streaming.
- **"Close" Button**: Dismisses the modal.

---

## 3. Architecture & Mechanics

### 3.1 SQLite Online Backup Mechanism
When a backup is requested:
1. The backend locates the active screener database at `data/screener_cache.db`.
2. A timestamped target path is constructed inside `backups/`:
   ```
   backups/screener_cache_YYYY-MM-DD_HH-MM-SS.db
   ```
3. The system opens a connection to `data/screener_cache.db` and uses the SQLite Online Backup API:
   ```python
   with sqlite3.connect(db_path) as src, sqlite3.connect(dest_path) as dst:
       src.backup(dst)
   ```
   This guarantees an internally consistent snapshot even if other read queries are occurring in WAL mode.
4. The backup is registered in `backups/manifest.json` with metadata:
   ```json
   {
     "filename": "screener_cache_2026-09-11_08-30-00.db",
     "timestamp": "2026-09-11T08:30:00.000000",
     "size_bytes": 860266496,
     "size_mb": 820.4,
     "type": "screener"
   }
   ```

---

## 4. REST API Endpoints

### 4.1 Trigger Screener Backup
- **Endpoint**: `POST /api/screener/backup`
- **Request Body**: `{}`
- **Response**:
  ```json
  {
    "ok": true,
    "message": "Screener cache backup created successfully.",
    "filename": "screener_cache_2026-09-11_08-30-00.db",
    "path": "C:\\Users\\...\\backups\\screener_cache_2026-09-11_08-30-00.db",
    "size_bytes": 860266496,
    "size_mb": 820.4,
    "timestamp": "2026-09-11T08:30:00.000000"
  }
  ```

### 4.2 Download Screener Backup
- **Endpoint**: `GET /api/screener/backup/download/<filename>`
- **Response**: Binary stream with `Content-Disposition: attachment; filename="<filename>"`.

---

## 5. Step-by-Step Database Restoration Instructions

If you need to revert or restore your screener cache to a previously backed up state:

### Method 1: Local Filesystem Replacement (Recommended)
1. **Stop the Application**:
   Ensure the Flask backend and scheduler are stopped so no active locks exist on `screener_cache.db`.
2. **Locate the Desired Backup Snapshot**:
   Open the `backups/` directory and select the desired file (e.g. `backups/screener_cache_2026-09-11_08-30-00.db`).
3. **Copy to Data Directory**:
   Copy the backup file to `data/screener_cache.db`, replacing the existing file:
   ```powershell
   Copy-Item -Path "backups\screener_cache_2026-09-11_08-30-00.db" -Destination "data\screener_cache.db" -Force
   ```
4. **Remove Stale WAL / SHM Files**:
   If `screener_cache.db-wal` or `screener_cache.db-shm` exist in `data/`, delete them:
   ```powershell
   Remove-Item -Path "data\screener_cache.db-wal", "data\screener_cache.db-shm" -ErrorAction SilentlyContinue
   ```
5. **Restart the Application**:
   Start the backend and frontend. The Screener tab will immediately reflect the restored cache and historical dates.

### Method 2: Restoring from a Downloaded File
If restoring on a new machine or from a browser download:
1. Rename the downloaded file (e.g. `screener_cache_2026-09-11_08-30-00.db`) to `screener_cache.db`.
2. Move it into the `data/` directory of your Daily Updater project.
3. Start the application.
