# Portfolio and Stock Monitor (BAPA & MADI)

A comprehensive local desktop application for tracking NSE/BSE stock portfolios, conducting scenario-based fundamental/technical valuation tracking, and scanning the broad Indian stock market (>3,400 companies) with predictive multi-day momentum indicators.

The application features a modern **React + Bootstrap 5** interface served inside a **native desktop window** (powered by [pywebview](https://pywebview.flowrl.com/)) or any web browser.

---

## 📚 Feature Documentation by Tab

Detailed feature guides, formulas, screening criteria, and workflows have been modularized by application tab:

| Tab | Documentation | Description |
| :--- | :--- | :--- |
| **Tab 1: Tracker** | [**Portfolio Monitor Guide**](docs/TAB1_PORTFOLIO_MONITOR.md) | Multi-portfolio tracking (BAPA & MADI), 10 stacked Daily/Weekly EMAs, priority sorting, SELL/HOLD signals, NSE/BSE auto-switching, and ticker management. |
| **Tab 2: Portfolio Tracker** | [**Portfolio Tracker Guide**](docs/PORTFOLIO_TRACKER.md) | Transactional holdings ledger (MADI, BAPA, LOAN), multi-buy aggregation, realized sold records, dividends, loan balance sheet, and full Excel round-trip import/export. |
| **Tab 3: Status** | [**Stock Status & Scenario Analysis**](docs/TAB2_STOCK_STATUS.md) | Valuation journal, Base/Bull/Bear targets & CAGR %, Best Entry tracking, live price comparisons, and multi-date analysis versioning. |
| **Tab 4: Screener** | [**Market Screener & Predictive Analysis**](docs/TAB3_MARKET_SCREENER.md) | Broad-market scanning (>3,400 NSE stocks), automated daily `X-WP-Nonce` lifecycle, 154-column table, 1-click strategy presets, custom filter builder, and multi-day trajectory engine. |
| **Tab 5: Swing Tracker** | [**Swing Tracker Guide**](docs/SWING_TRACKER.md) | Swing trade journal with entry zones, stop losses, multi-target tracking, pattern breakouts, trade sources, range-average percentage calculations, and daily 9:30 AM auto-refresh. |

Additional references:

| Document | Description |
| :--- | :--- |
| [**Sheet Format Spec**](docs/SHEET_FORMAT.md) | Column layout and Excel workbook structure for Portfolio Tracker import/export. |
| [**Contributing Guide**](CONTRIBUTING.md) | Naming conventions, project structure rules, and guide for adding new features. |

---

## Table of Contents

1. [How It Works](#how-it-works)
2. [Project Structure](#project-structure)
3. [Setup & Installation](#setup--installation)
4. [Running the Application](#running-the-application)
5. [Frontend Development](#frontend-development)
6. [Tab Overview Summaries](#tab-overview-summaries)
   - [Tab 1: Portfolio Monitor (Tracker)](#tab-1-portfolio-monitor-tracker)
   - [Tab 2: Portfolio Tracker](#tab-2-portfolio-tracker)
   - [Tab 3: Stock Status & Scenarios](#tab-3-stock-status--scenarios)
   - [Tab 4: Market Screener & Predictive Analysis](#tab-4-market-screener--predictive-analysis)
   - [Tab 5: Swing Tracker](#tab-5-swing-tracker)
7. [Scheduled Runs & Windows Task Scheduler](#scheduled-runs--windows-task-scheduler)
8. [Configuration Reference](#configuration-reference)
9. [Error Handling & Logging](#error-handling--logging)
10. [HTTP API Reference](#http-api-reference)
11. [Backup, Restore & Disaster Recovery](#backup-restore--disaster-recovery)
12. [Known Limitations & Planned Features](#known-limitations--planned-features)

---

## How It Works

```
config/settings.json ────────────────┐
data/stockmon.db (portfolios, etc.) ─┤
                                     ▼
   scheduled_run.py / "Refresh now" ──► yfinance ──► EMA engine
                         │
                         ├──► data/stockmon.db       (stores snapshot, quote cache, bumps sync_state)
                         ├──► backups/stockmon-*.gz  (automatic online gzip backup)
                         └──► data/screener_cache.db (prunes old dates > 60 trading days)
                                       │
                                       ▼
                  Flask (daemon thread) ──SSE──► React Frontend (pywebview / Browser)
                                                   (auto-refreshes on version update)
                  scheduled_run.py ──► show_window.py ──► pops up reminder window
                                         (only if no window is already open)
```

* **Prices & Historical Bars**: Fetched via `yfinance`. NSE symbols use `.NS`, BSE symbols use `.BO`.
* **Weekly Candles**: Resampled from daily history (Friday-anchored) for speed and live price consistency.
* **Shared Database State**: Flask and scheduled tasks communicate through SQLite in Write-Ahead Logging (`WAL`) mode, preventing cross-process read/write lock contention.
* **Real-Time UI Updates**: Open desktop windows receive Server-Sent Events (SSE) from Flask whenever the `sync_state` version updates.

---

## Project Structure

```
Daily Updater/
├── app.py                        # Desktop window entry point (python app.py)
├── show_window.py                # Reminder popup launched after a scheduled refresh
├── scheduled_run.py              # Batch refresh entry point (run by Task Scheduler)
├── requirements.txt
├── CONTRIBUTING.md               # Naming conventions and development guidelines
├── config.template.json          # Template for config/settings.json
├── portfolios.template.json      # Template for config/portfolios.json
│
├── docs/                         # Modular documentation by application tab
│   ├── TAB1_PORTFOLIO_MONITOR.md
│   ├── TAB2_STOCK_STATUS.md
│   ├── TAB3_MARKET_SCREENER.md
│   ├── PORTFOLIO_TRACKER.md
│   ├── SWING_TRACKER.md
│   └── SHEET_FORMAT.md           # Excel import/export column layout spec
│
├── frontend/                     # React + Bootstrap 5 frontend (Vite)
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── App.jsx               # Root component with 5-tab navigation
│       ├── main.jsx              # React entry point
│       ├── api.js                # API client (all backend calls)
│       ├── components/
│       │   ├── Header.jsx        # Navbar with refresh button & stats
│       │   ├── Footer.jsx        # SSE connection status bar
│       │   ├── Toast.jsx         # Floating notifications
│       │   ├── PortfolioSection.jsx      # Tab 1: portfolio container
│       │   ├── PortfolioTable.jsx        # Tab 1: EMA data table
│       │   ├── EmaCell.jsx               # Tab 1: individual EMA value
│       │   ├── AddTickerPanel.jsx        # Tab 1: ticker management
│       │   ├── SchedulePanel.jsx         # Tab 1: schedule config
│       │   ├── ErrorsPanel.jsx           # Tab 1: error display
│       │   ├── PortfolioTrackerTab.jsx   # Tab 2: holdings ledger
│       │   ├── SoldPositionsModal.jsx    # Tab 2: realized gains history
│       │   ├── DividendsModal.jsx        # Tab 2: dividend management
│       │   ├── StatusTab.jsx             # Tab 3: stock analysis tab
│       │   ├── StatusTable.jsx           # Tab 3: analysis data table
│       │   ├── AddStatusModal.jsx        # Tab 3: add/edit analysis
│       │   ├── ScreenerTab.jsx           # Tab 4: market screener
│       │   ├── ScreenerFilterPanel.jsx   # Tab 4: filter controls
│       │   ├── SwingTrackerTab.jsx       # Tab 5: swing trades
│       │   └── SwingTradeModal.jsx       # Tab 5: add/edit trade
│       ├── constants/
│       │   ├── portfolioCharges.js       # Brokerage charge defaults
│       │   ├── screenerColumns.js        # Screener column metadata
│       │   └── screenerFilters.js        # Filter presets & evaluators
│       ├── hooks/
│       │   └── useTickerLookup.js        # Ticker search with debounce
│       ├── utils/
│       │   ├── date.js                   # Date formatting
│       │   └── swingCalculations.js      # Risk/reward math
│       └── styles/
│           └── custom.css                # Application design system
│
├── stockmon/                     # Python backend package
│   ├── __init__.py               # Package root, re-exports refresh_portfolios
│   ├── paths.py                  # Config/data/log/backup path resolution
│   ├── logging_config.py         # Rotating file + console logging
│   ├── errors.py                 # ValidationError, DataFetchError
│   ├── config_manager.py         # settings.json manager
│   ├── portfolio.py              # Portfolios, ticker validation, TradingView links
│   ├── portfolio_tracker.py      # Portfolio Tracker financial calculations
│   ├── data_fetcher.py           # yfinance integration with retry backoff
│   ├── ema.py                    # EMA calculations & weekly resampling
│   ├── service.py                # Orchestration (refresh, build/drop rows, snapshots)
│   ├── status.py                 # Version counter and update signaling
│   ├── stock_status.py           # Stock analysis status CRUD
│   ├── screener.py               # Prime screener API client & daily nonce handling
│   ├── multi_day_analyzer.py     # Multi-day chronological sequence engine
│   ├── backtester.py             # Strategy backtesting engine
│   ├── swing_tracker.py          # Swing trade management & price updates
│   ├── sheet_io.py               # Excel/CSV import & export engine
│   ├── sheet_format.py           # Column layout constants for sheet I/O
│   ├── jsonstore.py              # JSON file read/write helpers
│   │
│   ├── db/                       # SQLite database foundation
│   │   ├── __init__.py           # Connection management, health checks, lifecycle
│   │   ├── migrations.py         # Append-only PRAGMA user_version migration engine
│   │   ├── backup.py             # Online backup API, gzip snapshots & restore
│   │   ├── schema_v1.sql         # Durable schema: portfolios, quotes, status
│   │   ├── schema_v2.sql         # Portfolio Tracker: holdings, lots, sales, dividends
│   │   ├── schema_v5.sql         # Swing Tracker: trades & sources
│   │   ├── schema_screener.sql   # Disposable screener cache schema
│   │   └── repositories/         # Repository SQL access layer (all SQL lives here)
│   │       ├── __init__.py       # Design contract: no raw SQL outside this package
│   │       ├── portfolios.py     # Portfolio & ticker management
│   │       ├── holdings.py       # Holdings CRUD, lot management, FIFO selling
│   │       ├── dividends.py      # Dividend records
│   │       ├── summary.py        # Loan Summary key-value metrics
│   │       ├── quotes.py         # Quote cache read/write
│   │       ├── snapshots.py      # Tracker snapshot persistence
│   │       ├── stock_status.py   # Stock analysis status entries
│   │       ├── screener.py       # Screener cache queries & pruning
│   │       ├── swing_tracker.py  # Swing trade & source CRUD
│   │       └── sync_state.py     # Version coordination (sync_state table)
│   │
│   └── web/                      # Flask web layer
│       ├── __init__.py           # App factory (create_app)
│       └── routes/               # Route handlers split by domain
│           ├── __init__.py       # Blueprint registration & error handlers
│           ├── tracker.py        # Core tracker, data, refresh, tickers, SSE
│           ├── stock_status.py   # Stock status CRUD endpoints
│           ├── screener.py       # Screener fetch, analysis, backtest
│           ├── backup.py         # Backup create, list, restore
│           ├── portfolio_tracker.py  # Holdings, lots, sales, import/export
│           └── swing_tracker.py  # Swing trade CRUD & price refresh
│
├── scripts/                      # Windows Task Scheduler & migration automation
│   ├── migrate_to_sqlite.py      # Re-runnable JSON to SQLite database importer
│   ├── export_to_json.py         # Escape hatch export from SQLite back to JSON
│   ├── update_holdings_tickers.py # One-off ticker symbol correction utility
│   ├── register_task.ps1         # Registers/updates scheduled task from settings
│   ├── run_scheduled.ps1         # PowerShell execution wrapper
│   └── run_scheduled.bat         # Batch file execution wrapper
│
├── tests/                        # Test suite
│   ├── conftest.py               # Shared fixtures (in-memory DB setup)
│   ├── test_backtester.py
│   ├── test_dropdown_parity.py
│   ├── test_portfolio_swap.py
│   ├── test_portfolio_tracker.py
│   ├── test_portfolio_tracker_edit.py
│   ├── test_portfolio_tracker_stock_name.py
│   ├── test_strategy_filters.py
│   ├── test_swing_tracker.py
│   └── test_tracker_linking.py
│
├── config/                       # Local configuration (gitignored)
├── data/                         # SQLite databases (gitignored)
│   ├── stockmon.db               #   Durable, backed up (portfolios, holdings, quotes)
│   ├── screener_cache.db         #   Disposable (rebuildable from API)
│   └── screener_cache.json       #   Screener nonce metadata
├── backups/                      # Online consistent compressed backups (gitignored)
└── logs/                         # Application, scheduler, and audit logs (gitignored)
```

---

## Setup & Installation

Requires **Python 3.10+** on Windows. **No API keys are required** — public endpoints are utilized. The desktop window is powered by [pywebview](https://pywebview.flowrl.com/).

```powershell
cd "C:\Users\hmaru\Downloads\Personal\Project\Daily Updater"

# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

On first run, `config/settings.json` and `config/portfolios.json` will be automatically generated from the template defaults.

### Building the Frontend

```powershell
cd frontend
npm install          # first time only
npm run build        # compiles to frontend/dist/
```

---

## Running the Application

```powershell
# Default: Launch as a native desktop window (starts maximized)
.\.venv\Scripts\python.exe app.py

# Optional: Run on a custom port
.\.venv\Scripts\python.exe app.py --port 8000

# Optional: Open in your default web browser instead of desktop window
.\.venv\Scripts\python.exe app.py --browser

# Optional: Development mode with Flask auto-reload
.\.venv\Scripts\python.exe app.py --debug
```

If no portfolio data has been fetched yet, click **Refresh now** in the UI header (or run `python scheduled_run.py` once) to populate the tables.

---

## Frontend Development

The frontend is built with **React**, **Bootstrap 5**, and **Lucide Icons** using **Vite**.

```powershell
cd frontend

# Start Vite dev server with hot-reload (proxies /api to Flask on port 5000)
npm run dev

# Compile production bundle into frontend/dist/ (served by Flask)
npm run build
```

---

## Tab Overview Summaries

### Tab 1: Portfolio Monitor (Tracker)
*Full details in [docs/TAB1_PORTFOLIO_MONITOR.md](docs/TAB1_PORTFOLIO_MONITOR.md)*

* **Portfolio Separation**: Monitors two distinct portfolios (**BAPA** and **MADI**).
* **Dual Timeframe EMAs**: Tracks the **9, 21, 50, 100, and 200 EMA** across both **Daily (D:)** and **Weekly (W:)** timeframes (10 values per ticker).
* **Display Rule**: Values are rendered in **red** only when the current price is below that EMA; otherwise, the space remains blank.
* **Priority Sorting**: Tickers breaching the 200 daily EMA appear at the very top (highest priority alert), followed by 100, 50, 21, and 9 EMA. Within the same priority, tickers sort alphabetically.
* **Signal Badge**: Clearly displays **`SELL`** (red) if below the daily 200 EMA, and **`HOLD`** (green) if holding above.
* **Smart History Switching**: Automatically checks alternate exchanges (`.NS` ↔ `.BO`) if a symbol has fewer than 400 trading bars.
* **Ticker CRUD**: Add and remove tickers directly from the UI with real-time symbol validation and duplicate checks.

---

### Tab 2: Portfolio Tracker
*Full details in [docs/PORTFOLIO_TRACKER.md](docs/PORTFOLIO_TRACKER.md)*

* **Transactional Holdings Ledger**: Track open positions across **MADI**, **BAPA**, and **LOAN** portfolios with full audit history.
* **Multi-Buy Aggregation**: Multiple buy lots per stock with expand/collapse rows showing individual cost basis, dates, and per-lot metrics.
* **FIFO Selling**: Sell workflow with automatic FIFO tranche allocation and realized gain/loss calculation.
* **Cross-Portfolio Transfers**: Swap holdings between portfolios (e.g., MADI ↔ BAPA) with automatic reparenting of all buy lots and sales.
* **Dividends & Summary**: Per-portfolio dividend tracking and loan balance sheet with user-entered summary metrics.
* **Excel Round-Trip**: Import holdings from `Invest.xlsx` workbook format and export back to Excel/CSV.
* **Cost-Basis Risk Pills**: Visual badges on the Tracker tab (Tab 1) indicating whether current price is above or below average buy price.

---

### Tab 3: Stock Status & Scenarios
*Full details in [docs/TAB2_STOCK_STATUS.md](docs/TAB2_STOCK_STATUS.md)*

* **Valuation Scenarios**: Record target price and expected CAGR (%) across **Base**, **Bull**, and **Bear** business cases.
* **Best Entry Tracking**: Specify target buy zones; the UI displays live percentage distances from the current price to your ideal entry price.
* **Status Badges**: Color-coded investment stances (`Buy`, `Avoid`, `Hold`, `Acc on dip`).
* **Multi-History Versioning**: Keep an audit trail of past analyses; switch between dates via the Date of Analysis dropdown to inspect how your thesis evolved over time.
* **Live Quotes & Local Cache**: Live market prices update on demand with background caching in `stockmon.db`.

---

### Tab 4: Market Screener & Predictive Analysis
*Full details in [docs/TAB3_MARKET_SCREENER.md](docs/TAB3_MARKET_SCREENER.md)*

* **Broad Market Universe**: Scan >3,400 NSE companies on demand from Prime Screener (`bigbreakingwire.in`).
* **Automated Daily Nonce**: Automatically discovers, caches, and rotates the required `X-WP-Nonce` daily.
* **154-Column Table**: Categorized column selector with frozen sticky columns, pagination, and TradingView chart links.
* **Multi-Day Sequence Analyzer**: Analyzes up to 11 chronological daily trading sessions to calculate predictive trajectory indicators:
  * `Accumulation Score (0–100)`: Quantifies institutional accumulation and flat-base coiling.
  * `Signal Freshness`: Pinpoints whether a breakout or trend flip occurred on Day 0/1 or is stale.
  * `VCP Compression Ratio`: Measures volatility contraction prior to expansion.
* **1-Click Strategy Presets**:
  * **Predictive Trajectory**: *Silent Accumulation*, *Fresh Signal Ignition*, *Multi-Day VCP Breakout*, *Staircase Buying*.
  * **Explosive 1–2 Day Setups**: *Institutional Blastoff*, *Coiled Spring Squeeze*, *Blue Sky ATH*, *8/8 Consensus*.
  * **Classical Momentum & Positional**: *BTST Surge*, *Swing Breakout*, *52W High*, *Dip Buyer*, *Compounders*, *High Delivery*.
* **Custom Filter Builder**: Multi-rule filter builder supporting 146 technical fields, column-to-column comparisons, and custom preset saving.

---

### Tab 5: Swing Tracker
*Full details in [docs/SWING_TRACKER.md](docs/SWING_TRACKER.md)*

* **Trade Journal**: Record swing trade setups with entry zones, stop losses, and multiple price targets.
* **Range Parsing**: Buy zones and targets specified as ranges (e.g., "100–120") with automatic midpoint calculations.
* **Percentage Distances**: Live percentage distance from current price to buy zone, stop loss, and each target.
* **Pattern Breakouts**: Track breakout patterns and thesis notes with preserved formatting.
* **Trade Sources**: Dynamic source tracking (e.g., "Self Analysis", custom sources) with persistent storage.
* **Bulk Price Refresh**: One-click refresh of current prices for all active swing trades, reusing Portfolio table quotes when available.
* **Auto-Refresh**: Automatic 9:30 AM IST price refresh on market open.

---

## Scheduled Runs & Windows Task Scheduler

Scheduled updates run twice daily on **weekdays (Monday–Friday)**.

### Registering or Updating the Task
The schedule times (default: **09:30** and **11:30**) can be configured directly from the UI or in `config/settings.json`. Saving times in the UI automatically synchronizes the Windows Task Scheduler.

To configure manually via PowerShell:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\register_task.ps1
```

### Unregistering or Disabling the Task
```powershell
# Remove the task completely
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\register_task.ps1 -Unregister

# Temporarily disable the task
Disable-ScheduledTask -TaskName "StockMonitor-DailyUpdate"

# Re-enable the task
Enable-ScheduledTask -TaskName "StockMonitor-DailyUpdate"
```

### Scheduled Execution Workflow
1. Runs `scheduled_run.py` at the scheduled times.
2. Checks the weekday guard (Mon–Fri only).
3. Atomically drains and consumes newly added tickers from `stockmon.db` (preventing lost updates).
4. Fetches market prices, recomputes EMAs, and updates the `tracker_snapshot` table in `stockmon.db`.
5. Refreshes current prices for all active Swing Tracker trades.
6. Increments `sync_state.version` in `stockmon.db`, triggering an instant SSE refresh on any open desktop window.
7. Prunes screener records older than `screener_retention_days` (default: 60 trading days) from `screener_cache.db`.
8. Takes an automatic online consistent compressed backup of `stockmon.db` into `backups/` and rotates old files.
9. Launches `show_window.py` to pop the window to the foreground as a visual alert.

---

## Configuration Reference

Settings are stored in `config/settings.json` (see `config.template.json`):

| Setting | Default | Description |
| :--- | :--- | :--- |
| `schedule.run_times` | `["09:30", "11:30"]` | Daily run times (24-hour `HH:MM`) |
| `schedule.timezone` | `Asia/Kolkata` | Market timezone reference |
| `schedule.task_name` | `StockMonitor-DailyUpdate` | Windows Task Scheduler task name |
| `data.default_exchange_suffix` | `.NS` | Default exchange suffix for bare symbols |
| `data.history_period` | `10y` | Historical period fetched for EMA calculation |
| `data.ema_periods` | `[9, 21, 50, 100, 200]` | Tracked EMA periods |
| `data.max_workers` | `4` | Concurrency for background downloads |
| `data.retries` / `data.retry_backoff_seconds` | `2` / `1.5` | Retry attempts and backoff duration |
| `data.screener_retention_days` | `60` | Number of recent trading days of screener history to keep |
| `ui.status_poll_seconds` | `5` | Fallback polling interval if SSE disconnects |
| `ui.price_decimals` | `2` | Number of decimal places rendered in tables |

---

## Error Handling & Logging

All events and anomalies are logged to rotating files in `logs/`:

| Log File | Description |
| :--- | :--- |
| `logs/app.log` | Flask web server logs, API requests, and UI operations. |
| `logs/scheduler.log` | Summary records of scheduled runs, processed tickers, and network errors. |
| `logs/ticker_additions.log` | Audit trail of all ticker additions made through the UI. |
| `logs/scheduled_run_console.log` | Full console stdout/stderr from Task Scheduler runs. |

---

## HTTP API Reference

The Flask backend provides clean REST endpoints and real-time SSE streaming.

### Core Tracker

| Method & Path | Description |
| :--- | :--- |
| `GET /` | Serves the single-page React desktop application. |
| `GET /api/data` | Returns raw snapshot JSON. |
| `GET /api/tables` | Returns portfolio tables data and summary stats. |
| `GET /api/status` | Returns current data version counter and last-run summary. |
| `POST /api/refresh` | Triggers immediate re-fetch and EMA recomputation for all portfolios. |
| `POST /api/tickers` | Validates, fetches, and appends a new ticker `{portfolio, symbol}`. |
| `DELETE /api/tickers` | Removes a ticker from a portfolio `{portfolio, symbol}`. |
| `GET /api/schedule` | Returns configured scheduled run times. |
| `POST /api/schedule` | Updates scheduled run times `{run_times: [...]}`. |
| `GET /api/stream` | Server-Sent Events (SSE) feed notifying clients of version updates. |
| `GET /api/stock-info?symbol=...` | Fetches live market price and official company name for a single ticker. |
| `POST /api/stock-quotes` | Batch fetches live market prices and timestamps for multiple tickers. |

### Stock Status

| Method & Path | Description |
| :--- | :--- |
| `GET /api/stock-status` | Retrieves all saved stock status and scenario analysis entries. |
| `POST /api/stock-status` | Saves a new stock status/scenario analysis entry. |
| `PUT /api/stock-status/<id>` | Updates an existing stock status entry. |
| `DELETE /api/stock-status/<id>` | Deletes a stock status entry. |

### Market Screener

| Method & Path | Description |
| :--- | :--- |
| `GET /api/screener/data?date=...` | Returns cached screener records and available historical dates. |
| `POST /api/screener/fetch` | Triggers on-demand screener fetch `{nonce, date, search, per_page}`. |
| `GET /api/screener/detect-nonce` | Auto-detects and returns active `X-WP-Nonce` from the screener site. |
| `POST /api/screener/sync-history` | Synchronizes available past trading dates into local cache. |
| `GET /api/screener/multi-day-analysis` | Computes multi-day sequence metrics and returns ranked setups. |
| `POST /api/screener/backtest` | Runs a backtest strategy against screener data. |
| `POST /api/screener/rebuild` | Triggers background historical screener re-fetch. |

### Backup & Restore

| Method & Path | Description |
| :--- | :--- |
| `POST /api/backup/create` | Triggers immediate online consistent backup of `stockmon.db`. |
| `GET /api/backup/list` | Returns manifest of backups, sizes, SHA-256 checksums, and staleness warning. |
| `POST /api/backup/restore` | Safely restores durable database from a chosen backup file `{filename}`. |

### Portfolio Tracker

| Method & Path | Description |
| :--- | :--- |
| `GET /api/portfolio-tracker/<portfolio>` | Returns all holdings, lots, sales, dividends, and summary for a portfolio. |
| `GET /api/portfolio-tracker/lookup-ticker` | Searches and validates a ticker symbol with live price. |
| `POST /api/portfolio-tracker/holding` | Creates a new holding with initial buy lot. |
| `POST /api/portfolio-tracker/lot` | Adds a buy lot to an existing holding. |
| `DELETE /api/portfolio-tracker/holding/<id>` | Deletes a holding and all its lots, sales, and dividends. |
| `DELETE /api/portfolio-tracker/lot/<id>` | Deletes an individual buy lot. |
| `PUT /api/portfolio-tracker/lot/<id>` | Updates a buy lot (date, quantity, price, app, remarks). |
| `PUT /api/portfolio-tracker/holding/<id>` | Updates holding metadata (scheme name, stock name, app, person). |
| `POST /api/portfolio-tracker/swap` | Transfers a holding between portfolios (e.g., MADI → LOAN). |
| `PUT /api/portfolio-tracker/sold/<id>` | Updates a sold holding's metadata and notes. |
| `POST /api/portfolio-tracker/sell` | Sells a position (FIFO tranche allocation). |
| `PUT /api/portfolio-tracker/notes/<id>` | Updates buy/sell reason and mistake notes on a holding. |
| `GET /api/portfolio-tracker/mistakes` | Returns all holdings with learning notes. |
| `POST /api/portfolio-tracker/dividend` | Records a dividend for a portfolio. |
| `DELETE /api/portfolio-tracker/dividend/<id>` | Deletes a dividend record. |
| `GET /api/portfolio-tracker/summary` | Returns Loan Summary panel values. |
| `PUT /api/portfolio-tracker/summary` | Updates Loan Summary panel values. |
| `POST /api/portfolio-tracker/import` | Imports holdings from an Excel workbook. |
| `GET /api/portfolio-tracker/export` | Exports portfolio data as Excel or CSV. |

### Swing Tracker

| Method & Path | Description |
| :--- | :--- |
| `GET /api/swing-tracker` | Returns all swing trade setups. |
| `POST /api/swing-tracker` | Creates a new swing trade entry. |
| `PUT /api/swing-tracker/<id>` | Updates a swing trade entry. |
| `DELETE /api/swing-tracker/<id>` | Deletes a swing trade entry. |
| `POST /api/swing-tracker/<id>/refresh-price` | Refreshes current price for a single swing trade. |
| `POST /api/swing-tracker/refresh-all` | Bulk refreshes prices for all swing trades. |
| `GET /api/swing-tracker/sources` | Lists all persisted trade sources. |
| `POST /api/swing-tracker/sources` | Creates a new trade source option. |
| `GET /api/swing-tracker/lookup-ticker` | Validates a ticker and resolves price (portfolio table first, then live). |

---

## Backup, Restore & Disaster Recovery

### Safe Online Backups
* Backups run **automatically** at the end of every scheduled market run, and can also be triggered on demand via `POST /api/backup/create`.
* **7-Day Retention**: The system automatically retains **1 week (7 backups)** of daily snapshots; older backups are automatically pruned to prevent clutter.
* Backups only snapshot irreplaceable user data from `data/stockmon.db` (compressed to ~10–15 KB). Market screener data in `data/screener_cache.db` is disposable and rebuilt on demand from the upstream API.

### What is Inside `backups/` and What Each File Does
When copying to Google Drive or an external disk, copy the `backups/` directory:

| File Pattern | Description & Purpose |
| :--- | :--- |
| `stockmon-YYYY-MM-DD_HHMMSS.db.gz` | **Main Database Snapshot**: Contains your portfolios, stock status valuation records, and tracker snapshots. This is the primary file needed to restore your state. |
| `settings-YYYY-MM-DD_HHMMSS.json` | **Configuration Snapshot**: Backup of your `config/settings.json` (EMA periods, schedule times, retry options). |
| `manifest.json` | **Audit Ledger**: Contains SHA-256 integrity checksums, timestamps, row counts, and schema versions for every generated backup. |

### How to Copy to Google Drive Manually
1. Open your project root folder and locate the `backups/` directory.
2. Drag and drop the `backups/` folder (or just the latest `stockmon-*.db.gz` and `settings-*.json`) directly into your Google Drive or external storage.
3. *Note*: Never put the live `data/` folder itself inside a cloud-synced folder (sync conflicts can corrupt live SQLite databases in WAL mode). Always sync the static files in `backups/` instead.

### Manual CLI Disaster Recovery (Without Starting the App)
If the application is stopped or you are moving to a new PC and need to restore:
```powershell
# 1. Decompress your chosen backup file directly to data/stockmon.db
python -c "import gzip, shutil; shutil.copyfileobj(gzip.open('backups/stockmon-2026-09-06_192451.db.gz', 'rb'), open('data/stockmon.db', 'wb'))"

# 2. Copy the paired settings file into config/settings.json (optional)
Copy-Item "backups/settings-2026-09-06_192451.json" "config/settings.json"

# 3. Start the application (screener cache will re-sync from API if needed)
python app.py
```

### Automatic 1-Day Log Cleanup
All application and scheduler logs in `logs/` are automatically rotated and pruned:
* Log files or rolled-over logs older than **1 day** are automatically purged on startup and after every scheduled market run.

### Emergency JSON Export (Escape Hatch)
To dump the entire SQLite database back into raw, human-readable JSON files:
```powershell
python scripts/export_to_json.py --output-dir exported_json/
```

---

## Known Limitations & Planned Features

### Limitations
* **Local Single-User Architecture**: Built for local desktop use; does not require authentication.
* **Public Data Endpoints**: Market data relies on Yahoo Finance (`yfinance`) and Prime Screener; subject to intermittent network latency or rate-limiting.
* **Active Machine Requirement**: Scheduled runs execute via Windows Task Scheduler; machine must be active or awake.

### Roadmap
* [ ] Alerts: Native desktop toast or notification sound when prices cross watched EMAs.
* [ ] Direct Broker Integration: Pluggable fallback data providers (e.g. Zerodha Kite, Upstox).
* [ ] Portfolio Customization: Support creating, renaming, and deleting custom portfolios from the UI.
* [ ] Backtester UI: Frontend interface for the existing backtest strategy engine.
