# Portfolio Tracker Feature Documentation

## 1. Overview

The **Portfolio Tracker** tab is a comprehensive financial ledger and performance analytics suite built into the Portfolio and Stock Monitor desktop/web application. It provides transaction-level tracking of stock purchases, multi-buy dollar-cost averaging, realized exits, dividend income, and loan balance sheet accounting for three distinct portfolios:

- **`MADI`**: Personal trading portfolio
- **`BAPA`**: Personal investment portfolio
- **`LOAN`**: Leveraged loan-funded portfolio, with holdings mapped to individuals (`MADI` or `BAPA`)

All data is persistently stored in the durable SQLite database (`data/stockmon.db`, schema version 2), with automatic backup generation on every financial modification.

---

## 2. Architecture & Data Model

Following the architecture principle *"Store inputs, compute derivatives"*, only human-entered transactional inputs are persisted. Derived metrics (years, months, total invested, statutory buy/sell charges, earned profit, loss, CAGR, and total return percentages) are computed deterministically at read time.

```
                    ┌─────────────────────────┐
                    │      portfolio          │
                    │   (BAPA, MADI, LOAN)    │
                    └───────────┬─────────────┘
                                │ 1:N
                    ┌───────────▼─────────────┐
                    │       holding           │
                    │ (status: 'open'|'sold') │
                    └─────┬─────────────┬─────┘
                      1:N │             │ 1:1
       ┌──────────────────▼──┐       ┌──▼────────────────┐
       │      buy_lot        │       │       sale        │
       │ (individual buys)   │       │ (realized exit)   │
       └─────────────────────┘       └───────────────────┘

       ┌─────────────────────┐       ┌───────────────────┐
       │      dividend       │       │   summary_value   │
       │ (symbol, value, dt) │       │ (fixed panel figs)│
       └─────────────────────┘       └───────────────────┘
```

### 2.1 Database Tables (`schema_v2.sql`)

1. **`holding`**:
   - `id`: Integer primary key
   - `portfolio_name`: References `portfolio(name)`
   - `symbol`: Uppercase ticker (e.g. `TATAGOLD`, `RELIANCE.NS`)
   - `scheme_name`: Auto-fetched company name or manually confirmed text
   - `stock_name`: Official company name auto-resolved via ticker lookup (or manually confirmed)
   - `name_confirmed`: Boolean flag (`1`/`0`) indicating whether the stock name has been verified via lookup or explicit user confirmation
   - `person`: For `LOAN` portfolio (`MADI` | `BAPA`)
   - `app`: Origin platform/account (e.g. `Kite`, `Kite Madi`, `Kite Bapa`)
   - `remarks`: User tags (e.g. `ETF`, `Swing Self`, `PEAD`)
   - `bought_reason`, `sold_reason`, `mistake_learned`: Per-stock trading journal notes (§6)
   - `status`: `'open'` or `'sold'`
   - Index: Unique `(portfolio_name, symbol)` where `status = 'open'`

2. **`buy_lot`**:
   - `holding_id`: Foreign key with `ON DELETE CASCADE`
   - `invest_date`: Buy date (`YYYY-MM-DD`)
   - `quantity`: Number of shares
   - `avg_price`: Buy price per share
   - `buy_charge`: Manual override or calculated statutory charge

3. **`sale`**:
   - `holding_id`: Foreign key with `ON DELETE CASCADE`
   - `sell_date`: Exit execution date
   - `quantity`: Number of shares sold
   - `sell_price`: Realized exit price per share
   - `sell_charge`: Realized statutory exit charge

4. **`dividend`**:
   - `portfolio_name`: References `portfolio(name)`
   - `symbol`: Ticker symbol
   - `value`: Cash dividend received in ₹
   - `received_date`: Term or ISO date string

5. **`summary_value`**:
   - `key`: Identifier (e.g. `loan_amount`, `current_mf_invest`, `current_mf_redeem`)
   - `value`: Real numeric value
   - `label`: Human-readable display label

### 2.2 Ticker Lookup & Name Validation

To prevent invalid or mismatched stock data, ticker entry across all modals (**Add Holding**, **Edit Holding**, and **Edit Sold Position**) is standardized via a shared lookup hook (`useTickerLookup`):
- **User provides only the ticker**: Entering or modifying the ticker triggers an automatic lookup against the live quoting engine (`/api/portfolio-tracker/lookup-ticker`).
- **Automatic Stock Name Population**: When recognized, the official company name is fetched and populated automatically.
- **Clear Error Surfacing**: If a ticker is invalid, delisted, or unrecognized, a warning alert is immediately displayed. The user must either correct the ticker or enter a manual company name and explicitly check the confirmation checkbox (`name_confirmed`) before saving.

### 2.3 Portfolio Row Swapping (`/api/portfolio-tracker/swap`)

Holdings can be moved between `LOAN`, `MADI`, and `BAPA` portfolios either individually (via the row Swap icon) or in batches (via multi-select checkboxes and the "Swap Selected" button):
- **Swapping to `LOAN`**: Prompts for destination person (`MADI` or `BAPA`).
- **Swapping to `MADI` or `BAPA`**: Clears person assignment.
- **Unique Constraint & Lot Merging**: If the destination portfolio already holds an open position for the same symbol, the incoming holding's buy lots are automatically re-parented into the existing destination holding and the source container is cleanly retired, preserving all lot purchase histories without constraint collisions.

### 2.4 Tracker Tab Cost-Basis Risk Indicator

Positions on the Tracker tab that are sourced from Portfolio Tracker automatically compare their live market price against their weighted average purchase price (`avg_price`). When a position trades below its cost basis, an inline risk pill is displayed stacked directly below the Avg Price value using a graduated three-tier severity model:
- **Tier 1 (Mild / Watch)**: `0.01%` to `4.99%` below cost basis. Rendered as a soft amber pill (`▼ -2.4%`, minor pullback).
- **Tier 2 (Stop-Loss Zone / Warning)**: `5.00%` to `9.99%` below cost basis. Rendered as an orange pill (`▼ -6.8%`, typical stop-loss action zone).
- **Tier 3 (Critical)**: `10.00%` or more below cost basis. Rendered as a crimson red pill (`▼ -12.5%`, critical drawdown).
- **At or Above Cost Basis (`price >= avg_price`)**: No risk pill displayed (clean numeric display).
- **Unowned Watchlist Tickers (`avg_price is None`)**: No risk pill displayed.

---

## 3. Financial Calculations (`stockmon/portfolio_tracker.py`)

All formulas are standardized and verified against the user's `Invest.xlsx` workbook:

| Metric | Formula / Derivation |
| :--- | :--- |
| **Invested Amount** | `Quantity × Average Price` |
| **Holding Period** | `DATEDIF(Invest Date, Current Date, "M")` and `Years = Months // 12` |
| **Statutory Buy Charge** | `(NSE 0.00345% + SEBI 0.0001% + Stamp 0.015% + STT 0.1%) × Invested + GST 18% on NSE` $\approx 0.119171\%$ |
| **Statutory Sell Charge** | `(STT 0.1% + NSE 0.00345% + SEBI 0.0001%) × Current Total + GST 18% on NSE` $\approx 0.104171\%$ |
| **Current Total** | `Quantity × LTP` (live quote or realized sell price) |
| **Earned (Profit)** | `Current Total - Invested - Buy Charge - Sell Charge` (if positive, else 0) |
| **Loss** | `-(Invested + Buy Charge + Sell Charge - Current Total)` (if negative, else 0) |
| **Total Return %** | `((Current Total / Invested) - 1) × 100` |
| **Annual Return %** | CAGR if period $\ge 1$ year: `((Current Total / Invested)^(1 / Years) - 1) × 100`; simple annualized if $< 1$ year |

---

## 4. Multi-Buy Aggregation (§2.2)

When a stock is purchased across multiple transactions at different price points:
1. The backend aggregates all `buy_lot` entries into a single parent row:
   $$\text{Total Quantity} = \sum Q_i$$
   $$\text{Total Invested} = \sum (Q_i \times \text{Price}_i)$$
   $$\text{Weighted Average Price} = \frac{\text{Total Invested}}{\text{Total Quantity}}$$
2. In the UI, stocks with `lot_count > 1` render an interactive `+ / −` expand control.
3. Expanding reveals the nested child lot table showing each tranche's buy date, quantity, price, charges, and individual P&L.
4. Child lots can be deleted individually without deleting the parent holding, or additional buy lots can be appended at any time.

---

## 5. Summary Panel (§8)

Available on the `LOAN` portfolio to track capital deployment, loan payoff, and net remaining surplus:

### Block A: Capital Deployment
- **Current Stock & ETF Invest**: Sum of open loan stock holdings (or user fixed override)
- **Current MF Invest**: Fixed user entry
- **Current MF Redeem**: Fixed user entry
- **Total**: Sum of the three above

### Block B: Loan & Profit Balance
- **Loan Amount**: Fixed principal borrowed
- **Remaining Invest From Loan**: `Total - Loan Amount`
- **Stock Profit**: Realized & unrealized gains (`Earned + Loss`)
- **Dividend**: Sum of all dividends received
- **Current MF Redeem + Profit**: Fixed user entry
- **Current Remaining**: Net cash balance ($= \text{Remaining Invest} + \text{Stock Profit} + \text{Dividend} + \text{MF Redeem+Profit}$)

---

## 6. Excel Import & Export Workflows

- **Import (`/api/portfolio-tracker/import`)**:
  - Uploads an XLSX file or imports the local `Invest.xlsx`.
  - Runs in a single atomic database transaction with rollback protection.
  - Safe against duplicate insertions: requires explicit confirmation before replacing existing data.
  - Automatically merges multi-buy rows into aggregated holdings with child lots.
  - Flags and preserves manual override entries (e.g. advisory deductions, custom notes).
  - *Note*: The UI "Import Sheet" button is temporarily hidden (see §7).
- **Export (`/api/portfolio-tracker/export`)**:
  - Two export operations available in the UI action bar:
    - **`Excel (All)`**: Generates a consolidated workbook containing all three portfolio tabs (`Stock Madi`, `Stock Bapa`, `Loan `).
    - **`{activePortfolio} (.xlsx)`**: Generates a single `.xlsx` workbook containing only the currently active portfolio tab (`Stock Madi`, `Stock Bapa`, or `Loan `).
  - Both export options faithfully cover Open Holdings, Sold Positions, and Dividends. For `Loan `, the Balance Sheet Summary Panel (Cols 39–40) is included.
  - Generates byte-compatible XLSX workbooks matching the layout and column structure of `Invest.xlsx` (including the `Current Date` column in exported sheets for 100% round-trip fidelity).
  - In the native desktop shell (`pywebview`), downloads are enabled via `webview.settings["ALLOW_DOWNLOADS"] = True` in `app.py` and `show_window.py`, prompting a native Windows Save File dialog.

---

## 7. Temporarily Hidden UI Controls & Re-enabling Guide

To streamline the user interface, certain controls and columns have been temporarily hidden in the UI without deleting any underlying backend, API, or computation logic:

### 7.1 Hidden Elements
1. **"Import Sheet" button**:
   - **Location**: Top action bar of the Portfolio Tracker tab.
   - **Status**: Hidden in UI. The modal, file upload pipeline, atomic database ingestion, and `/api/portfolio-tracker/import` backend logic remain completely functional.
2. **"Current Date" column in Open Holdings**:
   - **Location**: Open Holdings table (`<th>Current Date</th>` and respective cells in parent and child lot rows).
   - **Status**: Hidden in UI. All holding duration metrics ($Y$ years, $M$ months) continue to calculate accurately against today's date in real time. The exported `.xlsx` workbook retains the `Current Date` column to maintain full structure parity with `Invest.xlsx`.

### 7.2 Instructions to Re-enable / Unhide
Both elements are controlled by clean boolean feature flags located at the top of [frontend/src/components/PortfolioTrackerTab.jsx](../frontend/src/components/PortfolioTrackerTab.jsx):

```javascript
// Feature flags for temporarily hidden UI elements (see docs/PORTFOLIO_TRACKER.md §7)
// Set either flag to true to re-enable the respective control in the UI
const SHOW_IMPORT_BUTTON = false;
const SHOW_CURRENT_DATE = false;
```

To re-enable either or both elements:
1. Open `frontend/src/components/PortfolioTrackerTab.jsx`.
2. Toggle the desired flag(s) to `true`:
   - To unhide the Import Sheet button: change `SHOW_IMPORT_BUTTON = false;` to `SHOW_IMPORT_BUTTON = true;`.
   - To unhide the Current Date column: change `SHOW_CURRENT_DATE = false;` to `SHOW_CURRENT_DATE = true;`.
3. Rebuild the frontend bundle by opening a terminal in the project root and running:
   ```bash
   cd frontend
   npm run build
   ```
4. Restart or refresh the application. The controls will be immediately restored with automatic table alignment and column span adjustments.
