"""Multi-Day Sequence Analyzer & Predictive Screener.

Analyzes the chronological sequence (up to 11 trading days) of stock data
to detect predictive footprints:
1. Silent Institutional Accumulation (rising delivery build-up in flat base)
2. Fresh Signal Flips (Supertrend or 20 SMA flipped within last 24-48 hours)
3. Multi-Day VCP Coiling & Breakouts
4. Consecutive Higher Lows (Institutional staircase)

Now reads from ``screener_cache.db`` via indexed queries instead of parsing
~154 MB of JSON files.  The file-based cache (multi_day_analysis_cache.json)
is replaced by an in-memory cache keyed on dates.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from .db.repositories import screener as _screener_repo
from .screener import (
    fetch_screener_data,
    list_saved_screener_dates,
    load_cached_screener,
)

logger = logging.getLogger(__name__)

# In-memory cache to answer repeat requests in <1ms
_MEMORY_CACHE: dict[str, Any] | None = None
_MEMORY_CACHE_KEY: str | None = None


def clear_multi_day_cache() -> None:
    """Invalidate in-memory multi-day trajectory cache."""
    global _MEMORY_CACHE, _MEMORY_CACHE_KEY
    _MEMORY_CACHE = None
    _MEMORY_CACHE_KEY = None


def _compute_cache_key(dates: list[str]) -> str:
    """Create a cache fingerprint based on dates available in the DB."""
    return "|".join(dates)


def sync_historical_dates(
    target_dates: list[str] | None = None,
    max_days: int = 11,
    delay_seconds: float = 1.0,
    progress_callback: Callable[[str, int, int], None] | None = None,
) -> dict[str, Any]:
    """Sync missing historical dates from the screener API into the DB."""
    # Discover available dates from latest cached screener or fetch latest
    if not target_dates:
        latest = load_cached_screener()
        if not latest:
            latest = fetch_screener_data()
        available = latest.get("dates", []) if latest else []
        target_dates = available[:max_days]

    if not target_dates:
        import datetime
        target_dates = [datetime.date.today().isoformat()]

    synced_dates: list[str] = []
    already_cached: list[str] = []
    failed_dates: list[dict[str, str]] = []

    total_targets = len(target_dates)

    for idx, date_str in enumerate(target_dates, start=1):
        clean_date = date_str.strip()

        # Check the DB instead of the filesystem
        if _screener_repo.date_exists(clean_date):
            already_cached.append(clean_date)
            if progress_callback:
                progress_callback(clean_date, idx, total_targets)
            continue

        logger.info("Syncing historical screener dataset for %s (%d/%d)...", clean_date, idx, total_targets)
        try:
            fetch_screener_data(date=clean_date)
            synced_dates.append(clean_date)
            if progress_callback:
                progress_callback(clean_date, idx, total_targets)
            if idx < total_targets and delay_seconds > 0:
                time.sleep(delay_seconds)
        except Exception as exc:
            logger.warning("Failed to sync date %s: %s", clean_date, exc)
            failed_dates.append({"date": clean_date, "error": str(exc)})

    if synced_dates:
        clear_multi_day_cache()

    all_saved = list_saved_screener_dates()
    return {
        "ok": len(failed_dates) == 0,
        "target_dates": target_dates,
        "synced_dates": synced_dates,
        "already_cached": already_cached,
        "failed_dates": failed_dates,
        "total_cached": len(all_saved),
        "available_saved_dates": all_saved,
    }


def analyze_multi_day_sequences(
    target_dates: list[str] | None = None,
    max_days: int = 11,
    force_recompute: bool = False,
) -> dict[str, Any]:
    """Analyze multi-day sequence trajectories across saved historical dates.

    Now uses indexed DB queries instead of parsing full JSON files.
    """
    global _MEMORY_CACHE, _MEMORY_CACHE_KEY

    saved = list_saved_screener_dates()
    if not saved:
        return {"ok": False, "error": "No saved screener data available to analyze."}

    # Available dates sorted chronologically (oldest -> newest)
    all_saved_dates = sorted([x["date"] for x in saved])

    if target_dates:
        selected_dates = [d for d in all_saved_dates if d in target_dates]
    else:
        selected_dates = all_saved_dates[-max_days:]

    if not selected_dates:
        return {"ok": False, "error": "No matching saved screener dates to analyze."}

    cache_key = _compute_cache_key(selected_dates)

    # 1. Check in-memory cache
    if not force_recompute and _MEMORY_CACHE is not None and _MEMORY_CACHE_KEY == cache_key:
        return _MEMORY_CACHE

    # 2. Compute trajectory analysis using indexed DB queries
    t0 = time.time()

    # Load hot columns from DB — this replaces the 154 MB file-parsing path
    hot_rows = _screener_repo.load_hot_columns_for_dates(selected_dates)

    # Also load full data for the latest date (needed for UI rendering)
    latest_date = selected_dates[-1]
    latest_data = _screener_repo.load_screener_for_date(latest_date)
    latest_items = {item.get("symbol"): item for item in (latest_data.get("items", []) if latest_data else [])}

    # Build per-symbol time series from DB results
    # Group hot rows by symbol
    symbol_history: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for row in hot_rows:
        symbol = row.get("symbol")
        if not symbol:
            continue
        if symbol not in symbol_history:
            symbol_history[symbol] = []
        symbol_history[symbol].append((row["trade_date"], row))

    num_days = len(selected_dates)
    analyzed_items: list[dict[str, Any]] = []
    items_by_symbol: dict[str, dict[str, Any]] = {}

    setups_summary = {
        "silent_accumulation": 0,
        "fresh_signal_flip": 0,
        "vcp_breakout": 0,
        "momentum_staircase": 0,
    }

    for symbol, hist in symbol_history.items():
        # Get the full current item from the latest date
        current_item = latest_items.get(symbol)
        if not current_item:
            # Build a minimal item from the last hot row
            if hist:
                last_row = hist[-1][1]
                current_item = dict(last_row)
            else:
                continue

        item_enriched = dict(current_item)
        k = len(hist)

        # 1. Delivery Growth & Consecutive Rising Delivery
        consecutive_rising_delivery = 0
        delivery_growth_3d_pct = 0.0

        if k >= 2:
            for i in range(k - 1, 0, -1):
                cur_deliv = hist[i][1].get("delivery_qty") or hist[i][1].get("delivery_percent") or 0
                prev_deliv = hist[i - 1][1].get("delivery_qty") or hist[i - 1][1].get("delivery_percent") or 0
                if cur_deliv > prev_deliv:
                    consecutive_rising_delivery += 1
                else:
                    break

            start_idx = max(0, k - 4)
            d_start = hist[start_idx][1].get("delivery_qty") or 0
            d_end = hist[-1][1].get("delivery_qty") or 0
            if d_start > 0:
                delivery_growth_3d_pct = round(((d_end - d_start) / d_start) * 100, 1)

        # 2. Consecutive Higher Lows
        consecutive_higher_lows = 0
        if k >= 2:
            for i in range(k - 1, 0, -1):
                cur_low = hist[i][1].get("low") or 0
                prev_low = hist[i - 1][1].get("low") or 0
                if cur_low > prev_low:
                    consecutive_higher_lows += 1
                else:
                    break

        # 3. Fresh Supertrend Flip Days
        supertrend_flip_days: int | None = None
        current_st = current_item.get("supertrend_dir")
        if current_st == 1 or str(current_st) == "1":
            for i in range(k - 1, -1, -1):
                st_val = hist[i][1].get("supertrend_dir")
                if st_val != 1 and str(st_val) != "1":
                    supertrend_flip_days = (k - 1) - i - 1
                    break
            if supertrend_flip_days is None:
                supertrend_flip_days = k

        # 4. Fresh SMA 20 Cross Days
        ma20_cross_days: int | None = None
        cur_close = current_item.get("close") or 0
        cur_sma20 = current_item.get("sma_20") or 0
        if cur_close > cur_sma20 > 0:
            for i in range(k - 1, -1, -1):
                c = hist[i][1].get("close") or 0
                sma = hist[i][1].get("sma_20") or 0
                if c <= sma and sma > 0:
                    ma20_cross_days = (k - 1) - i - 1
                    break
            if ma20_cross_days is None:
                ma20_cross_days = k

        # 5. Multi-Day Volatility Contraction (VCP Ratio)
        vcp_compression_ratio: float | None = None
        if k >= 5:
            recent_lows = [h[1].get("low") or 0 for h in hist[-3:]]
            recent_highs = [h[1].get("high") or 0 for h in hist[-3:]]
            older_lows = [h[1].get("low") or 0 for h in hist[:-2]]
            older_highs = [h[1].get("high") or 0 for h in hist[:-2]]

            r_low = min(filter(lambda x: x > 0, recent_lows), default=0)
            r_high = max(recent_highs, default=0)
            o_low = min(filter(lambda x: x > 0, older_lows), default=0)
            o_high = max(older_highs, default=0)

            if r_low > 0 and o_low > 0 and o_high > o_low:
                r_range = (r_high - r_low) / r_low
                o_range = (o_high - o_low) / o_low
                if o_range > 0:
                    vcp_compression_ratio = round(r_range / o_range, 2)

        # 6. Price change across observed window
        p_start = hist[0][1].get("close") or 1
        p_end = hist[-1][1].get("close") or 1
        window_price_change_pct = round(((p_end - p_start) / p_start) * 100, 2) if p_start else 0.0

        # 7. Accumulation Score (0-100)
        score = 0
        if consecutive_rising_delivery >= 3:
            score += 30
        elif consecutive_rising_delivery == 2:
            score += 20
        elif consecutive_rising_delivery == 1:
            score += 10

        deliv_pct = current_item.get("delivery_percent") or 0
        if deliv_pct >= 60:
            score += 20
        elif deliv_pct >= 45:
            score += 15
        elif deliv_pct >= 30:
            score += 10

        cnh = current_item.get("close_near_high_pct") or 0
        if cnh >= 85:
            score += 20
        elif cnh >= 75:
            score += 15
        elif cnh >= 60:
            score += 10

        if abs(window_price_change_pct) <= 4.0:
            score += 20
        elif abs(window_price_change_pct) <= 7.0:
            score += 10

        rvol = current_item.get("volume_ratio_20") or 0
        if rvol >= 1.5:
            score += 10
        elif rvol >= 1.2:
            score += 5

        accumulation_score = min(100, score)

        # 8. Setup Categorization
        predictive_setups = []

        if accumulation_score >= 65 and abs(window_price_change_pct) <= 5.0 and deliv_pct >= 35:
            predictive_setups.append("silent_accumulation")
            setups_summary["silent_accumulation"] += 1

        if (
            (supertrend_flip_days in (0, 1) or ma20_cross_days in (0, 1))
            and rvol >= 1.2
            and (current_item.get("pct_change") or 0) > 0
        ):
            predictive_setups.append("fresh_signal_flip")
            setups_summary["fresh_signal_flip"] += 1

        if (
            ((vcp_compression_ratio is not None and vcp_compression_ratio <= 0.65) or (current_item.get("range_pct_5") or 100) <= 6.0)
            and rvol >= 1.4
            and (current_item.get("pct_change") or 0) >= 1.5
            and cnh >= 75
        ):
            predictive_setups.append("vcp_breakout")
            setups_summary["vcp_breakout"] += 1

        if consecutive_higher_lows >= 3 and (current_item.get("pct_change") or 0) >= 0.5:
            predictive_setups.append("momentum_staircase")
            setups_summary["momentum_staircase"] += 1

        metrics = {
            "accumulation_score": accumulation_score,
            "consecutive_rising_delivery": consecutive_rising_delivery,
            "delivery_growth_3d_pct": delivery_growth_3d_pct,
            "consecutive_higher_lows": consecutive_higher_lows,
            "supertrend_flip_days": supertrend_flip_days,
            "ma20_cross_days": ma20_cross_days,
            "vcp_compression_ratio": vcp_compression_ratio,
            "window_price_change_pct": window_price_change_pct,
            "predictive_setups": predictive_setups,
            "analyzed_days_count": k,
        }

        item_enriched.update(metrics)
        analyzed_items.append(item_enriched)
        items_by_symbol[symbol] = metrics

    logger.info(
        "Analyzed multi-day sequence across %d dates for %d stocks in %.2fs. Setups: %s",
        num_days,
        len(analyzed_items),
        time.time() - t0,
        setups_summary,
    )

    result = {
        "ok": True,
        "cache_key": cache_key,
        "latest_date": latest_date,
        "dates_analyzed": selected_dates,
        "days_count": num_days,
        "total_stocks": len(analyzed_items),
        "setups_summary": setups_summary,
        "items": analyzed_items,
        "items_by_symbol": items_by_symbol,
    }

    _MEMORY_CACHE = result
    _MEMORY_CACHE_KEY = cache_key

    return result
