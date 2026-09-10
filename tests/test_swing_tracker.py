from datetime import datetime
from unittest.mock import patch

import pytest
from stockmon.db import get_connection
from stockmon.db.repositories import swing_tracker as repo
from stockmon.swing_tracker import (
    add_swing_trade,
    calculate_distance_pct,
    delete_swing_trade,
    load_swing_trades,
    parse_range_or_number,
    refresh_all_swing_trade_prices,
    refresh_swing_trade_price,
    resolve_ticker_price,
    update_swing_trade,
)


@pytest.fixture
def clean_swing_tracker(db_conn):
    """Ensure clean swing_tracker and swing_tracker_source tables before each test."""
    conn = get_connection()

    def _wipe():
        conn.execute("DELETE FROM swing_tracker")
        conn.execute("DELETE FROM swing_tracker_source")

    _wipe()
    yield conn
    _wipe()


def test_schema_tables_exist(db_conn):
    """Verify migration v5 created both swing_tracker and swing_tracker_source tables."""
    conn = get_connection()
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "swing_tracker" in tables
    assert "swing_tracker_source" in tables


def test_parse_range_or_number():
    # Single values
    assert parse_range_or_number("100") == (100.0, False, 100.0, 100.0)
    assert parse_range_or_number(250.5) == (250.5, False, 250.5, 250.5)
    assert parse_range_or_number("₹ 1,500.00") == (1500.0, False, 1500.0, 1500.0)

    # Ranges with hyphen, en-dash, em-dash, 'to'
    assert parse_range_or_number("100-105") == (102.5, True, 100.0, 105.0)
    assert parse_range_or_number("100 - 105") == (102.5, True, 100.0, 105.0)
    assert parse_range_or_number("105-100") == (102.5, True, 100.0, 105.0)
    assert parse_range_or_number("100 to 110") == (105.0, True, 100.0, 110.0)
    assert parse_range_or_number("₹ 1,000 – ₹ 1,100") == (1050.0, True, 1000.0, 1100.0)

    # Edge cases
    assert parse_range_or_number("") == (None, False, None, None)
    assert parse_range_or_number(None) == (None, False, None, None)
    assert parse_range_or_number("invalid text") == (None, False, None, None)


def test_calculate_distance_pct():
    # Single number target
    assert calculate_distance_pct(100.0, 110.0) == 10.0
    assert calculate_distance_pct(100.0, 95.0) == -5.0

    # Range target averaged
    # Range 100-110 has avg 105. Distance from 100 is +5%
    assert calculate_distance_pct(100.0, "100-110") == 5.0
    # Stop loss range 90-95 has avg 92.5. Distance from 100 is -7.5%
    assert calculate_distance_pct(100.0, "90-95") == -7.5

    # Edge cases: price is zero, negative, None, or string
    assert calculate_distance_pct(None, 100.0) is None
    assert calculate_distance_pct(0, 100.0) is None
    assert calculate_distance_pct(-10.0, 100.0) is None
    assert calculate_distance_pct(100.0, "") is None
    assert calculate_distance_pct(100.0, None) is None


def test_swing_trade_crud_lifecycle(clean_swing_tracker):
    # 1. Create
    trade = add_swing_trade({
        "symbol": "TATAMOTORS",
        "date": "2026-09-10",
        "current_price": 980.0,
        "buy_zone": "970-985",
        "stop_loss": "950",
        "target1": "1050",
        "target2": "1100-1120",
        "pattern_break": "Bull Flag Breakout",
        "thesis": "High delivery volume + retesting 20 EMA support.",
        "trade_source": "VIP Discord",
    })

    assert trade["id"] is not None
    assert trade["symbol"] == "TATAMOTORS.NS"  # normalized
    assert trade["current_price"] == 980.0
    assert trade["buy_zone"] == "970-985"
    assert trade["trade_source"] == "VIP Discord"

    # Verify source was automatically persisted
    sources = repo.list_sources()
    assert "VIP Discord" in sources

    # 2. Read
    fetched = repo.get_trade(trade["id"])
    assert fetched is not None
    assert fetched["symbol"] == "TATAMOTORS.NS"

    loaded = load_swing_trades()
    assert len(loaded["trades"]) == 1
    t = loaded["trades"][0]
    # Check enriched percentages
    # Buy zone avg = (970+985)/2 = 977.5 -> (977.5 - 980)/980 = -0.26%
    assert t["buy_zone_dist_pct"] == -0.26
    # Stop loss = 950 -> (950 - 980)/980 = -3.06%
    assert t["stop_loss_dist_pct"] == -3.06
    # Target 1 = 1050 -> (1050 - 980)/980 = +7.14%
    assert t["target1_dist_pct"] == 7.14
    # Target 2 avg = 1110 -> (1110 - 980)/980 = +13.27%
    assert t["target2_dist_pct"] == 13.27

    # 3. Update
    updated = update_swing_trade(trade["id"], {
        "target1": "1060",
        "current_price": 990.0,
        "thesis": "Updated thesis after earnings release.",
    })
    assert updated["target1"] == "1060"
    assert updated["current_price"] == 990.0
    assert updated["thesis"] == "Updated thesis after earnings release."

    # 4. Delete
    deleted = delete_swing_trade(trade["id"])
    assert deleted is True
    assert repo.get_trade(trade["id"]) is None
    assert len(load_swing_trades()["trades"]) == 0


def test_trade_source_persistence(clean_swing_tracker):
    # Add sources on the fly
    s1 = repo.add_source("Alpha Breakouts")
    assert s1 == "Alpha Breakouts"
    repo.add_source("Self Analysis")

    # Duplicate should be ignored cleanly
    repo.add_source("Alpha Breakouts")

    sources = repo.list_sources()
    assert "Alpha Breakouts" in sources
    assert "Self Analysis" in sources
    assert len([s for s in sources if s == "Alpha Breakouts"]) == 1


def test_thesis_formatting_preservation(clean_swing_tracker):
    multi_line_text = (
        "Line 1: Breakout confirmed on daily timeframe.\n\n"
        "Line 2: Target 1 at 200 EMA resistance.\n"
        "• Point A with bullet\n"
        "    Indented line with 4 spaces\n"
        "Special chars: ₹ & < > \" '"
    )

    trade = add_swing_trade({
        "symbol": "INFY",
        "date": "2026-09-10",
        "current_price": 1800.0,
        "thesis": multi_line_text,
    })

    fetched = repo.get_trade(trade["id"])
    assert fetched["thesis"] == multi_line_text


def test_price_reuse_from_portfolio(clean_swing_tracker):
    # Mock load_snapshot to return a portfolio with RELIANCE.NS at 2950.0
    mock_snapshot = {
        "portfolios": {
            "BAPA": {
                "rows": [
                    {"symbol": "RELIANCE.NS", "display": "RELIANCE", "price": 2950.0},
                    {"symbol": "TCS.NS", "display": "TCS", "price": 4200.0},
                ]
            },
            "MADI": {"rows": []},
        }
    }

    with patch("stockmon.swing_tracker.load_snapshot", return_value=mock_snapshot):
        with patch("stockmon.swing_tracker.fetch_ticker_quote") as mock_fetch:
            # RELIANCE exists in BAPA portfolio -> should reuse without fetching
            price, source = resolve_ticker_price("RELIANCE")
            assert price == 2950.0
            assert source == "portfolio"
            mock_fetch.assert_not_called()

            # INFY does NOT exist in portfolio -> should call fetch_ticker_quote
            mock_fetch.return_value = {"symbol": "INFY.NS", "price": 1825.50}
            price_infy, source_infy = resolve_ticker_price("INFY")
            assert price_infy == 1825.50
            assert source_infy == "live"
            mock_fetch.assert_called_once()


def test_refresh_single_and_all_prices(clean_swing_tracker):
    trade1 = add_swing_trade({
        "symbol": "SBIN",
        "date": "2026-09-10",
        "current_price": 750.0,
    })
    trade2 = add_swing_trade({
        "symbol": "ICICIBANK",
        "date": "2026-09-10",
        "current_price": 1100.0,
    })

    # Mock resolve_ticker_price to return updated prices
    def mock_resolve(sym):
        if "SBIN" in sym:
            return (770.0, "live")
        if "ICICI" in sym:
            return (1125.0, "live")
        return (None, "failed")

    with patch("stockmon.swing_tracker.resolve_ticker_price", side_effect=mock_resolve):
        # Single refresh
        refreshed1 = refresh_swing_trade_price(trade1["id"])
        assert refreshed1["current_price"] == 770.0

        # Batch refresh
        batch_stats = refresh_all_swing_trade_prices()
        assert batch_stats["total"] == 2
        assert batch_stats["updated"] == 2

        loaded = load_swing_trades()["trades"]
        prices = {t["symbol"]: t["current_price"] for t in loaded}
        assert prices["SBIN.NS"] == 770.0
        assert prices["ICICIBANK.NS"] == 1125.0


def test_flask_api_endpoints(clean_swing_tracker):
    from stockmon.web import create_app
    app = create_app()
    client = app.test_client()

    # 1. GET /api/swing-tracker (initially empty)
    res = client.get("/api/swing-tracker")
    assert res.status_code == 200
    json_data = res.get_json()
    assert json_data["ok"] is True
    assert json_data["trades"] == []
    assert "sources" in json_data

    # 2. POST /api/swing-tracker/sources
    res = client.post("/api/swing-tracker/sources", json={"name": "Twitter Alpha"})
    assert res.status_code == 200
    assert "Twitter Alpha" in res.get_json()["sources"]

    # 3. POST /api/swing-tracker
    res = client.post(
        "/api/swing-tracker",
        json={
            "symbol": "WIPRO",
            "date": "2026-09-10",
            "current_price": 450.0,
            "buy_zone": "440-455",
            "stop_loss": "430",
            "target1": "490",
            "target2": "520",
            "pattern_break": "Double Bottom",
            "thesis": "Reversal confirmed on daily chart.",
            "trade_source": "Twitter Alpha",
        },
    )
    assert res.status_code == 200
    trade_json = res.get_json()
    assert trade_json["ok"] is True
    assert trade_json["trade"]["symbol"] == "WIPRO.NS"
    trade_id = trade_json["trade"]["id"]

    # 4. PUT /api/swing-tracker/<id>
    res = client.put(
        f"/api/swing-tracker/{trade_id}",
        json={"target1": "500", "current_price": 455.0},
    )
    assert res.status_code == 200
    updated_json = res.get_json()
    assert updated_json["ok"] is True
    assert updated_json["trade"]["target1"] == "500"

    # 5. GET /api/swing-tracker/lookup-ticker
    with patch("stockmon.swing_tracker.check_portfolio_table_price", return_value=455.0):
        res = client.get("/api/swing-tracker/lookup-ticker?symbol=WIPRO")
        assert res.status_code == 200
        data = res.get_json()
        assert data["ok"] is True
        assert data["symbol"] == "WIPRO.NS"
        assert data["price"] == 455.0
        assert data["source"] == "portfolio"

    # 6. DELETE /api/swing-tracker/<id>
    res = client.delete(f"/api/swing-tracker/{trade_id}")
    assert res.status_code == 200
    assert res.get_json()["ok"] is True
    assert len(res.get_json()["trades"]) == 0

