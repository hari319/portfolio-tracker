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
- **Export (`/api/portfolio-tracker/export`)**:
  - Re-generates a byte-compatible XLSX workbook with tabs `Stock Madi`, `Stock Bapa`, and `Loan `.
  - Recreates exact headers, stacked vs side-by-side layouts, formatted numbers, totals rows, and the Loan summary panel.
  - Guarantees complete round-trip fidelity.
