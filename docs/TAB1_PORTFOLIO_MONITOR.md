# Tab 1: Portfolio Monitor (Tracker)

The **Tracker** tab is the primary dashboard for monitoring multiple stock portfolios (default: **BAPA** and **MADI**) against standard Exponential Moving Averages (EMAs) across daily and weekly timeframes.

---

## 1. Core Architecture & Philosophy

* **Live Monitoring**: Shows live market prices and evaluates whether current prices are holding above or falling below critical trend baselines.
* **Avg Price (₹)**: Directly linked to **Portfolio Tracker**; displays the weighted average purchase price for the holding across open lots (combining Personal and Loan entries). Displays `—` for purely manual tickers.
* **Dual Timeframe (Daily & Weekly)**: For every stock, the system tracks 5 key EMA periods on both Daily and Weekly intervals (10 EMAs total):
  * **9 EMA**: Short-term momentum
  * **21 EMA**: Short-term trend baseline
  * **50 EMA**: Institutional support level
  * **100 EMA**: Intermediate trend support
  * **200 EMA**: Major bull/bear boundary
* **Signal Column**:
  * **`SELL`** (red badge): Triggered whenever the current price is **below the daily 200 EMA**.
  * **`HOLD`** (green badge): Current price is holding above the daily 200 EMA (or 200 EMA data is not yet available due to recent listing).

---

## 2. Display & Priority Sorting Logic

### Priority Sorting Rules
Stocks in each portfolio table are prioritized and sorted based on the highest breached daily EMA:
1. **Priority 0 (Critical Alert)**: Price below daily **200 EMA**
2. **Priority 1**: Price below daily **100 EMA**
3. **Priority 2**: Price below daily **50 EMA**
4. **Priority 3**: Price below daily **21 EMA**
5. **Priority 4**: Price below daily **9 EMA**
6. **Priority 5 (Healthy Trend)**: Price holding above all daily EMAs

*Within the same priority tier, stocks are sorted alphabetically by ticker symbol.*

### Stacked Cell Display (`D:` and `W:`)
Each EMA column renders a stacked cell:
* **D:** Daily EMA value (top line)
* **W:** Weekly EMA value (bottom line)

**Rendering Rules**:
* **Price BELOW the EMA**: The EMA value is displayed in **bold red** (e.g. `D: 245.30`).
* **Price ABOVE the EMA**: The value remains **blank** (keeping the table clean so breached levels stand out immediately).
* **Data Unavailable (N/A)**: If a newly listed stock lacks sufficient history for long-term EMAs (such as 200-week), that specific line renders `N/A` in muted grey without breaking other columns.

---

## 3. Dual Exchange Auto-Switching (NSE ↔ BSE)

* NSE symbols typically end in `.NS` (e.g., `RELIANCE.NS`), while BSE symbols end in `.BO` (e.g., `500325.BO`).
* If a ticker on one exchange has thin historical data (< 400 daily bars), the data fetcher automatically queries the alternate exchange and selects the one with richer history to ensure accurate EMA calculations.

---

## 4. Ticker Management & Portfolio Tracker Linking

### Ticker Sourcing from Portfolio Tracker
* **MADI Table**: Automatically populated with open holdings from Portfolio Tracker's **MADI** table PLUS Portfolio Tracker's **LOAN** table where `person = 'MADI'`.
* **BAPA Table**: Automatically populated with open holdings from Portfolio Tracker's **BAPA** table PLUS Portfolio Tracker's **LOAN** table where `person = 'BAPA'`.
* **Deduplication & Weighted Avg Price**: If a ticker exists in both Personal and Loan tables for that person, it is automatically merged into a single row with combined weighted average purchase price.
* **Sold Lifecycle**: When an open holding is marked as sold in Portfolio Tracker (or deleted), it is automatically removed from the Tracker tab once the position reaches zero. Partially sold holdings remain in the Tracker tab with updated lot quantities and Avg Price.
* **Protected Deletion**: Sourced tickers cannot be deleted via the Tracker tab's trash button (trash button is disabled with an explanatory tooltip).

### Adding a Manual Ticker
1. Use the **Add ticker** form located below the portfolio tables.
2. Select the target portfolio (**BAPA** or **MADI**).
3. Enter the ticker symbol:
   * Bare symbol defaults to NSE (e.g., `TCS` → `TCS.NS`).
   * Explicit suffix supported: `500325.BO` or `INFY.NS`.
4. Click **Add & fetch**. The system immediately validates the symbol via Yahoo Finance, computes its full EMA set, persists it to `stockmon.db` (in `portfolio_ticker`), and updates the UI in real time via Server-Sent Events (SSE). Purely manual tickers retain an active trash button for removal.

### Shared Single Price Fetch (LTP)
* Live prices (LTP) fetched for the Tracker tab (during scheduled or manual runs) are automatically saved to `quote_cache` in `stockmon.db`.
* The Portfolio Tracker tab (`/api/portfolio-tracker/<portfolio>`) reads this exact same cached quote for Loan, Madi, and Bapa tables, eliminating duplicate external network calls.

---

## 5. Scheduled Automation & Desktop Reminders

* **Scheduled Refresh Engine**: Configured via Windows Task Scheduler to run twice daily on **weekdays (Monday to Friday)**, typically at **09:30** and **11:30** IST.
* **Top-Level Reminder Window**: When a scheduled run finishes in the background, `show_window.py` pops up a clean desktop window on top of all active workspaces to notify you of the fresh price calculation.
* **Manual Refresh**: Click **Refresh now** in the navbar to recompute all portfolio EMAs on demand.
