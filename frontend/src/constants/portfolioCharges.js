// Statutory charge rates for the Portfolio Tracker sell preview.
// Must stay in sync with BUY_CHARGE_TOTAL_RATE / SELL_CHARGE_TOTAL_RATE
// in stockmon/portfolio_tracker.py, which remains the authority (§1.4).

const NSE_RATE = 0.0000345;
const GST_ON_NSE = 0.18 * NSE_RATE;

export const BUY_CHARGE_RATE =
  NSE_RATE + 0.000001 + 0.00015 + 0.001 + GST_ON_NSE;
export const SELL_CHARGE_RATE = 0.0010355 + GST_ON_NSE;
