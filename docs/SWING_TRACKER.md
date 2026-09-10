# Swing Tracker Feature Documentation

## 1. Overview

The **Swing Tracker** tab is a specialized trade journaling and position tracking suite within the Daily Updater application. It allows users to record, monitor, and manage swing trading opportunities across Indian equities (NSE & BSE) with structured entry/exit parameters, live market price monitoring, and trade source attribution.

Key capabilities include:
- **Trade Setup Journal**: Log setups with Ticker, Date of entry, Current Price, Buy Zone, Stop Loss (SL), Target 1, Target 2, Pattern Break description, Thesis, and Trade Source.
- **Range & Distance Engine**: Supports single price levels or price ranges (e.g. `100-105`), automatically averaging ranges and calculating live percentage distances from Current Price to each level.
- **Portfolio Price Reuse & 9:30 AM Auto-Refresh**: Reuses existing quotes from active Portfolio tables (`BAPA`, `MADI`) before fetching, minimizing redundant network requests. Prices auto-refresh daily at 9:30 AM via Windows Task Scheduler, with 1-click manual refresh available per row.
- **Dynamic Trade Source Persistence**: Dedicated dropdown with on-the-fly source addition persisted directly to SQLite.
- **Preserved Free-Text Formatting**: Formatted multi-line thesis notes (paragraphs, line breaks, indentation) are rendered without flattening.
- **Live As-You-Type Search**: Instant filtering across symbols, patterns, theses, and trade sources without requiring a submit button.

---

## 2. Architecture & Data Model

All swing trade records and sources are stored in the durable SQLite database (`data/stockmon.db`, schema version 5):

```
                   ┌───────────────────────────────┐
                   │          stockmon.db          │
                   └───────┬───────────────┬───────┘
                           │               │
        ┌──────────────────▼──┐         ┌──▼────────────────────────┐
        │    swing_tracker    │         │   swing_tracker_source    │
        │  (trade setups)     │         │ (persisted dropdown items)│
        └─────────────────────┘         └───────────────────────────┘
```

### 2.1 Database Schema (`schema_v5.sql`)

#### Table: `swing_tracker`
| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | `INTEGER PRIMARY KEY AUTOINCREMENT` | Unique trade identifier |
| `symbol` | `TEXT NOT NULL` | Normalized ticker (e.g. `TATAMOTORS.NS`, `RELIANCE.NS`) |
| `date` | `TEXT NOT NULL` | Trade setup/entry date (`YYYY-MM-DD`) |
| `current_price` | `REAL` | Cached latest market price (₹) |
| `current_price_updated_at` | `TEXT` | Timestamp of last price update |
| `buy_zone` | `TEXT` | Target entry price or range (e.g. `970-985` or `980`) |
| `stop_loss` | `TEXT` | Stop-loss price or range (e.g. `950` or `945-950`) |
| `target1` | `TEXT` | Primary profit target or range (e.g. `1050` or `1040-1060`) |
| `target2` | `TEXT` | Secondary profit target or range (e.g. `1100`) |
| `pattern_break` | `TEXT` | Technical chart pattern (e.g. `Ascending Triangle`, `Cup & Handle`) |
| `thesis` | `TEXT` | Free-text reasoning with line breaks and formatting preserved |
| `trade_source` | `TEXT` | Origin/provider of trade (e.g. `Self Analysis`, `Aman Sharma`) |
| `created_at` | `TEXT NOT NULL` | ISO 8601 creation timestamp |
| `updated_at` | `TEXT NOT NULL` | ISO 8601 modification timestamp |

#### Table: `swing_tracker_source`
| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | `INTEGER PRIMARY KEY AUTOINCREMENT` | Unique source identifier |
| `name` | `TEXT NOT NULL UNIQUE` | Trade source name (persisted for future dropdown selections) |
| `created_at` | `TEXT NOT NULL` | ISO 8601 creation timestamp |

---

## 3. Core Features & Business Logic

### 3.1 Range Parsing & Percentage Distance Calculations

For the **Buy Zone**, **SL**, **Target 1**, and **Target 2** fields:
1. Inputs can be entered as a single number (e.g. `100`, `₹1,250.50`) or a range (e.g. `100-105`, `100 - 105`, `100 to 105`).
2. When a range is provided, the engine computes the arithmetic mean:
   $$\text{Average} = \frac{\text{Low} + \text{High}}{2}$$
3. The percentage distance from the **Current Price** is computed as:
   $$\text{Distance \%} = \frac{\text{Level Value} - \text{Current Price}}{\text{Current Price}} \times 100$$
4. **Context-Aware Visual Badges**:
   - **Buy Zone**: If Current Price is inside the range, displays an **`In Buy Zone`** green badge; otherwise shows the distance percentage.
   - **Stop Loss (SL)**: Displays negative distance (e.g. `-5.2%`) in neutral style when safe. If Current Price drops below Stop Loss, displays a **`⚠️ SL Hit (+X.X%)`** red warning badge.
   - **Target 1 & Target 2**: Display positive distance pills in green (e.g. `+12.4%`).

### 3.2 Price Resolution: Portfolio Table Reuse First

To optimize performance and minimize rate-limiting on external quote fetchers:
1. Before fetching external quotes for a ticker, the system checks whether the ticker already exists in the active **Portfolio** tables (`BAPA` or `MADI`) with an active price $> 0$.
2. If found, the existing price is reused immediately without network requests (`source = 'portfolio'`).
3. If not found in active portfolios, the system falls back to fetching a live market quote via `fetch_ticker_quote()` (`source = 'live'`).

### 3.3 Auto-Refresh at 9:30 AM & On-Demand Row Refresh

- **Daily Scheduled Run (9:30 AM & 11:30 AM)**:
  `scheduled_run.py` calls `refresh_all_swing_trade_prices()`, automatically updating prices for all swing trades during market hours.
- **Manual Row Refresh**:
  Each row in the Swing Tracker table features a 1-click refresh icon button next to Current Price to force an immediate update for that specific stock.
- **Manual Table Refresh**:
  A **"Refresh Prices"** button in the header refreshes all swing trade prices simultaneously.

### 3.4 Trade Source Dropdown with On-the-Fly Creation

- The Trade Source column identifies who provided or recommended the trade setup.
- The modal provides a dropdown of all saved sources.
- An inline `+ Add New Source` action enables adding new sources directly from the modal; new sources are saved to `swing_tracker_source` in SQLite and immediately selected.

### 3.5 Free-Text Thesis Formatting

- The Thesis field is stored as verbatim text.
- In the table, thesis entries are rendered with CSS `white-space: pre-wrap`, preserving paragraphs, line breaks, bullet points, and indentation.
- Long entries feature an inline **"Show more / Show less"** expander to keep table rows clean.

### 3.6 Live As-You-Type Search

- Both the **Swing Tracker** tab and the **Screener** tab feature live as-you-type search filtering with no submit button.
- Typing in the search bar instantly filters rows by symbol, pattern, thesis, source, or date.
- Supported keyboard shortcut: `Ctrl+F` (or `Cmd+F`) immediately focuses and selects the search input.

---

## 4. HTTP API Reference

All endpoints are served by Flask under `/api/swing-tracker`:

| Method | Endpoint | Description | Payload / Query |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/swing-tracker` | Retrieve all swing trades and available sources | None |
| `POST` | `/api/swing-tracker` | Add a new swing trade setup | JSON with `symbol`, `date`, `buy_zone`, `stop_loss`, `target1`, `target2`, `pattern_break`, `thesis`, `trade_source`, optional `current_price` |
| `PUT` | `/api/swing-tracker/<id>` | Update an existing swing trade | JSON with fields to update |
| `DELETE` | `/api/swing-tracker/<id>` | Delete a swing trade by ID | None |
| `POST` | `/api/swing-tracker/<id>/refresh-price` | Force-refresh price for a single trade row | None |
| `POST` | `/api/swing-tracker/refresh-all` | Batch-refresh prices for all swing trades | None |
| `GET` | `/api/swing-tracker/sources` | List all persisted trade sources | None |
| `POST` | `/api/swing-tracker/sources` | Add and persist a new trade source on the fly | `{"name": "SourceName"}` |
| `GET` | `/api/swing-tracker/lookup-ticker` | Check Portfolio table or fetch live quote | `?symbol=TATAMOTORS` |
