"""Test parity between table column picker (SCREENER_COLUMNS) and rule builder dropdown (SCREENER_FILTERS)."""
import re
from pathlib import Path

# Paths to constant files
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "src" / "constants"
COLUMNS_FILE = FRONTEND_DIR / "screenerColumns.js"
FILTERS_FILE = FRONTEND_DIR / "screenerFilters.js"

# Fields intentionally excluded from the rule builder because they are static
# constants (e.g. Supertrend parameter constants 10 and 3) rather than per-stock data.
INTENTIONALLY_EXCLUDED_FIELDS = frozenset({
    "st_period",
    "st_multiplier",
})


def _extract_keys(js_content: str, array_name: str) -> set[str]:
    """Extract all 'key': '...' strings inside a specific exported array."""
    # Find the array block
    match = re.search(rf"export\s+const\s+{array_name}\s*=\s*\[(.*?)\];", js_content, re.DOTALL)
    if not match:
        raise ValueError(f"Could not find array {array_name} in JS file")
    
    block = match.group(1)
    keys = set(re.findall(r'["\']key["\']\s*:\s*["\']([^"\']+)["\']', block))
    return keys


def test_rule_builder_dropdown_parity():
    """Verify that every field available in SCREENER_COLUMNS is available in SCREENER_FILTERS."""
    assert COLUMNS_FILE.exists(), f"Missing {COLUMNS_FILE}"
    assert FILTERS_FILE.exists(), f"Missing {FILTERS_FILE}"

    col_content = COLUMNS_FILE.read_text(encoding="utf-8")
    flt_content = FILTERS_FILE.read_text(encoding="utf-8")

    column_keys = _extract_keys(col_content, "SCREENER_COLUMNS")
    filter_keys = _extract_keys(flt_content, "SCREENER_FILTERS")

    # Determine missing fields
    missing_from_filters = (column_keys - filter_keys) - INTENTIONALLY_EXCLUDED_FIELDS

    assert not missing_from_filters, (
        f"The following {len(missing_from_filters)} fields exist in the table columns "
        f"(SCREENER_COLUMNS) but are missing from the rule builder dropdown (SCREENER_FILTERS): "
        f"{sorted(missing_from_filters)}"
    )


def test_essential_swing_fields_present():
    """Verify that setup, confirmations, and multi-day trajectory fields are in SCREENER_FILTERS."""
    flt_content = FILTERS_FILE.read_text(encoding="utf-8")
    filter_keys = _extract_keys(flt_content, "SCREENER_FILTERS")

    essential_fields = [
        "confirmation_count",
        "setup_strength",
        "setup",
        "trend_direction",
        "trend_strength",
        "signal",
        "consecutive_rising_delivery",
        "accumulation_score",
        "delivery_growth_3d_pct",
        "predictive_setups",
    ]

    for field in essential_fields:
        assert field in filter_keys, f"Essential field '{field}' must be in SCREENER_FILTERS"
