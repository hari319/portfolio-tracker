# Google Sheet / Excel Workbook Format Specification (`Invest.xlsx`)

This document records the exact structure, layout, headers, date conventions, and formulas of the user's `Invest.xlsx` workbook. Both the importer (`stockmon/sheet_io.py`) and exporter rely on this specification to ensure 100% round-trip fidelity.

---

## 1. Sheet Overview

| Sheet Name in Workbook | Normalized Portfolio Key | Notes |
| :--- | :--- | :--- |
| `Stock Madi` | `MADI` | Personal portfolio. Holdings, Sold, and Dividends are stacked vertically. |
| `Stock Bapa` | `BAPA` | Personal portfolio. Holdings and Sold are side-by-side (Cols 1–18 and 20–37). Dividends stacked below Holdings. |
| `Loan ` *(trailing space)* | `LOAN` | Loan-funded portfolio. Holdings & Sold side-by-side. Dividends below. Summary Panel at Cols 39–40 (AM–AN). |

---

## 2. Column Definitions (Holdings & Sold)

Both open Holdings and Sold tables share the same 18 conceptual columns:

| Col # | Header Name (as in Excel) | Type | Formula / Origin |
| :---: | :--- | :--- | :--- |
| **1** | `Scheme` | Text | Stock ticker / company name (e.g. `TATAGOLD`, `ZENTEC`, `HDBFS`) |
| **2** | `Invest Date` | String/Date | User input: Format `DD.MM.YY` (e.g. `18.09.25`) |
| **3** | `Current Date` | String/Date | Today's date for open holdings; Sell Date for sold rows (`DD.MM.YY`) |
| **4** | `Y` (Years) | Number | `=QUOTIENT(M, 12)` |
| **5** | `M` (Months) | Number | `=DATEDIF(DATE(20yy, mm, dd), DATE(20yy, mm, dd), "M")` |
| **6** | `Q` (Quantity) | Number | User input quantity (shares) |
| **7** | `Avg` | Number | User input buy price per share |
| **8** | `LTP` | Number | Live quote for open holdings; realized exit price for sold |
| **9** | `Invested ` | Number | `=Q * Avg` (`=SUM(F3*G3)`) |
| **10** | `Buy Charge` | Number | `=(0.0000345 + 0.000001 + 0.00015 + 0.001) * Invested + 0.18 * (0.0000345 * Invested)` *(or manual override)* |
| **11** | `Sell Charge` | Number | `=0.0010355 * Current_Total + 0.18 * (0.0000345 * Current_Total)` |
| **12** | `Current Total` | Number | `=Q * LTP` (`=SUM(F3*H3)`) |
| **13** | `Earned ` | Number | `=IF((Current_Total - Invested) > 0, Current_Total - Buy_Charge - Sell_Charge - Invested, 0)` |
| **14** | `Loss` | Number | `=IF((Invested - Current_Total) < 0, 0, -(Invested + Buy_Charge + Sell_Charge - Current_Total))` |
| **15** | `Annual Return` | % / Number | Annualized return % |
| **16** | `Total Return` | % / Number | `=((Current_Total / Invested) - 1) * 100` |
| **17** | `App` | Text | Platform / Person. In `Loan `, contains `Kite Madi` or `Kite Bapa` (maps to `Person = MADI` or `BAPA`) |
| **18** | `Remarks` / `Reamrks` | Text | User notes (e.g. `PEAD`, `ETF`, `Swing Self`, `Devi Money`) |

---

## 3. Sheet Layouts

> The importer locates the Holdings, Sold, Dividend and Summary blocks by their
> marker labels (`Scheme`, `Sold`, `Dividend`, and the Summary labels in §4), because
> an exported workbook shifts every section as the data grows. The row numbers below
> describe the original `Invest.xlsx` and are used only as a fallback when a marker
> cannot be found. See `FALLBACK_LAYOUT` in `stockmon/sheet_format.py`.

### 3.1 `Stock Madi` (Vertical Stacking)
- **Row 1**: Title / metadata (`996` in A1)
- **Row 2**: Header row (Cols 1–18)
- **Rows 3–73**: Open Holdings
- **Row 74**: Holdings Total row (`Total` in Col 1, sums in Invested, Current Total, Earned, Loss)
- **Row 77**: Sold Section Header (`Sold` in Col 1)
- **Rows 78–133**: Sold Transactions (Cols 1–18)
- **Row 134**: Sold Total row
- **Row 135**: Dividend Section Header (`Dividend` in Col 1)
- **Row 136**: Dividend Header (`Stock`, `Divi`, `Term` in Cols 1–3)
- **Rows 137–177**: Dividend entries
- **Row 178**: Dividend Total row (`Total`, sum)

### 3.2 `Stock Bapa` (Side-by-Side)
- **Row 1**: Section label `SOLD` above Col 20
- **Row 2**: Headers:
  - Cols 1–18: Open Holdings headers
  - Cols 20–37: Sold headers
- **Rows 3–99**: Open Holdings (Cols 1–18)
- **Row 100**: Open Holdings Total row
- **Rows 3–184**: Sold Transactions (Cols 20–37)
- **Row 185**: Sold Total row
- **Row 182**: Dividend Section Header (`Dividend` in Col 1)
- **Row 183**: Dividend Headers (`Stock`, `Divi`, `Term` in Cols 1–3)
- **Rows 197–334**: Dividend entries
- **Row 335**: Dividend Total row

### 3.3 `Loan ` (Side-by-Side + Summary Panel)
- **Row 1**: `Stock Invest Details` (Col 1), `Stock Sold` (Col 20)
- **Row 2**: Headers:
  - Cols 1–18: Open Holdings
  - Cols 20–37: Sold
- **Rows 3–94**: Open Holdings
- **Row 95**: Holdings Total row
- **Rows 3–184**: Sold Transactions
- **Row 185**: Sold Total row
- **Row 176**: Dividend Section Header (`Dividend` in Col 1)
- **Row 177**: Dividend Headers (`Stock`, `Divi`, `Term`)
- **Rows 298–300**: Dividend entries
- **Row 301**: Dividend Total row
- **Cols 39–40 (Rows 76–87)**: Summary Panel

---

## 4. Summary Panel Mapping (`Loan ` Sheet, Cols 39–40)

| Row | Label in Sheet | Key in `summary_value` DB | Default Value | Type | Formula / Source |
| :---: | :--- | :--- | :--- | :--- | :--- |
| **76** | `Current Stock & ETF Invest` | `current_stock_etf_invest` | 5,213,974.77 | Fixed | User-entered (holdings total) |
| **77** | `Current MF Invest` | `current_mf_invest` | 1,300,000.00 | Fixed | User-entered |
| **78** | `Current MF Redeem` | `current_mf_redeem` | 450,000.00 | Fixed | User-entered |
| **79** | `Total ` | `_total_invest` | 6,963,974.77 | Computed | Row 76 + Row 77 + Row 78 |
| **82** | `Loan Amount` | `loan_amount` | 6,530,152.87 | Fixed | User-entered |
| **83** | `Reamining Invest From Loan` | `_remaining_invest_loan` | -433,821.90 | Computed | `Loan Amount - Total` (negative once deployment exceeds the loan) |
| **84** | `Stock Proift ` | `_stock_profit` | 586,778.17 | Computed | `Loan Earned - Loan Loss` |
| **85** | `Dividend` | `_total_dividend` | 1,093.00 | Computed | Sum of all loan dividends |
| **86** | `Current MF Reddem + Profit` | `current_mf_redeem_profit` | 474,623.00 | Fixed | User-entered |
| **87** | `Current Remaining` | `_current_remaining` | 628,672.27 | Computed | Row 83 + Row 84 + Row 85 + Row 86 |
