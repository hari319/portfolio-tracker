"""Comprehensive tests for StockName persistence, lookup fallback, export round-trip,
and sticky header styling rules.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from stockmon.db.repositories import holdings as hold_repo
from stockmon.sheet_format import (
    HOLDING_COLUMNS,
    HOLDINGS_HEADER_LABELS,
    SOLD_START_COLUMN,
)
from stockmon.sheet_io import export_csv, export_workbook, import_workbook


def test_schema_and_migration_has_stock_name(clean_tracker):
    """Verify that the holding table contains the stock_name column."""
    conn = clean_tracker
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(holding)").fetchall()]
    assert "stock_name" in cols
    assert "scheme_name" in cols


def test_holding_persistence_with_stock_name(clean_tracker):
    """Verify add_holding, update_holding, sell_holding and update_sold_position persist stock_name."""
    # 1. Add open holding with explicit stock_name
    h_id, _ = hold_repo.add_holding(
        portfolio_name="MADI",
        symbol="TCS",
        scheme_name="Tata Consultancy Services Ltd",
        stock_name="Tata Consultancy Services Limited",
        invest_date="2025-01-15",
        quantity=10.0,
        avg_price=3500.0,
        remarks="Core portfolio",
    )

    holdings = hold_repo.list_holdings("MADI", "open")
    assert len(holdings) == 1
    assert holdings[0]["symbol"] == "TCS"
    assert holdings[0]["stock_name"] == "Tata Consultancy Services Limited"

    # 2. Update holding stock_name
    hold_repo.update_holding(
        holding_id=h_id,
        symbol="TCS",
        stock_name="Tata Consultancy Services Ltd (Updated)",
        remarks="Core portfolio updated",
    )
    updated = hold_repo.get_holding(h_id)
    assert updated["stock_name"] == "Tata Consultancy Services Ltd (Updated)"

    # 3. Sell holding and verify stock_name is copied over to sold record
    sale_id = hold_repo.sell_holding(
        holding_id=h_id,
        sell_date="2025-06-01",
        sell_price=3900.0,
        remarks="Partial/full exit",
    )
    sold_list = hold_repo.list_holdings("MADI", "sold")
    assert len(sold_list) == 1
    assert sold_list[0]["symbol"] == "TCS"
    assert sold_list[0]["stock_name"] == "Tata Consultancy Services Ltd (Updated)"
    sold_holding_id = sold_list[0]["id"]

    # 4. Update sold position stock_name
    hold_repo.update_sold_position(
        holding_id=sold_holding_id,
        symbol="TCS",
        stock_name="TCS Limited Final",
        invest_date="2025-01-15",
        sell_date="2025-06-01",
        quantity=10.0,
        avg_price=3500.0,
        sell_price=3900.0,
        remarks="Exit completed",
    )
    sold_updated = hold_repo.get_holding(sold_holding_id)
    assert sold_updated["stock_name"] == "TCS Limited Final"


def test_holding_fallback_when_stock_name_empty(clean_tracker):
    """When stock_name is omitted, it gracefully falls back to scheme_name or symbol."""
    h_id, _ = hold_repo.add_holding(
        portfolio_name="BAPA",
        symbol="INFY",
        scheme_name="Infosys Ltd",
        invest_date="2025-02-01",
        quantity=20.0,
        avg_price=1400.0,
    )
    holding = hold_repo.get_holding(h_id)
    # Both stock_name and scheme_name should be preserved
    assert holding["scheme_name"] == "Infosys Ltd"
    assert holding["stock_name"] in ("Infosys Ltd", "")

    holdings = hold_repo.list_holdings("BAPA", "open")
    assert len(holdings) == 1
    assert holdings[0]["stock_name"] == "Infosys Ltd"


def test_csv_export_format_and_no_lingering_scheme_header(clean_tracker):
    """CSV export must include StockTicker and StockName without lingering Scheme header."""
    hold_repo.add_holding(
        portfolio_name="MADI",
        symbol="RELIANCE",
        scheme_name="Reliance Industries Limited",
        stock_name="Reliance Industries Limited",
        invest_date="2025-01-10",
        quantity=5.0,
        avg_price=2400.0,
    )

    buf = io.BytesIO()
    export_csv(buf, portfolio="MADI")
    content = buf.getvalue().decode("utf-8")

    assert "StockTicker" in content
    assert "StockName" in content
    assert "RELIANCE" in content
    assert "Reliance Industries Limited" in content

    # Header line must not have standalone 'Scheme'
    header_line = [line for line in content.splitlines() if line.startswith("Section,")][0]
    headers = header_line.split(",")
    assert "Scheme" not in headers
    assert headers[1] == "StockTicker"
    assert headers[2] == "StockName"


def test_workbook_round_trip_preserves_stock_name(clean_tracker):
    """Workbook export with 19 columns re-imports cleanly with stock_name preserved."""
    h_id, _ = hold_repo.add_holding(
        portfolio_name="MADI",
        symbol="TATAMOTORS",
        scheme_name="Tata Motors Limited",
        stock_name="Tata Motors Passenger & Commercial",
        invest_date="2025-01-05",
        quantity=50.0,
        avg_price=700.0,
        remarks="Auto EV",
    )
    hold_repo.sell_holding(
        holding_id=h_id,
        sell_date="2025-05-10",
        sell_price=850.0,
        remarks="Target reached",
    )

    # Export to Excel
    buf = io.BytesIO()
    export_workbook(buf)
    buf.seek(0)

    # Re-import with replace=True
    report = import_workbook(buf, replace=True)
    assert report["ok"] is True

    # Check imported sold holding has stock_name preserved
    sold_list = hold_repo.list_holdings("MADI", "sold")
    assert len(sold_list) == 1
    assert sold_list[0]["symbol"] == "TATAMOTORS"
    assert sold_list[0]["stock_name"] == "Tata Motors Passenger & Commercial"


def test_sticky_header_css_rules_present():
    """Verify custom.css defines vertical pinning (top: 0) and horizontal pinning (left: 0) for sticky ticker headers."""
    css_path = Path(__file__).resolve().parent.parent / "frontend" / "src" / "styles" / "custom.css"
    assert css_path.exists(), f"custom.css not found at {css_path}"

    css_content = css_path.read_text(encoding="utf-8")

    # Check that thead th for sticky ticker has top: 0 and left: 0
    assert "thead th.col-sticky-ticker" in css_content
    assert "top: 0 !important" in css_content
    assert "left: 0 !important" in css_content

    # Check that stock name tooltip styles are present
    assert ".stock-info-tooltip-trigger" in css_content
    assert ".stock-name-tooltip" in css_content
