from stockmon.db.repositories import holdings as hold_repo


def test_update_buy_lot(clean_tracker):
    h_id, lot_id = hold_repo.add_holding(
        portfolio_name="MADI",
        symbol="TATAMOTORS",
        scheme_name="Tata Motors Ltd",
        invest_date="2024-01-10",
        quantity=50.0,
        avg_price=800.0,
        remarks="Initial lot",
    )

    # Verify initial state
    lots = hold_repo.get_lots(h_id)
    assert len(lots) == 1
    assert lots[0]["quantity"] == 50.0
    assert lots[0]["avg_price"] == 800.0

    # Update lot
    success = hold_repo.update_lot(
        lot_id=lot_id,
        invest_date="2024-01-15",
        quantity=60.0,
        avg_price=820.0,
        invested_amount=49200.0,
        buy_charge=58.5,
        remarks="Corrected quantity and price",
    )
    assert success is True

    # Verify updated lot
    updated_lot = hold_repo.get_lot(lot_id)
    assert updated_lot is not None
    assert updated_lot["invest_date"] == "2024-01-15"
    assert updated_lot["quantity"] == 60.0
    assert updated_lot["avg_price"] == 820.0
    assert updated_lot["invested_amount"] == 49200.0
    assert updated_lot["buy_charge"] == 58.5
    assert updated_lot["remarks"] == "Corrected quantity and price"

    # Verify holding aggregates update
    holdings = hold_repo.list_holdings("MADI", "open")
    assert len(holdings) == 1
    assert holdings[0]["total_qty"] == 60.0
    assert holdings[0]["weighted_avg_price"] == 820.0
    assert holdings[0]["total_invested"] == 49200.0


def test_update_holding_metadata(clean_tracker):
    h_id, _ = hold_repo.add_holding(
        portfolio_name="LOAN",
        symbol="INCORRECT",
        scheme_name="Wrong Scheme",
        invest_date="2024-02-01",
        quantity=10.0,
        avg_price=100.0,
        person="MADI",
        remarks="Old note",
    )

    success = hold_repo.update_holding(
        holding_id=h_id,
        symbol="CORRECT",
        scheme_name="Correct Scheme Name",
        person="BAPA",
        remarks="Updated note",
    )
    assert success is True

    h = hold_repo.get_holding(h_id)
    assert h["symbol"] == "CORRECT"
    assert h["scheme_name"] == "Correct Scheme Name"
    assert h["person"] == "BAPA"
    assert h["remarks"] == "Updated note"


def test_update_sold_position(clean_tracker):
    h_id, _ = hold_repo.add_holding(
        portfolio_name="BAPA",
        symbol="INFY",
        scheme_name="Infosys Ltd",
        invest_date="2024-01-01",
        quantity=20.0,
        avg_price=1500.0,
    )
    hold_repo.sell_holding(
        holding_id=h_id,
        sell_date="2024-05-01",
        sell_price=1600.0,
        remarks="Sold on target",
    )

    sold = hold_repo.list_holdings("BAPA", "sold")
    assert len(sold) == 1
    sold_hid = sold[0]["id"]
    assert sold[0]["sold_quantity"] == 20.0
    assert sold[0]["sell_price"] == 1600.0

    # Correct values in sold position
    success = hold_repo.update_sold_position(
        holding_id=sold_hid,
        invest_date="2024-01-05",
        sell_date="2024-05-10",
        quantity=25.0,
        avg_price=1480.0,
        sell_price=1650.0,
        invested_amount=37000.0,
        buy_charge=44.0,
        sell_charge=42.0,
        remarks="Corrected sell record",
        person="BAPA",
    )
    assert success is True

    updated_sold = hold_repo.list_holdings("BAPA", "sold")
    assert len(updated_sold) == 1
    s = updated_sold[0]
    assert s["invest_date"] == "2024-01-05"
    assert s["sell_date"] == "2024-05-10"
    assert s["sold_quantity"] == 25.0
    assert s["avg_price"] == 1480.0
    assert s["sell_price"] == 1650.0
    assert s["invested_amount"] == 37000.0
    assert s["buy_charge"] == 44.0
    assert s["sell_charge"] == 42.0
    assert s["sale_remarks"] == "Corrected sell record"


def test_api_update_holding_with_ticker_lookup_and_resolution(clean_tracker, monkeypatch):
    """Verify PUT /api/portfolio-tracker/holding/<id> resolves stock_name automatically from ticker."""
    from stockmon.web import create_app
    app = create_app()
    client = app.test_client()

    # Add holding with dummy scheme_name
    h_id, _ = hold_repo.add_holding(
        portfolio_name="MADI",
        symbol="TEMP",
        scheme_name="Temporary Name",
        stock_name="Temporary Name",
        invest_date="2024-01-01",
        quantity=10.0,
        avg_price=100.0,
    )

    # Mock _resolve_ticker to return a known resolution
    monkeypatch.setattr(
        "stockmon.web.routes.portfolio_tracker._resolve_ticker",
        lambda sym: {"symbol": f"{sym}.NS", "name": "Tata Consultancy Services Limited", "price": 3800.0, "found": True}
        if sym == "TCS" else {"symbol": sym, "name": "", "price": None, "found": False}
    )

    # 1. Update with only ticker (TCS) and no stock_name -> auto-resolves name
    res = client.put(f"/api/portfolio-tracker/holding/{h_id}", json={"symbol": "TCS"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert data["stock_name"] == "Tata Consultancy Services Limited"

    h = hold_repo.get_holding(h_id)
    assert h["symbol"] == "TCS"
    assert h["stock_name"] == "Tata Consultancy Services Limited"
    assert h["name_confirmed"] == 1


def test_api_update_holding_manual_name_confirmed(clean_tracker, monkeypatch):
    """Verify PUT /api/portfolio-tracker/holding/<id> allows manual stock_name when ticker lookup fails."""
    from stockmon.web import create_app
    app = create_app()
    client = app.test_client()

    h_id, _ = hold_repo.add_holding(
        portfolio_name="MADI",
        symbol="OLDTICKER",
        scheme_name="Old Name",
        invest_date="2024-01-01",
        quantity=10.0,
        avg_price=100.0,
    )

    # Unrecognized ticker returns found: False
    monkeypatch.setattr(
        "stockmon.web.routes.portfolio_tracker._resolve_ticker",
        lambda sym: {"symbol": sym, "name": "", "price": None, "found": False}
    )

    # Update with custom manual stock_name and confirmation
    res = client.put(
        f"/api/portfolio-tracker/holding/{h_id}",
        json={
            "symbol": "CUSTOMTICKER",
            "stock_name": "Custom Unlisted Company Name",
            "name_confirmed": True,
        }
    )
    assert res.status_code == 200
    h = hold_repo.get_holding(h_id)
    assert h["symbol"] == "CUSTOMTICKER"
    assert h["stock_name"] == "Custom Unlisted Company Name"
    assert h["name_confirmed"] == 1


def test_api_update_sold_with_ticker_resolution(clean_tracker, monkeypatch):
    """Verify PUT /api/portfolio-tracker/sold/<id> resolves stock_name automatically from ticker."""
    from stockmon.web import create_app
    app = create_app()
    client = app.test_client()

    h_id, _ = hold_repo.add_holding(
        portfolio_name="LOAN",
        symbol="OLDTICK",
        scheme_name="Old Stock",
        invest_date="2024-01-01",
        quantity=10.0,
        avg_price=100.0,
        person="MADI",
    )
    hold_repo.sell_holding(h_id, sell_date="2024-06-01", sell_price=120.0)
    sold_list = hold_repo.list_holdings("LOAN", "sold")
    assert len(sold_list) == 1
    sold_id = sold_list[0]["id"]

    monkeypatch.setattr(
        "stockmon.web.routes.portfolio_tracker._resolve_ticker",
        lambda sym: {"symbol": f"{sym}.NS", "name": "Infosys Limited", "price": 1500.0, "found": True}
        if sym == "INFY" else {"symbol": sym, "name": "", "price": None, "found": False}
    )

    res = client.put(
        f"/api/portfolio-tracker/sold/{sold_id}",
        json={
            "symbol": "INFY",
            "invest_date": "2024-01-01",
            "sell_date": "2024-06-01",
            "quantity": 10.0,
            "avg_price": 100.0,
            "sell_price": 120.0,
            "person": "MADI",
        }
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert data["stock_name"] == "Infosys Limited"

    h = hold_repo.get_holding(sold_id)
    assert h["symbol"] == "INFY"
    assert h["stock_name"] == "Infosys Limited"
    assert h["name_confirmed"] == 1


def test_api_lookup_ticker_route(clean_tracker, monkeypatch):
    """Verify GET /api/portfolio-tracker/lookup-ticker returns expected structure."""
    from stockmon.web import create_app
    app = create_app()
    client = app.test_client()

    monkeypatch.setattr(
        "stockmon.web.routes.portfolio_tracker._resolve_ticker",
        lambda sym: {"symbol": "RELIANCE.NS", "name": "Reliance Industries Limited", "price": 2900.0, "found": True}
        if sym == "RELIANCE" else {"symbol": sym, "name": "", "price": None, "found": False}
    )

    # Valid lookup
    res = client.get("/api/portfolio-tracker/lookup-ticker?symbol=RELIANCE")
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert data["found"] is True
    assert data["name"] == "Reliance Industries Limited"
    assert data["resolved_symbol"] == "RELIANCE.NS"

    # Unrecognized lookup
    res_invalid = client.get("/api/portfolio-tracker/lookup-ticker?symbol=UNKNOWN")
    assert res_invalid.status_code == 200
    data_inv = res_invalid.get_json()
    assert data_inv["ok"] is True
    assert data_inv["found"] is False
    assert data_inv["name"] == ""

