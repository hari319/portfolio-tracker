# Feature Request: Portfolio Tracker (new tab)

> **Terminology:** the existing Tab 1 is called **Tracker / Portfolio Monitor** (EMA dashboard for portfolios `BAPA` and `MADI`). The feature below is a **new, separate tab** named **Portfolio Tracker** (holdings, cost, P&L). Wherever this document says "Tracker tab", it means the **existing** Tab 1.

---

## 1. Scope

Add a new tab, **Portfolio Tracker**, tracking actual holdings (buy price, quantity, charges, profit/loss) for three portfolios:

| Portfolio | Notes |
| --- | --- |
| `BAPA` | Personal portfolio |
| `MADI` | Personal portfolio |
| `LOAN` | Loan-funded portfolio. Has one extra field: **Person** (`MADI` or `BAPA`) |

Each portfolio is rendered **separately** (its own table/section). A table is the default idea — propose a better layout if one exists.

### 1.1 Initial data source (Google Sheet)

All portfolio data **already exists in a Google Sheets workbook**, which the user will provide to seed the feature.

* The workbook has **three sheets**, one per portfolio: **Madi**, **Bapa**, **Loan**.
* The **Loan** sheet also contains the values for the **Summary panel** (section 8).
* This is a **one-time import** to populate the initial data; after that the app is the source of truth.

**Open question:** import mechanism — export the sheets to CSV/XLSX and parse them once, or read the workbook through the Google Sheets API.

---

## 2. Holdings table (per portfolio)

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

**Open question:** the exact Buy/Sell Charge formulas (brokerage, STT, stamp duty, exchange fees, GST) must be confirmed before implementation.

### 2.2 Row grouping (multiple buys of the same stock)

* A stock may be bought **once**, or **several times at different prices**.
* **Bought once** → render a single plain row.
* **Bought multiple times** → render **one aggregated parent row** (total quantity, total invested, weighted average price) with an **expand/collapse (+/−) control** that reveals the individual buy transactions as child rows.

### 2.3 Row actions

* **Delete row** — a row added by mistake, or a holding that is no longer needed, must be deletable **without** going through the sell flow (it must not appear in the Sold table).

---

## 3. Adding a holding

The user provides only:

1. **Ticker** → the system fetches the stock name (Scheme) automatically.
2. **Current Date** (buy date)
3. **Q** (quantity)
4. **Avg** (average buy price)
5. **Remarks**

Everything else is calculated.

**Edge case:** if the stock name cannot be fetched for a ticker, accept a **manually typed name**, but require the user to **confirm** it before saving.

---

## 4. Selling a holding

* To sell, the user **edits LTP and Current Date**; every other value recalculates automatically.
* On sell, the holding **moves out of the Holdings table into a separate "Sold" table**.
* The Sold table uses the **same column format** and is shown **per portfolio** (a portfolio's Sold table lists only that portfolio's sold stocks).

---

## 5. Totals row (both Holdings and Sold tables)

Each table ends with a totals row showing:

* Total Invested Amount (all rows)
* Total Current Total (all rows)
* Total Earned
* Total Loss
* Net Profit = Total Current Total − Total Invested Amount

---

## 6. Per-stock notes (bought reason / sold reason / lessons)

Each stock row carries three free-text fields:

* **Bought Reason**
* **Sold Reason**
* **Mistake / Learned**

They are **hidden by default** and opened on demand (e.g. a row button that opens a panel or modal).

**Follow-up idea:** a consolidated view listing **all "Mistake / Learned" entries in one place**, so past mistakes can be reviewed and avoided.

---

## 7. Dividends (per portfolio)

Each portfolio keeps its own dividend list, shown separately:

| Column | Type |
| --- | --- |
| Symbol | text |
| Value | number |
| Date | date |

---

## 8. Summary panel (below the portfolios)

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
| Remaining Invest From Loan | −₹433,821.90 | `Total − Loan Amount` |
| Stock Profit | 586,778.17 | `LOAN portfolio Earned − LOAN portfolio Loss` |
| Dividend | 1,093.00 | Sum of all dividend values |
| Current MF Redeem + Profit | ₹474,623 | Fixed |
| **Current Remaining** | ₹628,672.53 | Sum of: Remaining Invest From Loan + Stock Profit + Dividend + Current MF Redeem + Profit |

---

## 9. Integration with the existing Tracker tab (Tab 1)

Today, rows in the existing Tracker tab are added **manually**. After this feature ships:

* The **MADI** Tracker table is populated automatically from the **MADI** Portfolio Tracker holdings, **plus** the `LOAN` portfolio rows where `Person = MADI` (all other required values are fetched for those tickers).
* The same applies to **BAPA** (BAPA holdings + `LOAN` rows where `Person = BAPA`).
* A ticker is **removed from the Tracker tab only when the stock is sold** in the Portfolio Tracker.

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
2. Exact Buy Charge / Sell Charge formulas.
3. Annual Return formula — simple annualised return, or CAGR?
4. Storage location for holdings — new JSON files under `data/` (consistent with the existing store) or elsewhere.
5. Risk-management formula and thresholds for Phase 3.
6. Google Sheet import — file/CSV upload vs Sheets API, and confirmation of the exact column headers used in the Madi / Bapa / Loan sheets.
