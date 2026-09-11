# Swing Tracker Workflows & Architecture Guide

## 1. Overview

The **Swing Tracker** feature provides a dedicated trade journaling and monitoring workspace within the Daily Updater system. This document details the enhanced workflows introduced in Schema Version 6:
- **Active vs. Completed Tab Segmentation**
- **Soft-Delete (Archive to Completed) Workflow**
- **Permanent Deletion Workflows (Single, Bulk Selection, and Delete All)**
- **Multi-Select Trade Sources with Inline Tag Creation**

---

## 2. Active vs. Completed Tabs

The Swing Tracker interface is divided into two primary operational sub-tabs:

| Sub-Tab | Purpose | Available Actions |
| :--- | :--- | :--- |
| **Active Trades** | Actively tracked positions and watch candidates | • Add new swing trades<br>• Edit trade parameters<br>• Live market price refresh (single row & all rows)<br>• **Delete button**: Soft-moves trade to **Completed** |
| **Completed Trades** | Historical archive of completed, stopped out, or closed swing setups | • View historical parameters & technical notes<br>• Row selection via checkboxes<br>• **Permanent Delete (Single)**<br>• **Bulk Delete Selected**<br>• **Delete All Completed Trades** |

### 2.1 Interface Segregation
To keep closed trades from cluttering active operational views and preventing accidental edits:
- **Completed Tab Simplifications**:
  - The **"Add Swing Trade"** and **"Refresh Prices"** header buttons are hidden.
  - The row-level **Edit** and **Price Refresh** buttons are hidden.
  - Active market price updates (`refresh_all_swing_trade_prices`) run with `active_only=True` to eliminate redundant queries for archived trades.

---

## 3. Trade Lifecycle Workflows

```
  [User Enters Trade Setup]
              │
              ▼
   ┌──────────────────────┐
   │    ACTIVE TRADES     │ ◄─── Auto-refreshed at 9:30 AM & 11:30 AM
   └──────────┬───────────┘
              │
              │ Click Delete (Soft-Delete)
              ▼
   ┌──────────────────────┐
   │   COMPLETED TRADES   │ ◄─── Preserved historical journal
   └──────────┬───────────┘
              │
              ├── Click Delete (Single) ────────────► [ Irreversible SQL Delete ]
              ├── Select Rows + "Delete Selected" ──► [ Irreversible Bulk Delete ]
              └── Click "Delete All" ───────────────► [ Irreversible Purge All ]
```

### 3.1 Adding an Active Trade
1. Navigate to the **Swing Tracker** tab (default sub-tab: **Active Trades**).
2. Click **"+ Add Swing Trade"**.
3. In the modal:
   - Enter symbol (e.g. `TATAMOTORS.NS` or `RELIANCE`). The lookup button will fetch quotes and check active portfolios (`BAPA`/`MADI`).
   - Enter entry date, buy zone, stop-loss, targets, pattern break, and free-text thesis.
   - Select one or more **Trade Sources** from the multi-select picker or add a new one.
4. Click **Save Trade**. The trade enters SQLite with `status = 'active'`.

### 3.2 Moving Active Trades to Completed (Soft-Delete)
1. In the **Active Trades** tab, locate the trade to close or archive.
2. Click the **Delete** (trash icon) button in the Actions column.
3. Confirm the prompt: `Move swing trade for {symbol} to Completed?`.
4. The system issues `POST /api/swing-tracker/<id>/complete`, updating `status = 'completed'` in SQLite.
5. The trade immediately moves to the **Completed** tab without losing any notes, dates, or prices.

### 3.3 Permanent Deletion Workflows (Completed Tab)
Trades in the **Completed** tab can be permanently removed from SQLite:

#### Workflow A: Single-Row Permanent Deletion
1. Switch to the **Completed** sub-tab.
2. Click the red **Trash** icon on the target row.
3. Confirm the irreversible deletion prompt.
4. The system executes `DELETE /api/swing-tracker/<id>/permanent`, purging the row from SQLite.

#### Workflow B: Bulk Selection Deletion
1. In the **Completed** sub-tab, select individual row checkboxes or click the select-all checkbox in the table header.
2. The header action button updates to **"Delete Selected (N)"**.
3. Click **"Delete Selected (N)"** and confirm the prompt.
4. The system executes `POST /api/swing-tracker/bulk-delete` with `{ ids: [...] }`, deleting the chosen records in an atomic transaction.

#### Workflow C: Delete All Completed Trades
1. In the **Completed** sub-tab, click **"Delete All"**.
2. Confirm the explicit confirmation warning modal.
3. The system executes `POST /api/swing-tracker/bulk-delete` with `{ all: true }`, wiping all completed records while preserving all active trades.

---

## 4. Multi-Select Trade Sources

### 4.1 UI Interaction
- In the Add / Edit modal, the **Trade Source** field provides a multi-tag selector.
- Users can select multiple sources (e.g. `Self Analysis`, `Breakout Screener`, `Technical Channel`).
- Each selected source renders as a badge with an `×` remove button.
- Users can type a new source name and click **"+ Add New Source"**; the new source is persisted in SQLite (`swing_tracker_source`) and immediately tagged.

### 4.2 Data Storage & Backward Compatibility
- In the database table `swing_tracker`, trade sources are stored as comma-separated values in `trade_source` (e.g. `"Self Analysis, Breakout Screener"`).
- The API returns both:
  - `trade_source`: `"Self Analysis, Breakout Screener"` (guarantees backward compatibility for existing consumers)
  - `trade_sources`: `["Self Analysis", "Breakout Screener"]` (convenience array for frontend badge rendering)
- In the table view, each source renders as an individual badge pill.
- The live search bar matches any of the assigned sources.

---

## 5. Database Schema Changes (v6)

Migration `_v6_swing_tracker_status` applied the following modifications to `stockmon.db`:

```sql
-- Add status column defaulting to active
ALTER TABLE swing_tracker ADD COLUMN status TEXT NOT NULL DEFAULT 'active';

-- Index status column for fast tab filtering
CREATE INDEX IF NOT EXISTS idx_swing_tracker_status ON swing_tracker(status);
```

---

## 6. REST API Reference

| Endpoint | Method | Payload | Description |
| :--- | :--- | :--- | :--- |
| `/api/swing-tracker` | `GET` | — | Returns `trades`, `active_trades`, `completed_trades`, and `sources` |
| `/api/swing-tracker` | `POST` | Trade JSON | Create a new active swing trade (supports `trade_sources` list) |
| `/api/swing-tracker/<id>` | `PUT` | Trade JSON | Update an existing swing trade |
| `/api/swing-tracker/<id>` | `DELETE` | — | Soft-moves trade to `completed` |
| `/api/swing-tracker/<id>/complete` | `POST` | — | Explicit soft-move to `completed` |
| `/api/swing-tracker/<id>/permanent` | `DELETE` | — | Permanent, irreversible deletion of a completed trade |
| `/api/swing-tracker/bulk-delete` | `POST` | `{"ids": [...]}` or `{"all": true}` | Permanently deletes selected or all completed trades |
| `/api/swing-tracker/refresh-all` | `POST` | — | Refreshes market prices for all active trades |
| `/api/swing-tracker/sources` | `GET` / `POST` | `{"name": "..."}` | List or register new trade sources |
