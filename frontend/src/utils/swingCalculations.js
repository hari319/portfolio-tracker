/**
 * Utilities for parsing numeric ranges and calculating percentage distances
 * for the Swing Tracker tab.
 */

const RANGE_REGEX = /^\s*([0-9]+(?:\.[0-9]+)?)\s*(?:-|–|—|to)\s*([0-9]+(?:\.[0-9]+)?)\s*$/i;
const SINGLE_REGEX = /^\s*([0-9]+(?:\.[0-9]+)?)\s*$/;

/**
 * Parses a single number or a range (e.g. "100-105", "100 - 105", "100 to 105").
 * Returns: { avg: number | null, isRange: boolean, low: number | null, high: number | null }
 */
export function parseRangeOrNumber(val) {
  if (val === undefined || val === null) {
    return { avg: null, isRange: false, low: null, high: null };
  }

  if (typeof val === 'number') {
    return isNaN(val)
      ? { avg: null, isRange: false, low: null, high: null }
      : { avg: val, isRange: false, low: val, high: val };
  }

  const cleaned = String(val).trim().replace(/[₹$,]/g, '');
  if (!cleaned) {
    return { avg: null, isRange: false, low: null, high: null };
  }

  const rangeMatch = cleaned.match(RANGE_REGEX);
  if (rangeMatch) {
    const n1 = parseFloat(rangeMatch[1]);
    const n2 = parseFloat(rangeMatch[2]);
    if (!isNaN(n1) && !isNaN(n2)) {
      const low = Math.min(n1, n2);
      const high = Math.max(n1, n2);
      const avg = Number(((low + high) / 2).toFixed(2));
      return { avg, isRange: true, low, high };
    }
  }

  const singleMatch = cleaned.match(SINGLE_REGEX);
  if (singleMatch) {
    const n = parseFloat(singleMatch[1]);
    if (!isNaN(n)) {
      return { avg: n, isRange: false, low: n, high: n };
    }
  }

  return { avg: null, isRange: false, low: null, high: null };
}

/**
 * Calculates percentage distance from Current Price to Target/Zone/SL value.
 * Formula: ((value - currentPrice) / currentPrice) * 100
 * If value is a range, uses the range's average.
 */
export function calculateDistancePct(currentPrice, targetVal) {
  if (currentPrice === undefined || currentPrice === null) return null;
  const cp = Number(currentPrice);
  if (isNaN(cp) || cp <= 0) return null;

  const { avg } = parseRangeOrNumber(targetVal);
  if (avg === null || isNaN(avg)) return null;

  return Number((((avg - cp) / cp) * 100).toFixed(2));
}

/**
 * Determines whether the current price is currently inside the Buy Zone range.
 */
export function isInsideBuyZone(currentPrice, buyZoneVal) {
  if (currentPrice === undefined || currentPrice === null) return false;
  const cp = Number(currentPrice);
  if (isNaN(cp) || cp <= 0) return false;

  const { isRange, low, high, avg } = parseRangeOrNumber(buyZoneVal);
  if (isRange && low !== null && high !== null) {
    return cp >= low && cp <= high;
  }
  if (avg !== null) {
    return Math.abs(cp - avg) / avg < 0.005; // within 0.5%
  }
  return false;
}
