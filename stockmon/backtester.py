"""Backtesting engine for screener strategies.

Evaluates strategy rules against historical screener snapshots and
computes forward-return performance metrics.

Rules use the same format as the frontend ``STRATEGY_PRESETS``:
``{ field, op, value, compareField, valueMin, valueMax }``.
"""

from __future__ import annotations

import logging
from typing import Any

from stockmon.db.repositories import screener as screener_repo

logger = logging.getLogger(__name__)

# Fields that come from multi-day trajectory analysis (not in raw payload).
_MULTI_DAY_FIELDS = frozenset({
    "accumulation_score", "consecutive_rising_delivery", "consecutive_higher_lows",
    "predictive_setups", "delivery_growth_3d_pct", "supertrend_flip_days",
    "ma20_cross_days", "vcp_compression_ratio", "window_price_change_pct",
})


def list_backtestable_fields() -> list[str]:
    """Return the list of fields available for backtesting from the screener data."""
    return [
        # Hot columns
        "close", "open", "high", "low", "prev_close", "pct_change", "volume",
        "delivery_qty", "delivery_percent", "supertrend_dir", "sma_20",
        "close_near_high_pct", "volume_ratio_20", "range_pct_5", "series",
        # Key payload fields
        "confirmation_count", "setup_strength", "setup", "bearish_setup",
        "trend_direction", "trend_strength", "signal",
        "rsi_14", "rsi_7", "macd", "macd_signal", "macd_histogram",
        "adx_14", "adx_plus_di", "adx_minus_di",
        "sma_5", "sma_10", "sma_50", "sma_100", "sma_200",
        "ema_5", "ema_9", "ema_10", "ema_20", "ema_50", "ema_100", "ema_200",
        "atr_14", "atr_percent", "stochastic", "stochastic_d",
        "bb_upper", "bb_lower", "bb_bandwidth", "bb_pct_b",
        "momentum", "roc", "rsi_zone", "rsi_change", "rsi_trend",
        "dist_52w_high", "dist_52w_low", "pos_52w", "new_52w_high", "new_52w_low",
        "perf_1d", "perf_1w", "perf_1m", "perf_3m", "perf_6m", "perf_1y",
        "delivery_rising_3", "delivery_rising_5",
        "volume_rising_3", "volume_rising_5", "volume_change_pct",
        "is_highest_vol_20", "is_highest_vol_50", "is_highest_vol_252",
        "breakout_type", "breakout_price", "breakout_pct", "breakout_strength",
        "daily_range_pct", "daily_volatility", "annualised_volatility",
        "pe_ratio", "adjusted_pe",
        # Multi-day trajectory (requires enriched data)
        "accumulation_score", "consecutive_rising_delivery", "consecutive_higher_lows",
        "predictive_setups",
    ]


# ---------------------------------------------------------------------------
# Rule evaluation  (mirrors frontend evaluateItemMatchesRule)
# ---------------------------------------------------------------------------

def _parse_fraction_numerator(val: str) -> float | None:
    """Parse the numerator from a fraction string like '6/8' → 6.0."""
    if isinstance(val, str) and "/" in val:
        parts = val.split("/")
        if len(parts) == 2:
            try:
                return float(parts[0].strip())
            except ValueError:
                pass
    return None


def _to_number(val: Any) -> float | None:
    """Try to convert a value to float, including fraction strings."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        # Try fraction first (e.g. "6/8" → 6.0)
        frac = _parse_fraction_numerator(val)
        if frac is not None:
            return frac
        try:
            return float(val)
        except ValueError:
            return None
    return None


def evaluate_rule(item: dict, rule: dict) -> bool:
    """Evaluate a single filter rule against a stock item.

    Accepts the same rule format as the frontend:
    ``{ field, op, value, compareField, valueMin, valueMax }``.

    For ``confirmation_count`` and other fraction-string fields, numeric
    comparisons are performed on the **numerator** (e.g. ``"7/8"`` → ``7``).
    """
    if not item or not rule:
        return True
    field = rule.get("field")
    op = rule.get("op")
    if not field:
        return True

    item_val = item.get(field)
    if item_val is None:
        return False

    # --- Array contains (e.g. predictive_setups) ---
    if isinstance(item_val, list):
        if op in ("contains", "=="):
            target = str(rule.get("value", "")).lower()
            return any(
                target == str(el).lower() or target in str(el).lower()
                for el in item_val
            )
        return False

    # --- Column-to-column comparison ---
    compare_field = rule.get("compareField")
    if compare_field:
        target_val = item.get(compare_field)
        if target_val is None:
            return False
        num_a = _to_number(item_val)
        num_b = _to_number(target_val)
        if num_a is not None and num_b is not None:
            if op == ">": return num_a > num_b
            if op == ">=": return num_a >= num_b
            if op == "<": return num_a < num_b
            if op == "<=": return num_a <= num_b
            if op == "==": return num_a == num_b
            if op == "!=": return num_a != num_b
        return False

    # --- Range (between) ---
    if op == "between":
        num = _to_number(item_val)
        if num is None:
            return False
        val_min = _to_number(rule.get("valueMin"))
        val_max = _to_number(rule.get("valueMax"))
        if val_min is not None and num < val_min:
            return False
        if val_max is not None and num > val_max:
            return False
        return True

    # --- Numeric comparison ---
    rule_val = rule.get("value")
    num_item = _to_number(item_val)
    num_rule = _to_number(rule_val)

    if num_item is not None and num_rule is not None and rule_val is not None:
        if op == ">": return num_item > num_rule
        if op == ">=": return num_item >= num_rule
        if op == "<": return num_item < num_rule
        if op == "<=": return num_item <= num_rule
        if op == "==": return num_item == num_rule
        if op == "!=": return num_item != num_rule

    # --- Fallback: string comparison ---
    str_a = str(item_val).lower()
    str_b = str(rule_val or "").lower()
    if op == "==": return str_a == str_b
    if op == "!=": return str_a != str_b
    if op == "contains": return str_b in str_a

    return True


# In-memory caches to make multiple backtests instantaneous
_DATE_ITEMS_CACHE: dict[str, list[dict]] = {}
_HOT_PRICE_CACHE: dict[str, dict[str, float]] = {}


def clear_backtest_cache() -> None:
    """Clear memory caches used during backtesting."""
    _DATE_ITEMS_CACHE.clear()
    _HOT_PRICE_CACHE.clear()


# ---------------------------------------------------------------------------
# Backtesting engine
# ---------------------------------------------------------------------------

def backtest_strategy(
    rules: list[dict],
    hold_days: list[int] | None = None,
    min_dates: int = 5,
) -> dict:
    """Run a historical backtest for a set of strategy rules.

    For each signal date T₀ (where forward data is available), filters
    stocks using *rules*, then measures forward returns at T₀+N for each
    hold period N.

    Returns a structured results dict with hit rates, avg returns, profit
    factors, and a daily breakdown.
    """
    if hold_days is None:
        hold_days = [1, 2, 3, 5]

    dates_meta = screener_repo.list_saved_dates()
    dates_meta.sort(key=lambda x: x["date"])
    available_dates = [d["date"] for d in dates_meta]
    max_hold = max(hold_days) if hold_days else 0

    if len(available_dates) < min_dates + max_hold:
        return {
            "ok": False,
            "error": (
                f"Need at least {min_dates + max_hold} dates for backtesting "
                f"(have {len(available_dates)}). Sync more historical data first."
            ),
        }

    # Signal dates: all dates except the last max_hold (need forward data)
    signal_dates = available_dates[:-max_hold] if max_hold > 0 else available_dates

    # Check if rules reference multi-day trajectory fields
    needs_multi_day = any(r.get("field") in _MULTI_DAY_FIELDS for r in rules)

    # Accumulators
    hold_metrics: dict[str, dict[str, list[float]]] = {
        f"{d}d": {"gains": [], "losses": []} for d in hold_days
    }
    daily_breakdown: list[dict] = []
    total_picks = 0
    total_signal_dates = 0

    for i, t0_date in enumerate(signal_dates):
        if t0_date not in _DATE_ITEMS_CACHE:
            data = screener_repo.load_screener_for_date(t0_date)
            _DATE_ITEMS_CACHE[t0_date] = data.get("items", []) if data else []
        items = _DATE_ITEMS_CACHE[t0_date]
        if not items:
            continue

        # Warn once if multi-day fields missing
        if needs_multi_day and items:
            has_multi = any(f in items[0] for f in _MULTI_DAY_FIELDS)
            if not has_multi:
                return {
                    "ok": False,
                    "error": (
                        "Rules reference multi-day trajectory fields "
                        f"({', '.join(r['field'] for r in rules if r.get('field') in _MULTI_DAY_FIELDS)}), "
                        "but they are not present in the historical screener snapshots. "
                        "Multi-day fields are computed at runtime and not stored in raw data."
                    ),
                }

        # Apply rules
        picked: list[tuple[str, float]] = []
        for item in items:
            if all(evaluate_rule(item, rule) for rule in rules):
                sym = item.get("symbol")
                close = item.get("close")
                if sym and close and close > 0:
                    picked.append((sym, close))

        if not picked:
            day_stats = {"date": t0_date, "picks": 0}
            daily_breakdown.append(day_stats)
            continue

        day_picks = len(picked)
        total_picks += day_picks
        total_signal_dates += 1
        day_stats: dict[str, Any] = {"date": t0_date, "picks": day_picks}

        # Look up forward returns
        for d in hold_days:
            target_idx = i + d
            if target_idx >= len(available_dates):
                continue
            target_date = available_dates[target_idx]

            # Cache forward prices in global cache
            if target_date not in _HOT_PRICE_CACHE:
                rows = screener_repo.load_hot_columns_for_dates([target_date])
                _HOT_PRICE_CACHE[target_date] = {
                    row["symbol"]: row.get("close")
                    for row in rows
                    if row.get("trade_date") == target_date and row.get("close")
                }

            price_map = _HOT_PRICE_CACHE[target_date]
            day_returns: list[float] = []

            for sym, t0_close in picked:
                tn_close = price_map.get(sym)
                if tn_close is not None and tn_close > 0:
                    ret = (tn_close - t0_close) / t0_close * 100.0
                    day_returns.append(ret)
                    if ret > 0:
                        hold_metrics[f"{d}d"]["gains"].append(ret)
                    else:
                        hold_metrics[f"{d}d"]["losses"].append(ret)

            if day_returns:
                day_stats[f"avg_{d}d_return"] = round(
                    sum(day_returns) / len(day_returns), 3
                )

        daily_breakdown.append(day_stats)

    # Compute aggregate metrics per hold period
    hold_periods: dict[str, dict] = {}
    for d in hold_days:
        key = f"{d}d"
        gains = hold_metrics[key]["gains"]
        losses = hold_metrics[key]["losses"]
        total_trades = len(gains) + len(losses)
        if total_trades == 0:
            continue

        all_rets = gains + losses
        sorted_rets = sorted(all_rets)
        hit_rate = (len(gains) / total_trades) * 100.0
        avg_return = sum(all_rets) / total_trades
        mid = total_trades // 2
        median_return = (
            sorted_rets[mid]
            if total_trades % 2 == 1
            else (sorted_rets[mid - 1] + sorted_rets[mid]) / 2
        )
        max_gain = max(gains) if gains else 0.0
        max_loss = min(losses) if losses else 0.0
        sum_gains = sum(gains)
        sum_losses = abs(sum(losses))
        profit_factor = (
            round(sum_gains / sum_losses, 2) if sum_losses > 0 else None
        )

        hold_periods[key] = {
            "hit_rate": round(hit_rate, 2),
            "avg_return": round(avg_return, 3),
            "median_return": round(median_return, 3),
            "max_gain": round(max_gain, 2),
            "max_loss": round(max_loss, 2),
            "profit_factor": profit_factor,
            "total_trades": total_trades,
        }

    return {
        "ok": True,
        "total_signal_dates": total_signal_dates,
        "total_picks": total_picks,
        "avg_picks_per_day": (
            round(total_picks / total_signal_dates, 1)
            if total_signal_dates > 0
            else 0.0
        ),
        "hold_periods": hold_periods,
        "daily_breakdown": daily_breakdown,
        "rules_used": rules,
        "methodology": (
            "Fraction fields (e.g. confirmation_count '6/8') are compared by "
            "parsing the numerator for numeric operations. "
            "Each signal date T₀ filters stocks, then forward returns are "
            "measured at T₀+1, T₀+2, T₀+3, T₀+5 trading days."
        ),
    }
