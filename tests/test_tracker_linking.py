"""Tests for linking the Tracker tab to the Portfolio Tracker tab.

Verifies:
- Ticker sourcing from Portfolio Tracker (Personal + Loan matching person).
- Exclusion of Loan entries belonging to other persons.
- Deduplication and combined weighted Avg Price across Personal and Loan tables.
- Pure manual tickers with avg_price = None.
- Sourced ticker deletion protection.
- Immediate removal of sold positions when sold completely.
- Retention of position when sold partially.
- Shared quote cache population and LTP reuse.
"""

from unittest.mock import patch
import pytest

from stockmon.db.repositories import holdings as hold_repo
from stockmon.db.repositories import portfolios as port_repo
from stockmon.db.repositories import quotes as quote_repo
from stockmon.errors import ValidationError
from stockmon.portfolio import (
    add_ticker,
    load_portfolios,
    load_tracker_portfolios_meta,
    remove_ticker,
)
from stockmon.service import build_row, empty_snapshot, refresh_portfolios


@pytest.fixture(autouse=True)
def clean_all(clean_tracker):
    """Ensure both Portfolio Tracker tables and portfolio_ticker are wiped."""
    clean_tracker.execute("DELETE FROM portfolio_ticker")
    clean_tracker.execute("DELETE FROM pending_addition")
    clean_tracker.execute("DELETE FROM quote_cache")
    clean_tracker.execute("DELETE FROM tracker_snapshot")
    yield clean_tracker
    clean_tracker.execute("DELETE FROM portfolio_ticker")
    clean_tracker.execute("DELETE FROM pending_addition")
    clean_tracker.execute("DELETE FROM quote_cache")
    clean_tracker.execute("DELETE FROM tracker_snapshot")


class TestTrackerLinking:
    def test_madi_and_bapa_ticker_sourcing(self):
        """Madi gets Madi personal + Loan (person='MADI').

        Bapa gets Bapa personal + Loan (person='BAPA').
        Loan entries with other persons are excluded.
        """
        # Add Madi personal holding
        hold_repo.add_holding(
            portfolio_name="MADI",
            symbol="INFY.NS",
            stock_name="Infosys Ltd",
            quantity=10,
            avg_price=1500.0,
        )
        # Add Madi loan holding
        hold_repo.add_holding(
            portfolio_name="LOAN",
            symbol="TCS.NS",
            stock_name="Tata Consultancy Services",
            person="MADI",
            quantity=5,
            avg_price=3500.0,
        )
        # Add Bapa personal holding
        hold_repo.add_holding(
            portfolio_name="BAPA",
            symbol="RELIANCE.NS",
            stock_name="Reliance Industries",
            quantity=20,
            avg_price=2800.0,
        )
        # Add Bapa loan holding
        hold_repo.add_holding(
            portfolio_name="LOAN",
            symbol="HDFCBANK.NS",
            stock_name="HDFC Bank",
            person="BAPA",
            quantity=15,
            avg_price=1600.0,
        )
        # Add an unassociated loan holding (person='OTHER')
        hold_repo.add_holding(
            portfolio_name="LOAN",
            symbol="SBIN.NS",
            stock_name="State Bank of India",
            person="OTHER",
            quantity=50,
            avg_price=600.0,
        )

        ports = load_portfolios()
        assert "INFY.NS" in ports["MADI"]
        assert "TCS.NS" in ports["MADI"]
        assert "SBIN.NS" not in ports["MADI"]
        assert "RELIANCE.NS" not in ports["MADI"]

        assert "RELIANCE.NS" in ports["BAPA"]
        assert "HDFCBANK.NS" in ports["BAPA"]
        assert "SBIN.NS" not in ports["BAPA"]
        assert "INFY.NS" not in ports["BAPA"]

    def test_weighted_avg_price_deduplication(self):
        """When a ticker is in both Personal and Loan for the same person,

        a single merged row is returned with combined weighted average price.
        """
        # Madi personal: 10 shares @ 1000 = 10,000
        hold_repo.add_holding(
            portfolio_name="MADI",
            symbol="ITC.NS",
            stock_name="ITC Limited",
            quantity=10,
            avg_price=1000.0,
        )
        # Madi loan: 5 shares @ 1300 = 6,500
        # Total = 16,500 / 15 = 1100.0
        hold_repo.add_holding(
            portfolio_name="LOAN",
            symbol="ITC.NS",
            stock_name="ITC Limited",
            person="MADI",
            quantity=5,
            avg_price=1300.0,
        )

        meta = load_tracker_portfolios_meta(("MADI",))["MADI"]
        assert "ITC.NS" in meta
        itc = meta["ITC.NS"]
        assert itc["is_sourced"] is True
        assert itc["total_qty"] == 15.0
        assert itc["avg_price"] == 1100.0

    def test_manual_ticker_alongside_sourced_ticker(self):
        """A manually added ticker has avg_price=None and is_sourced=False."""
        # Add a sourced ticker to MADI
        hold_repo.add_holding(
            portfolio_name="MADI",
            symbol="INFY.NS",
            stock_name="Infosys",
            quantity=10,
            avg_price=1500.0,
        )
        # Add a manual ticker to MADI
        add_ticker("MADI", "WIPRO.NS")

        meta = load_tracker_portfolios_meta(("MADI",))["MADI"]
        assert meta["INFY.NS"]["is_sourced"] is True
        assert meta["INFY.NS"]["is_manual"] is False
        assert meta["INFY.NS"]["avg_price"] == 1500.0

        assert meta["WIPRO.NS"]["is_sourced"] is False
        assert meta["WIPRO.NS"]["is_manual"] is True
        assert meta["WIPRO.NS"]["avg_price"] is None

    def test_sourced_ticker_deletion_protection(self):
        """Purely sourced tickers cannot be removed via remove_ticker."""
        hold_repo.add_holding(
            portfolio_name="MADI",
            symbol="INFY.NS",
            stock_name="Infosys",
            quantity=10,
            avg_price=1500.0,
        )

        with pytest.raises(ValidationError, match="managed by Portfolio Tracker"):
            remove_ticker("MADI", "INFY.NS")

        # Now add manual entry for INFY.NS as well
        port_repo.add_ticker("MADI", "INFY.NS")
        meta = load_tracker_portfolios_meta(("MADI",))["MADI"]["INFY.NS"]
        assert meta["is_sourced"] is True
        assert meta["is_manual"] is True

        # Removing it now succeeds (strips manual flag)
        remove_ticker("MADI", "INFY.NS")
        updated = load_tracker_portfolios_meta(("MADI",))["MADI"]["INFY.NS"]
        assert updated["is_sourced"] is True
        assert updated["is_manual"] is False

    def test_sold_position_lifecycle(self):
        """Selling an open holding completely removes it from Tracker tab;

        partial sell retains it with updated weighted average price.
        """
        hid, _ = hold_repo.add_holding(
            portfolio_name="MADI",
            symbol="TATAMOTORS.NS",
            stock_name="Tata Motors",
            quantity=20,
            avg_price=900.0,
        )

        meta = load_tracker_portfolios_meta(("MADI",))["MADI"]
        assert "TATAMOTORS.NS" in meta
        assert meta["TATAMOTORS.NS"]["total_qty"] == 20.0

        # Partial sell: 10 shares sold @ 1000
        hold_repo.sell_holding(
            holding_id=hid,
            sell_date="2026-09-08",
            sell_price=1000.0,
            quantity=10,
        )

        meta_partial = load_tracker_portfolios_meta(("MADI",))["MADI"]
        assert "TATAMOTORS.NS" in meta_partial
        assert meta_partial["TATAMOTORS.NS"]["total_qty"] == 10.0

        # Sell the remaining 10 shares
        hold_repo.sell_holding(
            holding_id=hid,
            sell_date="2026-09-08",
            sell_price=1050.0,
            quantity=10,
        )

        meta_sold = load_tracker_portfolios_meta(("MADI",))["MADI"]
        assert "TATAMOTORS.NS" not in meta_sold

    @patch("stockmon.service.get_ticker_data")
    def test_shared_price_fetch_and_quote_cache_reuse(self, mock_get_data):
        """refresh_portfolios stores fetched price in quote_cache, and

        Portfolio Tracker API can immediately reuse it.
        """
        from stockmon.data_fetcher import TickerData
        import pandas as pd

        # Create mock TickerData
        df = pd.DataFrame(
            {"Close": [100.0, 105.0, 110.0, 115.0]},
            index=pd.date_range("2026-01-01", periods=4, freq="D"),
        )
        mock_get_data.return_value = TickerData(
            symbol="INFY.NS",
            name="Infosys Limited",
            price=1575.50,
            currency="INR",
            as_of="2026-09-08",
            daily=df,
            weekly=pd.DataFrame(),
        )

        # Add holding to Portfolio Tracker
        hold_repo.add_holding(
            portfolio_name="MADI",
            symbol="INFY.NS",
            stock_name="Infosys Limited",
            quantity=10,
            avg_price=1500.0,
        )

        # Run refresh_portfolios
        snapshot = refresh_portfolios(source="test", publish=False)

        # 1. Check Tracker snapshot contains avg_price and price
        madi_rows = snapshot["portfolios"]["MADI"]["rows"]
        assert len(madi_rows) == 1
        infy_row = madi_rows[0]
        assert infy_row["symbol"] == "INFY.NS"
        assert infy_row["price"] == 1575.50
        assert infy_row["avg_price"] == 1500.0
        assert infy_row["is_sourced"] is True

        # 2. Check quote_cache table was populated with the fetched price
        cached_quote = quote_repo.get_quote("INFY.NS")
        assert cached_quote is not None
        assert cached_quote["price"] == 1575.50

        # Bare symbol should also be in cache for fast lookup
        bare_cached = quote_repo.get_quote("INFY")
        assert bare_cached is not None
        assert bare_cached["price"] == 1575.50

    @patch("stockmon.data_fetcher.fetch_daily_history")
    @patch("stockmon.data_fetcher.fetch_live_price")
    def test_alternate_exchange_fallback_on_primary_failure(self, mock_live_price, mock_daily):
        """When .NS fails with DataFetchError, it automatically falls back to .BO."""
        from stockmon.data_fetcher import get_ticker_data, fetch_ticker_quote
        from stockmon.errors import DataFetchError
        import pandas as pd

        df_bo = pd.DataFrame(
            {"Close": [50.0, 52.0, 55.0]},
            index=pd.date_range("2026-01-01", periods=3, freq="D"),
        )

        def mock_fetch(sym, **kwargs):
            if sym.endswith(".NS"):
                raise DataFetchError(sym, "no price rows returned (delisted?)")
            return df_bo

        def mock_price(sym):
            if sym.endswith(".NS"):
                return None, None, ""
            return 55.0, "INR", "Simplex Castings"

        mock_daily.side_effect = mock_fetch
        mock_live_price.side_effect = mock_price

        # Call get_ticker_data for .NS
        data = get_ticker_data("SIMPLEXCAS.NS")
        assert data.symbol == "SIMPLEXCAS.NS"
        assert data.fetch_symbol == "SIMPLEXCAS.BO"
        assert data.price == 55.0
        assert any("using SIMPLEXCAS.BO data" in n for n in data.notes)

        # Call fetch_ticker_quote for .NS
        quote = fetch_ticker_quote("SIMPLEXCAS.NS")
        assert quote["symbol"] == "SIMPLEXCAS.BO"
        assert quote["price"] == 55.0

    def test_error_stocks_sorted_at_end_of_table(self):
        """Rows with fetch errors or missing prices must sort after all normal rows."""
        from stockmon.service import _ema_sort_key

        # Normal row below 200 EMA (priority 0)
        row_200 = {
            "symbol": "AAA.NS",
            "display": "AAA",
            "price": 100.0,
            "error": None,
            "emas": {"200": {"daily": {"below": True}}},
        }

        # Normal row above all EMAs (priority 5)
        row_healthy = {
            "symbol": "BBB.NS",
            "display": "BBB",
            "price": 200.0,
            "error": None,
            "emas": {str(p): {"daily": {"below": False}} for p in [9, 21, 50, 100, 200]},
        }

        # Error row (priority 6)
        row_error = {
            "symbol": "CCC.NS",
            "display": "CCC",
            "price": None,
            "error": "delisted",
            "emas": {},
        }

        # Row with missing price (priority 6)
        row_no_price = {
            "symbol": "DDD.NS",
            "display": "DDD",
            "price": None,
            "error": None,
            "emas": {},
        }

        rows = [row_error, row_healthy, row_no_price, row_200]
        rows.sort(key=_ema_sort_key)

        assert rows[0]["symbol"] == "AAA.NS"       # Priority 0
        assert rows[1]["symbol"] == "BBB.NS"       # Priority 5
        assert rows[2]["symbol"] == "CCC.NS"       # Priority 6 (alpha C)
        assert rows[3]["symbol"] == "DDD.NS"       # Priority 6 (alpha D)


class TestCostBasisRiskIndicator:
    """Test cost-basis drawdown percentage calculation and risk tiers."""

    def test_compute_cost_risk_tiers(self):
        from stockmon.service import compute_cost_risk

        # In profit
        pct, tier = compute_cost_risk(price=110.0, avg_price=100.0)
        assert pct == 10.0
        assert tier is None

        # Break-even
        pct, tier = compute_cost_risk(price=100.0, avg_price=100.0)
        assert pct == 0.0
        assert tier is None

        # Tier 1: Mild / Watch (0.01% to 4.99% below cost)
        pct, tier = compute_cost_risk(price=98.0, avg_price=100.0)
        assert pct == -2.0
        assert tier == "mild"

        pct, tier = compute_cost_risk(price=95.01, avg_price=100.0)
        assert pct == -4.99
        assert tier == "mild"

        # Tier 2: Stop-Loss Zone (-5.00% to -9.99%)
        pct, tier = compute_cost_risk(price=95.0, avg_price=100.0)
        assert pct == -5.0
        assert tier == "moderate"

        pct, tier = compute_cost_risk(price=93.0, avg_price=100.0)
        assert pct == -7.0
        assert tier == "moderate"

        pct, tier = compute_cost_risk(price=90.01, avg_price=100.0)
        assert pct == -9.99
        assert tier == "moderate"

        # Tier 3: Critical (<= -10.00%)
        pct, tier = compute_cost_risk(price=90.0, avg_price=100.0)
        assert pct == -10.0
        assert tier == "critical"

        pct, tier = compute_cost_risk(price=82.5, avg_price=100.0)
        assert pct == -17.5
        assert tier == "critical"

    def test_compute_cost_risk_edge_cases(self):
        from stockmon.service import compute_cost_risk

        # None / missing price or avg_price
        assert compute_cost_risk(price=None, avg_price=100.0) == (None, None)
        assert compute_cost_risk(price=100.0, avg_price=None) == (None, None)
        assert compute_cost_risk(price=None, avg_price=None) == (None, None)

        # Zero or negative avg_price (bonus shares / invalid input)
        assert compute_cost_risk(price=50.0, avg_price=0.0) == (None, None)
        assert compute_cost_risk(price=50.0, avg_price=-10.0) == (None, None)

    @patch("stockmon.service.get_ticker_data")
    def test_refresh_portfolios_populates_cost_risk(self, mock_get_ticker, clean_all):
        """refresh_portfolios must populate cost_drawdown_pct and risk_tier for sourced tickers."""
        from stockmon.data_fetcher import TickerData
        import pandas as pd

        # Add a holding in Portfolio Tracker for MADI
        hold_repo.add_holding(
            portfolio_name="MADI",
            symbol="INFY.NS",
            stock_name="Infosys Ltd",
            quantity=10,
            avg_price=1000.0,
        )

        # Mock ticker data with price at 940 (-6% drop -> moderate / stop-loss zone)
        mock_get_ticker.return_value = TickerData(
            symbol="INFY.NS",
            price=940.0,
            currency="INR",
            name="Infosys Ltd",
            as_of="2026-09-09",
            daily=pd.DataFrame({"Close": [940.0] * 250}),
            weekly=pd.DataFrame({"Close": [940.0] * 50}),
        )

        snapshot = refresh_portfolios(source="test", publish=False)
        madi_rows = snapshot["portfolios"]["MADI"]["rows"]
        assert len(madi_rows) == 1
        row = madi_rows[0]
        assert row["symbol"] == "INFY.NS"
        assert row["avg_price"] == 1000.0
        assert row["price"] == 940.0
        assert row["cost_drawdown_pct"] == -6.0
        assert row["risk_tier"] == "moderate"


