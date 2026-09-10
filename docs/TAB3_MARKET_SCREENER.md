# Tab 3: Market Screener & Predictive Analysis

The **Screener** tab scans the broad Indian market (>3,400 NSE stocks) using quantitative data from Prime Screener (`bigbreakingwire.in`). It combines static technical screening with an **11-Day Multi-Date Sequence Analyzer** to identify high-probability setups before they stage explosive moves.

---

## 1. On-Demand Fetching & Automatic Nonce Management

* **Manual Fetch Only**: The screener is never fetched automatically on app startup to conserve resources. Fetching occurs strictly on demand when you click **Fetch Data**.
* **Automatic Daily `X-WP-Nonce` Handling**:
  * The backend automatically extracts and caches the `X-WP-Nonce` token from `bigbreakingwire.in/screener/` for the current calendar date.
  * You do **not** need to manually copy or paste nonces. The token is valid for 12–24 hours and is refreshed automatically when a new day arrives or if an existing token expires mid-session (401/403).
  * An optional **Nonce Settings** panel is available if you ever wish to inspect the active token or provide a manual override.
* **Date Picker**: Choose between **Today / Latest** (default payload: `""`) or select any of the past 11 trading days (`"YYYY-MM-DD"`).
* **Local Persistence**: Every fetched dataset is saved into `data/screener_cache.db` with a high-performance hybrid schema (15 promoted hot columns for instant multi-day indexing + complete JSON payload for cold columns). Active nonces and metadata are maintained in `data/screener_cache.json`. Previously downloaded dates can be re-inspected instantly without network calls.

---

## 2. Interactive Screener Table

* **Sticky Frozen Columns**: The **Symbol** column (with clickable TradingView link and company name) and **Price** column stay frozen on horizontal scroll.
* **154-Column Selector**: Click **Columns** to toggle visibility across 19 categories (Price, Volume, Moving Averages, Supertrend, Technicals, Breakouts, Multi-Day Trajectory, etc.) with search and presets (*Default*, *Select All*, *Clear*).
* **Symbol Search**: Instant search filtering specifically on stock symbols.
* **Pagination**: 10, 20, 50, or 100 rows per page with page jumper.
* **Financial Styling**: Negative values in red (`#dc2626`), positive returns in green (`#16a34a`), signal badges (`Bullish`, `Bearish`, `Neutral`), and formatted Indian numbers.

---

## 3. Multi-Day Sequence Engine (Predictive Trajectory)

Single-day screening only reveals *what happened today*. The **Multi-Day Sequence Analyzer** tracks the chronological progression across up to 11 trading sessions ($T_{-10} \dots T_0$) to identify stocks **before** they stage explosive multi-day runs.

### One-Click History Sync
* Click **`[⚡ Sync History]`** in the screener header. The backend automatically downloads and writes missing historical dates directly into `data/screener_cache.db`. Consecutive queries execute in sub-milliseconds over SQLite indexed columns.

### Computed Trajectory Indicators:
1. **Accumulation Score (0–100)**: Quantifies institutional accumulation by scoring consecutive rising delivery volume, range position consistency, and flat base coiling.
2. **Signal Freshness (`supertrend_flip_days`, `ma20_cross_days`)**: Identifies whether a trend transition happened **today (Day 0)**, **yesterday (Day 1)**, or a week ago (stale).
3. **VCP Compression Ratio**: Compares recent 3-day volatility range against earlier sessions to detect tight coiling before an explosive expansion.
4. **Consecutive Rising Delivery & 3D Growth %**: Tracks multi-day smart money build-up.
5. **Consecutive Higher Lows**: Tracks unbroken daily staircases where buyers step in at higher prices each day.

---

## 4. 1-Click Curated Strategy Presets

The screener organizes presets into three tiers:

### Tier 1: 🔮 Multi-Day Predictive Trajectory (Upcoming 1–3 Day Movers)

1. **`📦 Silent Accumulation (Upcoming Pop)`**:
   * **Goal**: Detect stocks where institutions are quietly building positions across multiple sessions in a flat price base before lifting sell walls.
   * **Formula**: `Accumulation Score >= 65/100`, `Delivery % >= 35%`, `Multi-Day Window Return <= 5.0%`.
   * **Why it works**: Institutions cannot buy their entire position in an hour without driving up prices; they accumulate across days. Once finished, price expands rapidly.

2. **`⚡ Fresh Signal Ignition (Day 0–1)`**:
   * **Goal**: Catch breakouts and trend flips exactly on **Day 0 (today) or Day 1 (yesterday)**, eliminating stale/exhausted moves that happened a week ago.
   * **Formula**: `Supertrend Flip Days <= 1` OR `20 SMA Cross Days <= 1`, `RVOL >= 1.2x`, `Change % > 0%`.
   * **Why it works**: The first 1–2 days after a technical trend transition carry the highest statistical probability of continuation.

3. **`🎯 Multi-Day VCP Breakout` (Volatility Contraction)**:
   * **Goal**: Catch the release of a multi-day coiled spring.
   * **Formula**: `VCP Compression Ratio <= 0.65` OR `5-Session Range <= 6.0%`, `RVOL >= 1.4x`, `Change % >= +1.5%`, `Close Position in Range >= 75%`.
   * **Why it works**: Progressively shrinking price volatility over multiple days indicates complete supply exhaustion. When buyers step in, price pops with minimal overhead resistance.

4. **`📈 3+ Day Higher Lows Staircase`**:
   * **Goal**: Ride unbroken institutional staircase buying.
   * **Formula**: `Consecutive Higher Lows >= 3 sessions`, `Change % >= +0.5%`, `Close Position in Range >= 65%`.
   * **Why it works**: When buyers consistently bid up every dip across consecutive sessions, institutional accumulation is strongly in control.

---

### Tier 2: 🔥 Explosive 1–2 Day Setups (Top 15–30 High-Probability Candidates)

1. **`🚀 Institutional Blastoff` (1–2 Day Rocket)**:
   * **Goal**: Detect heavy institutional block accumulation before a multi-day continuation move.
   * **Formula**: `Highest Volume in 20 Sessions (is_highest_vol_20 == 1)`, `RVOL >= 2.0x`, `Close Position in Range >= 85%`, `Change % >= +2.5%`, `Supertrend == Bullish`.
   * **Typical Yield**: ~20–30 stocks out of 3,400+.

2. **`🎯 Coiled Spring (VCP Squeeze)` (Day 1 of the Move)**:
   * **Goal**: Catch the move right at origin (Day 1) before the general market notices.
   * **Formula**: `5-Session Range % <= 6.0%`, `RVOL >= 1.5x`, `Close in Range >= 80%`, `Change % >= +2.0%`.
   * **Typical Yield**: ~10–20 stocks out of 3,400+.

3. **`⭐ Blue Sky ATH Breakout` (Zero Overhead Supply)**:
   * **Goal**: Target stocks breaking within striking distance of all-time / 52-week highs with zero trapped overhead sellers.
   * **Formula**: `Distance from 52-Week High <= 2.0%`, `RVOL >= 2.0x`, `Change % >= +3.0%`, `Close in Range >= 85%`.
   * **Typical Yield**: ~15–25 stocks out of 3,400+.

4. **`🏆 8/8 Perfect Quantitative Consensus`**:
   * **Goal**: Maximum technical agreement across all internal quantitative indicators.
   * **Formula**: `Confirmation Count == '8/8'` (100% agreement across Supertrend, MAs, RSI, MACD, Volume, and Trend Strength), `RVOL >= 2.0x`, `Close in Range >= 80%`.
   * **Typical Yield**: ~25–35 stocks out of 3,400+.

---

### Tier 3: 📊 Classical Momentum & Positional Strategies

1. **`⚡ Quick Rocketing` (Backtested Swing Momentum)**:
   * **Goal**: Explosive 1–3 day breakout thrust with volume surge and active RSI momentum.
   * **Formula**: `Price >= ₹50`, `Change % >= +3.5%`, `RVOL >= 2.5x`, `Close in Range >= 85%`, `Supertrend == Bullish`, `RSI 14 between 60 and 78`.
   * **Backtest**: ~31 picks/day shortlist, 53.2% 2-day win rate (1.86 PF), 52.4% 3-day win rate (2.23 PF, +1.85% avg return).
2. **`🔥 Momentum Masters` (High-Consensus Swing Leaders)**:
   * **Goal**: Maximum technical alignment across indicator confirmations, confirmed strong trend, and volume.
   * **Formula**: `Price >= ₹50`, `Confirmations >= 7/8`, `Trend Direction == Bullish`, `Trend Strength == Strong`, `RVOL >= 2.0x`, `Close in Range >= 80%`, `Supertrend == Bullish`, `Change % >= +2.0%`.
   * **Backtest**: ~51 picks/day shortlist, 53.7% 3-day win rate (2.05 PF, +1.64% avg return).
3. **`🔬 Confirmed Accumulation Swing` (Disciplined Setup + Delivery)**:
   * **Goal**: Disciplined swing trading combining technical confirmations, strong setup quality, and heavy institutional delivery.
   * **Formula**: `Price >= ₹50`, `Confirmations >= 7/8`, `Setup Strength == Strong`, `Delivery % >= 45%`, `Supertrend == Bullish`, `RVOL >= 1.5x`, `Change % >= +1.5%`, `Close in Range >= 75%`.
   * **Backtest**: ~55 picks/day shortlist, 53.0% 1-day win rate (1.80 PF), 52.9% 3-day win rate (1.85 PF, +1.19% avg return).
4. **`⚡ BTST Surge`**: Overnight gap-up and next-morning continuation (`Close in Range >= 80%`, `Change % >= +1.5%`, `RVOL >= 1.2x`, `Delivery % >= 30%`).
5. **`🚀 Swing Momentum Breakout`**: Multi-week trend continuation (`Price > SMA 20 & 50`, `Supertrend == Bullish`, `RSI >= 55`, `RVOL >= 1.0x`).
6. **`⭐ 52W High Breakout`**: Within 5% of 52-week high with volume confirmation (`dist_52w_high <= 5%`, `RVOL >= 1.2x`).
7. **`📉 Dip Buyer`**: Low-risk entries in macro bull trends (`Price > SMA 200`, `Price < SMA 20`, `RSI between 40 and 52`).
8. **`💎 Long-Term Compounders`**: Multi-quarter relative strength (`Price > SMA 200`, `SMA 50 > SMA 200`, `1Y Return >= 15%`, `dist_52w_high <= 20%`).
9. **`📦 High Delivery Accumulation`**: Smart money taking physical delivery (`Delivery % >= 60%`, `RVOL >= 1.0x`, `Change % >= 0%`).

---

## 5. Custom Multi-Rule Filter Builder

* Click **Custom Rule Builder** to create your own custom scan conditions.
* **186 Technical & Fundamental Fields**: Complete parity with the 154-column table, including Moving Averages, RSI, MACD, ADX, ATR, Bollinger Bands, Delivery, Volatility, Supertrend, Setup indicators, Confirmations (with numerator fraction parsing like `>= 7`), and Multi-Day Trajectory indicators.
* **Column-to-Column Comparisons**: Compare any indicator directly against another column (e.g. `Price > SMA 20`, `SMA 50 > SMA 200`).
* **Flexible Operators**: `>`, `>=`, `<`, `<=`, `==`, `!=`, `between (Range)`, and `contains`.
* **Match Logic**: Toggle between `All Rules (AND)` and `Any Rule (OR)`.
* **Save Custom Presets**: Click **Save as Preset** to store your rules in browser local storage with a custom name for instant access anytime.
* **Strategy Explanation Modal**: Click the **(i)** icon on any preset chip to view its timeframe, in-depth rationale, and exact checklist.

