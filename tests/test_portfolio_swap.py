import pytest
from stockmon.db.repositories import holdings as hold_repo
from stockmon.errors import ValidationError
from stockmon.web import create_app


def test_swap_madi_to_bapa(clean_tracker):
    h_id, lot_id = hold_repo.add_holding(
        portfolio_name="MADI",
        symbol="TCS.NS",
        stock_name="Tata Consultancy Services",
        invest_date="2024-01-01",
        quantity=10.0,
        avg_price=3500.0,
    )

    res = hold_repo.swap_holdings(
        holding_ids=[h_id],
        target_portfolio="BAPA",
    )
    assert res["ok"] is True
    assert res["swapped_count"] == 1

    h = hold_repo.get_holding(h_id)
    assert h is not None
    assert h["portfolio_name"] == "BAPA"
    assert h["person"] is None


def test_swap_to_loan_with_person(clean_tracker):
    h_id, _ = hold_repo.add_holding(
        portfolio_name="MADI",
        symbol="INFY.NS",
        stock_name="Infosys Limited",
        invest_date="2024-01-01",
        quantity=20.0,
        avg_price=1400.0,
    )

    # Missing person raises error
    with pytest.raises(ValidationError):
        hold_repo.swap_holdings(
            holding_ids=[h_id],
            target_portfolio="LOAN",
            target_person=None,
        )

    res = hold_repo.swap_holdings(
        holding_ids=[h_id],
        target_portfolio="LOAN",
        target_person="MADI",
    )
    assert res["ok"] is True
    assert res["swapped_count"] == 1

    h = hold_repo.get_holding(h_id)
    assert h["portfolio_name"] == "LOAN"
    assert h["person"] == "MADI"


def test_swap_loan_to_bapa_clears_person(clean_tracker):
    h_id, _ = hold_repo.add_holding(
        portfolio_name="LOAN",
        symbol="HDFCBANK.NS",
        stock_name="HDFC Bank",
        person="BAPA",
        invest_date="2024-01-01",
        quantity=15.0,
        avg_price=1600.0,
    )

    res = hold_repo.swap_holdings(
        holding_ids=[h_id],
        target_portfolio="BAPA",
    )
    assert res["ok"] is True
    assert res["swapped_count"] == 1

    h = hold_repo.get_holding(h_id)
    assert h["portfolio_name"] == "BAPA"
    assert h["person"] is None


def test_swap_duplicate_symbol_merges_lots(clean_tracker):
    # BAPA already has RELIANCE.NS with 1 lot (10 shares)
    bapa_hid, bapa_lot = hold_repo.add_holding(
        portfolio_name="BAPA",
        symbol="RELIANCE.NS",
        stock_name="Reliance Industries",
        invest_date="2024-01-01",
        quantity=10.0,
        avg_price=2800.0,
    )

    # MADI has RELIANCE.NS with 1 lot (5 shares)
    madi_hid, madi_lot = hold_repo.add_holding(
        portfolio_name="MADI",
        symbol="RELIANCE.NS",
        stock_name="Reliance Industries",
        invest_date="2024-02-01",
        quantity=5.0,
        avg_price=2900.0,
    )

    # Swap MADI's holding to BAPA — should merge lots into BAPA's existing holding
    res = hold_repo.swap_holdings(
        holding_ids=[madi_hid],
        target_portfolio="BAPA",
    )
    assert res["ok"] is True
    assert res["merged_count"] == 1

    # Source holding in MADI should be deleted
    assert hold_repo.get_holding(madi_hid) is None

    # Destination holding in BAPA should now have 2 lots
    bapa_lots = hold_repo.get_lots(bapa_hid)
    assert len(bapa_lots) == 2
    lot_quantities = {lot["quantity"] for lot in bapa_lots}
    assert lot_quantities == {10.0, 5.0}


def test_swap_api_route(clean_tracker):
    app = create_app()
    client = app.test_client()

    h_id, _ = hold_repo.add_holding(
        portfolio_name="MADI",
        symbol="ITC.NS",
        stock_name="ITC Limited",
        invest_date="2024-01-01",
        quantity=100.0,
        avg_price=400.0,
    )

    # Invalid target
    resp = client.post("/api/portfolio-tracker/swap", json={
        "holding_ids": [h_id],
        "target_portfolio": "INVALID",
    })
    assert resp.status_code == 400

    # Valid swap to LOAN
    resp = client.post("/api/portfolio-tracker/swap", json={
        "holding_ids": [h_id],
        "target_portfolio": "LOAN",
        "target_person": "BAPA",
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["swapped_count"] == 1

    h = hold_repo.get_holding(h_id)
    assert h["portfolio_name"] == "LOAN"
    assert h["person"] == "BAPA"
