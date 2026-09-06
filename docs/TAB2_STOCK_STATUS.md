# Tab 2: Stock Status & Scenario Analysis

The **Status** tab is a dedicated research and valuation journal designed to track investment theses, scenario targets (Base, Bull, Bear), target CAGRs, and entry zones across time.

---

## 1. Core Purpose & Philosophy

Investors frequently analyze a stock at a specific price point, project targets, and set a "Best Entry" price. Over months, price fluctuates and new quarters unfold. The **Stock Status** system solves three key problems:
1. **Scenario Target Tracking**: Quantifies your upside and downside expectations under Base, Bull, and Bear cases.
2. **Best Entry Discipline**: Tracks how far the current market price is from your ideal entry level.
3. **Multi-History Versioning**: Preserves historical analyses so you can look back at what your thesis was on Date A versus Date B.

---

## 2. Key Features & Workflow

### Adding a Stock Analysis
1. Click **+ Add Stock** in the Status tab.
2. Enter the ticker symbol (e.g. `INFY` or `TATAMOTORS.NS`) and click **Fetch**.
   * Fetches the official company name and current market price from Yahoo Finance as your baseline **Price of Analysis**.
3. Choose a **Status** stance:
   * `Buy` — High conviction (green badge)
   * `Avoid` — Broken thesis or high risk (red badge)
   * `Hold` — Fairly valued, stay invested (yellow badge)
   * `Acc on dip` — Accumulate on pullbacks (light green badge)
4. Enter an optional **Best Entry** price.
5. Enter **Target Price** and expected **Target CAGR (%)** for all three scenarios:
   * **Base Scenario**: Most probable business outcome
   * **Bull Scenario**: Favorable tailwinds, accelerated earnings
   * **Bear Scenario**: Margin compression, valuation de-rating
6. Enter optional **Remarks** (key catalysts, thesis summary, stoploss level).
7. Click **Submit** to save the entry to `data/stockmon.db` (in the `stock_status` table with per-row CRUD transactions).

---

## 3. Real-Time Price Tracking & Comparisons

* **Live Current Price**: Displays the latest live market price alongside a color-coded percentage badge (`+X.X%` / `-X.X%`) comparing the current live price against the baseline analysis price.
* **Best Entry Comparison**: The Best Entry column shows your target purchase price alongside a color-coded distance badge (`+X.X%` / `-X.X%` from Current Price).
* **Quote Caching & Fallback**: Quotes are cached locally in `data/stockmon.db` (in the `quote_cache` table). If a live network lookup times out, the last known cached price and timestamp render seamlessly.
* **Refresh Prices Button**: Dedicated button in the Status tab to update live market quotes and timestamps for all analyzed stocks without recomputing portfolio EMAs.

---

## 4. Multi-History Analysis & Date Selector

* **Evolution Over Time**: An investor might analyze a stock in March at ₹400 and re-evaluate it in September at ₹650 after strong quarterly results.
* **Creating a New History Record**: Click the **Edit** (pencil) icon on any row and choose **New (History)**. This creates a fresh analysis record dated today, preserving the previous analysis.
* **Historical Analysis Date Dropdown**: When a ticker has multiple analysis entries, the **Date of Analysis** column renders a dropdown selector. Selecting a date dynamically updates:
  * Baseline Price of Analysis
  * Best Entry price
  * Status stance
  * Scenario targets (Base, Bull, Bear) and CAGRs
  * Remarks and thesis notes
  * *The **Current Price** remains live, allowing immediate comparison of present reality against any past thesis.*

---

## 5. Remarks & Formatting

* Renders exact whitespace, line breaks, bullet points, and formatting matching the input field.
* Collapsed by default to maintain compact row height. Click **Show more** to expand and **Show less** to collapse.
