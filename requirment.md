# Feature Request: Portfolio Tracker (new tab)

> **Terminology:** the existing Tab 1 is called **Tracker / Portfolio Monitor** (EMA dashboard for portfolios `BAPA` and `MADI`). The feature below is a **new, separate tab** named **Portfolio Tracker** (holdings, cost, P&L). Wherever this document says "Tracker tab", it means the **existing** Tab 1.

> **Storage baseline:** the SQLite migration is **done** — `data/stockmon.db` (durable, backed up) and `data/screener_cache.db` (disposable) are live, with `PRAGMA user_version` migrations in `stockmon/db/migrations.py` and all SQL confined to `stockmon/db/repositories/`. This feature is built **on the database**, not on JSON files. See §1.4.

---

## 1. Scope

Add a new tab, **Portfolio Tracker**, tracking actual holdings (buy price, quantity, charges, profit/loss) for three portfolios:

| Portfolio | Notes |
| --- | --- |
| `BAPA` | Personal portfolio |
| `MADI` | Personal portfolio |
| `LOAN` | Loan-funded portfolio. Has one extra field: **Person** (`MADI` or `BAPA`) |

Each portfolio is rendered **separately** (its own table/section). A table is the default idea — propose a better layout if one exists.

### 1.1 Initial data source (Google Sheet) — [COMPLETED]

> **Status: COMPLETED.** Implemented in `stockmon/sheet_io.py:import_workbook`. One transaction, idempotent-safe, multi-buy aggregation, preservation and reporting of manual override values.

### 1.2 Capture the sheet format on import (prerequisite for export) — [COMPLETED]

> **Status: COMPLETED.** `Invest.xlsx` has been inspected and captured in `docs/SHEET_FORMAT.md` and `stockmon/sheet_format.py`. Both the importer and exporter use this shared specification.

The workbook has been inspected and persisted as a reusable format definition:

| What to record | Why |
| --- | --- |
| Sheet/tab names and their order (`Madi`, `Bapa`, `Loan`, …) | Export must recreate the same tabs |
| Exact header text, spelling and column order of every column | Export must be byte-compatible so the user can paste it back into their own sheet |
| The header row index, and how many rows above it are titles/blank | Parser needs to know where data starts |
| Date format used (`DD-MM-YYYY`, `DD/MM/YY`, serial number, …) | Round-trip must not shift dates |
| Number format: currency symbol, thousands separator, decimal places, how negatives are shown (`-433821.90` vs `(433,821.90)`) | Round-trip must not corrupt values |
| How **multiple buys of the same stock** are laid out (repeated rows? a parent row plus indented children? a merged cell?) | Maps to `holding` → `buy_lot` (§2.2) |
| How **sold** rows are represented (separate block, separate sheet, or a status column?) | Maps to `sale` (§4) |
| Where the **dividend** block lives on each sheet and its column headers | Maps to `dividend` (§7) |
| Where the **Summary panel** values sit on the `Loan` sheet (exact cell addresses / labels) | Maps to `summary_value` (§8) |
| Which columns are formulas in the sheet vs typed values | Formula columns are **computed**, not imported or stored (§1.4) |
| The `Person` column values on the `Loan` sheet | Maps to `holding.person` (§2.1 col 17) |

The same format definition is then used by **both** the importer and the exporter, so the two can never drift apart.

### 1.3 Export back to the Google Sheet format — [COMPLETED]

> **Status: COMPLETED.** Implemented in `stockmon/sheet_io.py:export_workbook`. Exports exact sheets `Stock Madi`, `Stock Bapa`, `Loan ` with identical layout, headers, computed totals, dividends, and Loan Summary panel.

* Output: a single **XLSX** file with the same tabs (`Madi`, `Bapa`, `Loan`), same headers, same column order, same date/number formatting — plus **CSV per sheet** as a secondary option.
* Includes: holdings (with their individual buy lots laid out the same way the source sheet lays them out), sold rows, dividends, and the Summary panel values on the `Loan` sheet.
* Computed columns (§1.4) are written out as **values**, calculated by the app.
* Triggered from the Portfolio Tracker tab (an **Export** button, optionally scoped to one portfolio or all three).
* **Round-trip requirement:** exporting and then re-importing the produced file must yield the same data. This is the acceptance test for both features.

Purpose: the user keeps their existing spreadsheet workflow available — they can export at any time, work in Google Sheets, and (if needed) bring new data back in through the §1.1 importer.

### 1.4 Storage — SQLite database (decided)

The project has **already migrated from JSON files to SQLite** (see [docs/DATA_STORAGE_MIGRATION.md](docs/DATA_STORAGE_MIGRATION.md)). This feature stores **all** of its data in the durable database — no new JSON files.

| Decision | Detail |
| --- | --- |
| Database file | `data/stockmon.db` — the durable, backed-up database (the disposable `data/screener_cache.db` is **not** used by this feature) |
| Schema | Added by **migration v2** (`_v2_portfolio_tracker`) in `stockmon/db/migrations.py` — **[COMPLETED]** |
| Tables | `holding`, `buy_lot`, `sale`, `dividend`, `summary_value` — created via `stockmon/db/schema_v2.sql` — **[COMPLETED]** |
| Portfolio rows | `LOAN` is inserted into the existing `portfolio` table alongside `BAPA` and `MADI` |
| SQL location | **All** SQL lives in `stockmon/db/repositories/` (`holdings.py`, `dividends.py`, `summary.py`) — **[COMPLETED]** |
| Business logic | `stockmon/portfolio_tracker.py` owns every calculation and is the only place formulas live — **[COMPLETED]** |
| Import/export | `stockmon/sheet_io.py` handles §1.1 import and §1.3 export, driven by the §1.2 format definition — **[COMPLETED]** |
| API | New Flask routes in `stockmon/web/routes.py`, following the existing `/api/...` JSON convention — **[COMPLETED]** |
| Backups | Writes to holdings/sales/dividends trigger the existing debounced "edit" backup job — this is irreplaceable financial data |

**Store inputs, compute derivatives.** Only user-entered values are persisted. Of the 18 columns in §2.1, just these are stored: `invest_date`, `quantity`, `avg_price`, `person`, `remarks`, `scheme_name`, the §6 note fields, and — frozen at sale time — `sell_date`, `sell_price` and sold `quantity`. Everything else (Y, M, Invested Amount, Buy Charge, Sell Charge, Current Total, Earned, Loss, Annual Return, Total Return) is **calculated at read time**, so changing a formula never requires a data migration.

---

## 2. Holdings table (per portfolio) — [COMPLETED]

### 2.1 Columns

| # | Column | Type | Source |
| --- | --- | --- | --- |
| 1 | Scheme | text | Stock name, auto-fetched from the ticker |
| 2 | Invest Date | date | User input (buy date) |
| 3 | Current Date | date | Today while open; the sell date once sold |
| 4 | Y (Years) | number | Calculated from Invest Date → Current Date |
| 5 | M (Months) | number | Calculated from Invest Date → Current Date |
| 6 | Q (Quantity) | number | User input |
| 7 | Avg (Average Price) | number | User input per buy; averaged across multiple buys |
| 8 | LTP (Last Traded Price) | number | Live quote; user-editable when selling |
| 9 | Invested Amount | number | Calculated (`Q × Avg`) |
| 10 | Buy Charge | number | Calculated from Invested Amount |
| 11 | Sell Charge | number | Calculated from Current Total |
| 12 | Current Total | number | Calculated (`Q × LTP`) |
| 13 | Earned | number | Calculated (profit, when positive) |
| 14 | Loss | number | Calculated (loss, when negative) |
| 15 | Annual Return | % | Calculated from the holding period |
| 16 | Total Return | % | Calculated |
| 17 | Person | `MADI` \| `BAPA` | **LOAN portfolio only**, user selects one |
| 18 | Remarks | text | User input |

Calculation dependencies:

* **Y** and **M** are derived from **Invest Date** and **Current Date**.
* **Buy Charge**, **Sell Charge**, **Current Total**, **Earned**, **Loss**, **Annual Return** and **Total Return** are all derived from **Avg**, **LTP** and **Invested Amount**.
* **Person** (LOAN only) is later used to route rows into the existing Tracker tab — see section 9.

Only the input columns are written to the database; the rest are computed on read — see §1.4.

### 2.2 Row grouping (multiple buys of the same stock) — [COMPLETED]

* A stock may be bought **once**, or **several times at different prices**.
* **Bought once** → render a single plain row.
* **Bought multiple times** → render **one aggregated parent row** (total quantity, total invested, weighted average price) with an **expand/collapse (+/−) control** that reveals the individual buy transactions as child rows.

### 2.3 Row actions — [COMPLETED]

* **Delete row** — a row added by mistake, or a holding that is no longer needed, must be deletable **without** going through the sell flow (it must not appear in the Sold table). Deleting a holding cascades to its buy lots (`ON DELETE CASCADE`); deleting a single child buy lot leaves the parent holding and re-aggregates the remaining lots.

---

## 3. Adding a holding — [COMPLETED]

The user provides only:

1. **Ticker** → the system fetches the stock name (Scheme) automatically.
2. **Current Date** (buy date)
3. **Q** (quantity)
4. **Avg** (average buy price)
5. **Remarks**

Everything else is calculated.

**Edge case:** if the stock name cannot be fetched for a ticker, accept a **manually typed name**, but require the user to **confirm** it before saving.

---

## 4. Selling a holding — [COMPLETED]

* To sell, the user **edits LTP and Current Date**; every other value recalculates automatically.
* On sell, the holding **moves out of the Holdings table into a separate "Sold" table**.
* The Sold table uses the **same column format** and is shown **per portfolio** (a portfolio's Sold table lists only that portfolio's sold stocks).

---

## 5. Totals row (both Holdings and Sold tables) — [COMPLETED]

Each table ends with a totals row showing:

* Total Invested Amount (all rows)
* Total Current Total (all rows)
* Total Earned
* Total Loss
* Net Profit = Total Current Total − Total Invested Amount

---

## 6. Per-stock notes (bought reason / sold reason / lessons) — [COMPLETED]

Each stock row carries three free-text fields:

* **Bought Reason**
* **Sold Reason**
* **Mistake / Learned**

They are **hidden by default** and opened on demand (e.g. a row button that opens a panel or modal).

* **Consolidated view:** implemented with the "Mistakes & Lessons" modal listing all past recorded lessons across portfolios.

---

## 7. Dividends (per portfolio) — [COMPLETED]

Each portfolio keeps its own dividend list, shown separately:

| Column | Type |
| --- | --- |
| Symbol | text |
| Value | number |
| Date | date |

---

## 8. Summary panel (below the portfolios) — [COMPLETED]

A mix of **fixed (user-entered)** and **calculated** values. The initial values come from the **Loan sheet** of the Google Sheet described in section 1.1.

### Block A

| Label | Example value | Source |
| --- | --- | --- |
| Current Stock & ETF Invest | 5,213,974.77 | Fixed |
| Current MF Invest | ₹1,300,000 | Fixed |
| Current MF Redeem | ₹450,000 | Fixed |
| **Total** | 6,963,974.77 | Sum of the three rows above |

### Block B

| Label | Example value | Source |
| --- | --- | --- |
| Loan Amount | ₹6,530,152.87 | Fixed |
| Remaining Invest From Loan | −₹433,821.90 | `Loan Amount − Total` |
| Stock Profit | 586,778.17 | `LOAN portfolio Earned − LOAN portfolio Loss` |
| Dividend | 1,093.00 | Sum of all dividend values |
| Current MF Redeem + Profit | ₹474,623 | Fixed |
| **Current Remaining** | ₹628,672.27 | Sum of: Remaining Invest From Loan + Stock Profit + Dividend + Current MF Redeem + Profit |

The **Fixed** values are stored in the `summary_value` table (key/value/label) and are editable in the UI. The **calculated** values are never stored.

---

## 9. Integration with the existing Tracker tab (Tab 1)

Today, rows in the existing Tracker tab are added **manually**. After this feature ships:

* The **MADI** Tracker table is populated automatically from the **MADI** Portfolio Tracker holdings, **plus** the `LOAN` portfolio rows where `Person = MADI` (all other required values are fetched for those tickers).
* The same applies to **BAPA** (BAPA holdings + `LOAN` rows where `Person = BAPA`).
* A ticker is **removed from the Tracker tab only when the stock is sold** in the Portfolio Tracker.

Because holdings now live in the database, the existing hand-maintained `portfolio_ticker` table can become a **view derived from `holding`** (`WHERE status = 'open'`), which removes the possibility of the two lists drifting apart. Do this as a follow-up once the tab is working, not as part of the initial build.

---

## 10. Phase 2 (after the above is implemented): buy/sell analysis

* Using the **saved Screener data** (current and previous days), analyse a stock named by the user and produce a **buy or sell recommendation** — "is this a good price/time to buy?" and the equivalent for selling.
* **Must display a disclaimer**: this is a purely technical calculation; fundamentals, events and news can change the decision.

---

## 11. Phase 3 (after Phase 2): risk-management column in the Tracker tab

* In the existing **Tracker tab**, every company in the portfolio is available along with its **average buy price**.
* Add a new column **Avg** showing the average buy price, positioned **before the Current Price column**.
* Derived from Avg, add a **risk-management calculation** comparing **average buy price vs current price**, to flag positions moving against the user where the loss could grow further — effectively an **exit signal**.
  * Position **against** the user → show the percentage in **red** (possible exit signal).
  * Position **in favour** of the user → show nothing, or the percentage in **green**.

**Open question:** the exact risk formula and thresholds are undecided — a proposal is needed (e.g. % drawdown from average price, ATR-based stop, or a breach of a specific EMA).

---

## Open questions summary

1. `Q` = Quantity — please confirm (originally written as "Quality").
2. ~~Exact Buy Charge / Sell Charge formulas.~~ **Answered:** Verified from `Invest.xlsx` formulas:
   - Buy Charge: `(0.0000345 [NSE] + 0.000001 [SEBI] + 0.00015 [Stamp] + 0.001 [STT]) * Invested + 0.18 * (0.0000345 * Invested) [GST]` = `0.00119171 * Invested` (with support for manual override values).
   - Sell Charge: `0.0010355 * Current_Total + 0.18 * (0.0000345 * Current_Total)` = `0.00104171 * Current_Total`.
3. Annual Return formula — simple annualised return, or CAGR? (CAGR implemented by default).
4. ~~Storage location for holdings.~~ **Answered:** SQLite — `data/stockmon.db`, migration v2, tables `holding` / `buy_lot` / `sale` / `dividend` / `summary_value`. See §1.4.
5. Risk-management formula and thresholds for Phase 3.
6. ~~Google Sheet import mechanism.~~ **Answered:** XLSX/CSV file upload, no Sheets API. Workbook provided as `Invest.xlsx` and format captured in `docs/SHEET_FORMAT.md` & `stockmon/sheet_format.py`.

---

## Verification Audit & Fixes [COMPLETED]

A full audit verified implementation against requirements and resolved all items:

1. **BUG-1 (Fixed):** Added module-level `import io` to `stockmon/web/routes.py` for workbook import stream.
2. **BUG-2 (Fixed):** Replaced cartesian product in `holdings.py` sold query with a subquery aggregating buy lots per holding.
3. **BUG-3 (Fixed):** Implemented partial sell support using FIFO lot allocation; sold shares move to a new `sold` record, remaining shares stay in `open` holding with adjusted lots.
4. **BUG-4 (Fixed):** Corrected `colSpan` offset in Open Holdings and Sold tables `<tfoot>` so totals align across MADI, BAPA, and LOAN.
5. **BUG-5 (Fixed):** Updated `export_workbook` to expand individual buy lots for multi-buy holdings, preserving round-trip spreadsheet fidelity.
6. **BUG-6 (Fixed):** Added `.NS` ticker normalization via `stockmon.portfolio.normalize_symbol()` in add-holding and lookup routes.
7. **BUG-7 (Fixed):** Implemented formula vs manual override detection in `sheet_io.py`. Excel formula cells are set to `None` and computed dynamically per §1.4; manual overrides are preserved and flagged.
8. **GAP-1 (Fixed):** Added `export_csv()` and `/api/portfolio-tracker/export?format=csv` route and frontend CSV download button.
9. **GAP-2 (Fixed):** Added `Current Date` and `Annual %` columns to Open Holdings and Sold tables.
10. **GAP-3 (Fixed):** Implemented single-portfolio export scoping (`/api/portfolio-tracker/export?portfolio=LOAN&format=xlsx|csv`).
11. **GAP-4 (Fixed):** Added interactive ticker lookup button and manual scheme name confirmation checkbox to Add Holding modal.
12. **GAP-5 (Fixed):** Added live recalculated sale preview card (Exit Total, Charges, Net Realized, Partial Sell info) in Sell modal.
13. **GAP-6 (Fixed):** Made Summary Panel accessible from all portfolio tabs with a toggle button.
14. **Automated Tests:** Added `tests/test_portfolio_tracker.py` covering charge calculations, period math, partial sell lifecycle, and CSV export. All 4 tests passing.

