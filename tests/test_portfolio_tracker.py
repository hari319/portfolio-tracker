import io

from stockmon.db.repositories import dividends as div_repo
from stockmon.db.repositories import holdings as hold_repo
from stockmon.db.repositories import summary as sum_repo
from stockmon.portfolio_tracker import (
    calculate_period,
    compute_buy_charge,
    compute_sell_charge,
    compute_summary_panel,
    compute_totals,
    enrich_holding_row,
    enrich_sold_row,
)
from stockmon.sheet_io import export_csv, export_workbook, import_workbook


def test_charge_calculations():
    # Buy charge ≈ 0.119171%
    assert 118.0 <= compute_buy_charge(100000.0) <= 120.0
    # Sell charge ≈ 0.104171%
    assert 103.0 <= compute_sell_charge(100000.0) <= 105.0


def test_calculate_period():
    # Matches Excel: M is the total month count, Y = QUOTIENT(M, 12).
    years, months = calculate_period("2023-01-01", "2024-07-01")
    assert (years, months) == (1, 18)


def test_summary_panel_matches_sheet():
    """The worked example in docs/SHEET_FORMAT.md §4 must reproduce exactly."""
    panel = compute_summary_panel(
        {
            "current_stock_etf_invest": 5213974.77,
            "current_mf_invest": 1300000.00,
            "current_mf_redeem": 450000.00,
            "loan_amount": 6530152.87,
            "current_mf_redeem_profit": 474623.00,
        },
        loan_earned=586778.17,
        loan_loss=0.0,
        loan_dividends=1093.00,
    )
    assert panel["block_a"]["total"] == 6963974.77
    # Deployed more than the loan, so this is negative.
    assert panel["block_b"]["remaining_invest_loan"] == -433821.90
    assert panel["block_b"]["current_remaining"] == 628672.27


def test_partial_sell_lifecycle(clean_tracker):
    h_id, _ = hold_repo.add_holding(
        portfolio_name="MADI",
        symbol="TESTLIFECYCLE",
        scheme_name="Lifecycle Corp",
        invest_date="2024-01-01",
        quantity=100.0,
        avg_price=50.0,
    )

    hold_repo.sell_holding(
        holding_id=h_id,
        sell_date="2024-06-01",
        sell_price=75.0,
        quantity=40.0,
        remarks="Partial exit",
    )

    open_test = hold_repo.list_holdings("MADI", "open")
    assert len(open_test) == 1
    assert open_test[0]["total_qty"] == 60.0

    sold_test = hold_repo.list_holdings("MADI", "sold")
    assert len(sold_test) == 1
    assert sold_test[0]["sold_quantity"] == 40.0
    assert sold_test[0]["sell_price"] == 75.0


def test_sold_query_has_no_duplicate_rows(clean_tracker):
    """A sold holding with several buy lots yields individual sold transactions per lot."""
    h_id, _ = hold_repo.add_holding(
        portfolio_name="BAPA",
        symbol="MULTILOT",
        scheme_name="MULTILOT",
        invest_date="2024-01-01",
        quantity=10.0,
        avg_price=100.0,
    )
    hold_repo.add_buy_lot(h_id, "2024-02-01", 20.0, 110.0)
    hold_repo.add_buy_lot(h_id, "2024-03-01", 30.0, 120.0)
    hold_repo.sell_holding(holding_id=h_id, sell_date="2024-09-01", sell_price=150.0)

    sold = hold_repo.list_holdings("BAPA", "sold")
    assert len(sold) == 3
    assert sum(s["sold_quantity"] for s in sold) == 60.0
    # Each lot preserved with its own invested amount, summing to 6800.00
    assert round(sum(s["invested_amount"] for s in sold), 2) == 6800.00



def test_totals_row():
    rows = [
        {"invested_amount": 1000.0, "current_total": 1200.0, "earned": 195.0, "loss": 0.0},
        {"invested_amount": 500.0, "current_total": 400.0, "earned": 0.0, "loss": -101.0},
    ]
    totals = compute_totals(rows)
    assert totals["invested_amount"] == 1500.0
    assert totals["net_profit"] == 100.0


def _seed_round_trip_data():
    """Multi-lot, sold, dividend and summary data across two portfolios."""
    madi_id, _ = hold_repo.add_holding(
        portfolio_name="MADI",
        symbol="TATAGOLD",
        scheme_name="TATAGOLD",
        invest_date="2025-01-10",
        quantity=100.0,
        avg_price=11.5,
        remarks="ETF",
    )
    hold_repo.add_buy_lot(madi_id, "2025-03-20", 250.0, 12.25, remarks="ETF")

    sold_id, _ = hold_repo.add_holding(
        portfolio_name="MADI",
        symbol="ZENTEC",
        scheme_name="ZENTEC",
        invest_date="2025-02-05",
        quantity=15.0,
        avg_price=1650.0,
        remarks="Swing Self",
    )
    hold_repo.sell_holding(
        holding_id=sold_id,
        sell_date="2025-06-18",
        sell_price=1810.0,
        remarks="Swing Self",
    )

    hold_repo.add_holding(
        portfolio_name="LOAN",
        symbol="HDBFS",
        scheme_name="HDBFS",
        invest_date="2025-04-01",
        quantity=40.0,
        avg_price=740.0,
        person="MADI",
        app="Kite Madi",
        remarks="PEAD",
    )

    div_repo.add_dividend("MADI", "TATAGOLD", 312.5, "21.07")
    div_repo.add_dividend("LOAN", "HDBFS", 780.5, "2025-08-14")

    sum_repo.upsert("loan_amount", 6530152.87, "Loan Amount")
    sum_repo.upsert("current_mf_invest", 1300000.0, "Current MF Invest")


def _snapshot():
    """Everything the workbook is meant to carry, in comparable form."""
    snap = {}
    for port in ("MADI", "BAPA", "LOAN"):
        open_rows = []
        for h in hold_repo.list_holdings(port, "open"):
            lots = hold_repo.get_lots(h["id"])
            open_rows.append((
                h["symbol"],
                h["person"],
                round(h["total_qty"], 2),
                round(h["total_invested"], 2),
                h["first_invest_date"],
                tuple(sorted((round(l["quantity"], 2), round(l["avg_price"], 4)) for l in lots)),
            ))
        sold_rows = [
            (
                s["symbol"],
                round(s["sold_quantity"], 2),
                round(s["sell_price"], 2),
                s["sell_date"],
                s["invest_date"],
            )
            for s in hold_repo.list_holdings(port, "sold")
        ]
        divs = [
            (d["symbol"], round(d["value"], 2), d["received_date"])
            for d in div_repo.list_dividends(port)
        ]
        snap[port] = {
            "open": sorted(open_rows),
            "sold": sorted(sold_rows),
            "dividends": sorted(divs),
        }
    snap["summary"] = sum_repo.get_all()
    return snap


def test_export_import_round_trip(clean_tracker):
    """§1.3 acceptance test: export then re-import must reproduce the same data."""
    _seed_round_trip_data()
    before = _snapshot()

    buf = io.BytesIO()
    export_workbook(buf)
    buf.seek(0)

    result = import_workbook(buf, replace=True)
    assert result["ok"], result

    assert _snapshot() == before


def test_round_trip_keeps_charges_derived(clean_tracker):
    """Exported charges are plain values; re-importing must not freeze them as overrides."""
    hold_repo.add_holding(
        portfolio_name="BAPA",
        symbol="DERIVED",
        scheme_name="DERIVED",
        invest_date="2025-01-02",
        quantity=10.0,
        avg_price=500.0,
    )

    buf = io.BytesIO()
    export_workbook(buf)
    buf.seek(0)
    assert import_workbook(buf, replace=True)["ok"]

    holding = hold_repo.list_holdings("BAPA", "open")[0]
    assert hold_repo.get_lots(holding["id"])[0]["buy_charge"] is None


def test_manual_charge_override_survives_round_trip(clean_tracker):
    hold_repo.add_holding(
        portfolio_name="BAPA",
        symbol="OVERRIDE",
        scheme_name="OVERRIDE",
        invest_date="2025-01-02",
        quantity=10.0,
        avg_price=500.0,
        buy_charge=250.0,
    )

    buf = io.BytesIO()
    export_workbook(buf)
    buf.seek(0)
    assert import_workbook(buf, replace=True)["ok"]

    holding = hold_repo.list_holdings("BAPA", "open")[0]
    assert hold_repo.get_lots(holding["id"])[0]["buy_charge"] == 250.0


def test_enrich_holding_row_derives_columns():
    enriched = enrich_holding_row(
        {
            "total_qty": 10.0,
            "weighted_avg_price": 100.0,
            "total_invested": 1000.0,
            "first_invest_date": "2024-01-01",
        },
        live_price=150.0,
        current_date="2025-01-01",
    )
    assert enriched["years"] == 1
    assert enriched["months"] == 12
    assert enriched["current_total"] == 1500.0
    assert enriched["total_return"] == 50.0
    assert enriched["loss"] == 0.0


def test_enrich_sold_row_uses_sell_date_as_current_date():
    enriched = enrich_sold_row({
        "invest_date": "2024-01-01",
        "sell_date": "2024-07-01",
        "sold_quantity": 10.0,
        "avg_price": 100.0,
        "sell_price": 80.0,
    })
    assert enriched["current_date"] == "2024-07-01"
    assert enriched["earned"] == 0.0
    assert enriched["loss"] < 0


def test_csv_export(clean_tracker):
    buf = io.BytesIO()
    export_csv(buf, portfolio="MADI")
    text = buf.getvalue().decode("utf-8")
    assert "Portfolio Tracker — MADI" in text
    assert "Section,Scheme,Invest Date" in text


def test_sold_ordering_recent_first(clean_tracker):
    """Sold positions must be returned sorted by sell_date descending (recent on top)."""
    h1, _ = hold_repo.add_holding("MADI", "LATE", "Late Exit", "2024-01-01", 10.0, 100.0)
    h2, _ = hold_repo.add_holding("MADI", "EARLY", "Early Exit", "2023-01-01", 10.0, 100.0)
    h3, _ = hold_repo.add_holding("MADI", "MID", "Mid Exit", "2023-06-01", 10.0, 100.0)

    # Sell in non-chronological order
    hold_repo.sell_holding(h1, sell_date="2024-11-20", sell_price=120.0)
    hold_repo.sell_holding(h2, sell_date="2023-05-15", sell_price=110.0)
    hold_repo.sell_holding(h3, sell_date="2024-03-01", sell_price=115.0)

    sold = hold_repo.list_holdings("MADI", "sold")
    assert len(sold) == 3
    # Most recent sell date on top
    assert [r["sell_date"] for r in sold] == ["2024-11-20", "2024-03-01", "2023-05-15"]


