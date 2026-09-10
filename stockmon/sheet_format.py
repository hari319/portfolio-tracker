"""Machine-readable specification and helpers for the Google Sheet / Excel workbook.

Shared by both sheet_io.py (importer) and the exporter so layouts and
headers can never drift out of sync.
See docs/SHEET_FORMAT.md for the full documentation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

# Normalized portfolio keys mapped to workbook sheet names
SHEET_NAMES = {
    "MADI": "Stock Madi",
    "BAPA": "Stock Bapa",
    "LOAN": "Loan ",  # Note the trailing space in the Excel workbook
}

REVERSE_SHEET_NAMES = {v.strip().lower(): k for k, v in SHEET_NAMES.items()}
# Support both exact and stripped lookup
for k, v in SHEET_NAMES.items():
    REVERSE_SHEET_NAMES[v] = k

# Standard column headers in the spreadsheet
HOLDING_COLUMNS = [
    "StockTicker",
    "StockName",
    "Invest Date",
    "Current Date",
    "Y",
    "M",
    "Q",
    "Avg",
    "LTP",
    "Invested ",
    "Buy Charge",
    "Sell Charge",
    "Current Total",
    "Earned ",
    "Loss",
    "Annual Return",
    "Total Return",
    "App",
    "Remarks",
]

DIVIDEND_COLUMNS = ["Stock", "Divi", "Term"]

# Section markers used to locate blocks on a sheet without relying on row numbers,
# so an exported workbook (whose rows shift with the data) re-imports correctly.
HOLDINGS_HEADER_LABEL = "stockticker"
HOLDINGS_HEADER_LABELS = ("stockticker", "scheme")
SOLD_SECTION_LABELS = ("sold", "stock sold")
DIVIDEND_SECTION_LABEL = "dividend"
DIVIDEND_HEADER_LABEL = "stock"
TOTAL_ROW_LABEL = "total"

# Column holding the Sold block: MADI stacks it below Holdings, the others sit side-by-side.
SOLD_START_COLUMN = {"MADI": 1, "BAPA": 21, "LOAN": 21}

# Row numbers from the original Invest.xlsx (docs/SHEET_FORMAT.md §3).
# Only used when the markers above cannot be found on a sheet.
FALLBACK_LAYOUT = {
    "MADI": {"holdings_start": 3, "sold_start": 78, "dividend_start": 137},
    "BAPA": {"holdings_start": 3, "sold_start": 3, "dividend_start": 197},
    "LOAN": {"holdings_start": 3, "sold_start": 3, "dividend_start": 298},
}

# Summary panel columns on the Loan sheet (AO = label, AP = value).
SUMMARY_LABEL_COLUMN = 41
SUMMARY_VALUE_COLUMN = 42

# Loan sheet Summary Panel items (Cols 39-40, rows 76-87 in Loan sheet)
SUMMARY_PANEL_CONFIG = [
    {
        "key": "current_stock_etf_invest",
        "label": "Current Stock & ETF Invest",
        "type": "fixed",
        "row": 76,
    },
    {
        "key": "current_mf_invest",
        "label": "Current MF Invest",
        "type": "fixed",
        "row": 77,
    },
    {
        "key": "current_mf_redeem",
        "label": "Current MF Redeem",
        "type": "fixed",
        "row": 78,
    },
    {
        "key": "_total_invest",
        "label": "Total ",
        "type": "computed",
        "row": 79,
    },
    {
        "key": "loan_amount",
        "label": "Loan Amount",
        "type": "fixed",
        "row": 82,
    },
    {
        "key": "_remaining_invest_loan",
        "label": "Reamining Invest From Loan",
        "type": "computed",
        "row": 83,
    },
    {
        "key": "_stock_profit",
        "label": "Stock Proift ",
        "type": "computed",
        "row": 84,
    },
    {
        "key": "_total_dividend",
        "label": "Dividend",
        "type": "computed",
        "row": 85,
    },
    {
        "key": "current_mf_redeem_profit",
        "label": "Current MF Reddem + Profit",
        "type": "fixed",
        "row": 86,
    },
    {
        "key": "_current_remaining",
        "label": "Current Remaining",
        "type": "computed",
        "row": 87,
    },
]


def normalize_label(raw: Any) -> str:
    """Lower-case and collapse whitespace so sheet labels compare reliably.

    Sheet labels carry stray spaces and typos (``'Loan '``, ``'Earned '``).
    """
    if raw is None:
        return ""
    return " ".join(str(raw).split()).strip().lower()


def parse_sheet_date(raw: Any) -> str:
    """Normalize Excel date representation to 'YYYY-MM-DD' or keep original format.

    Excel dates may be:
    - datetime / date object
    - String like '18.09.25' (DD.MM.YY) or '04.04.2025' or '2025-04-04'
    """
    if raw is None:
        return ""
    if isinstance(raw, (datetime, date)):
        return raw.strftime("%Y-%m-%d")
    s = str(raw).strip()
    if not s:
        return ""

    # Common dot format 'DD.MM.YY' or 'DD.MM.YYYY'
    if "." in s:
        parts = [p.strip() for p in s.split(".") if p.strip()]
        if len(parts) == 3:
            try:
                day = int(parts[0])
                month = int(parts[1])
                year = int(parts[2])
                if year < 100:
                    year += 2000
                return f"{year:04d}-{month:02d}-{day:02d}"
            except ValueError:
                return s
        elif len(parts) == 2:
            # e.g. '1.09' or '28.08' in dividend terms
            return s

    # Slash format 'DD/MM/YY' or 'DD/MM/YYYY'
    if "/" in s:
        parts = [p.strip() for p in s.split("/") if p.strip()]
        if len(parts) == 3:
            try:
                day = int(parts[0])
                month = int(parts[1])
                year = int(parts[2])
                if year < 100:
                    year += 2000
                return f"{year:04d}-{month:02d}-{day:02d}"
            except ValueError:
                return s

    return s


def format_sheet_date(iso_date: str) -> str:
    """Format 'YYYY-MM-DD' to Excel sheet standard 'DD/MM/YYYY'."""
    if not iso_date:
        return ""
    try:
        dt = datetime.strptime(iso_date, "%Y-%m-%d")
        return dt.strftime("%d/%m/%Y")
    except ValueError:
        return iso_date



def map_app_to_person(app_val: Any) -> str | None:
    """Map the 'App' column (e.g. 'Kite Madi', 'Kite Bapa') to person 'MADI' | 'BAPA'."""
    if not app_val:
        return None
    s = str(app_val).strip().upper()
    if "MADI" in s:
        return "MADI"
    if "BAPA" in s:
        return "BAPA"
    return None
