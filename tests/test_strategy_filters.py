import pytest
from stockmon.backtester import evaluate_rule


def _make_stock(**overrides):
    """Create a mock stock with defaults."""
    base = {
        'symbol': 'TESTSTOCK',
        'close': 100.0, 'open': 98.0, 'high': 102.0, 'low': 97.0,
        'prev_close': 99.0, 'pct_change': 1.0, 'volume': 1000000,
        'delivery_percent': 40.0, 'delivery_qty': 400000,
        'supertrend_dir': 1, 'sma_20': 95.0, 'sma_50': 90.0,
        'close_near_high_pct': 80.0, 'volume_ratio_20': 1.5,
        'range_pct_5': 5.0, 'rsi_14': 60.0,
        'confirmation_count': '6/8',
        'setup_strength': 'Strong',
        'trend_direction': 'Bullish',
        'trend_strength': 'Strong',
        'signal': 'Bullish',
    }
    base.update(overrides)
    return base


def _all_rules_pass(item, rules):
    return all(evaluate_rule(item, r) for r in rules)


class TestMomentumMasters:
    RULES = [
        {'field': 'confirmation_count', 'op': '>=', 'value': 7},
        {'field': 'trend_direction', 'op': '==', 'value': 'Bullish'},
        {'field': 'trend_strength', 'op': '==', 'value': 'Strong'},
        {'field': 'volume_ratio_20', 'op': '>=', 'value': 1.5},
        {'field': 'close_near_high_pct', 'op': '>=', 'value': 75},
        {'field': 'supertrend_dir', 'op': '==', 'value': 1},
    ]

    def test_perfect_match(self):
        stock = _make_stock(confirmation_count='8/8', volume_ratio_20=2.0, close_near_high_pct=90)
        assert _all_rules_pass(stock, self.RULES) is True

    def test_low_confirmations_fails(self):
        stock = _make_stock(confirmation_count='5/8')
        assert _all_rules_pass(stock, self.RULES) is False

    def test_bearish_trend_fails(self):
        stock = _make_stock(confirmation_count='8/8', trend_direction='Bearish')
        assert _all_rules_pass(stock, self.RULES) is False

    def test_low_volume_fails(self):
        stock = _make_stock(confirmation_count='8/8', volume_ratio_20=0.5)
        assert _all_rules_pass(stock, self.RULES) is False


class TestQuickRocketing:
    RULES = [
        {'field': 'pct_change', 'op': '>=', 'value': 3.0},
        {'field': 'volume_ratio_20', 'op': '>=', 'value': 2.0},
        {'field': 'delivery_percent', 'op': '>=', 'value': 35},
        {'field': 'supertrend_dir', 'op': '==', 'value': 1},
        {'field': 'rsi_14', 'op': '>=', 'value': 55},
        {'field': 'rsi_14', 'op': '<=', 'value': 80},
    ]

    def test_perfect_match(self):
        stock = _make_stock(pct_change=4.0, volume_ratio_20=2.5, delivery_percent=50, rsi_14=65)
        assert _all_rules_pass(stock, self.RULES) is True

    def test_overbought_rsi_fails(self):
        stock = _make_stock(pct_change=4.0, volume_ratio_20=2.5, delivery_percent=50, rsi_14=85)
        assert _all_rules_pass(stock, self.RULES) is False

    def test_low_pct_change_fails(self):
        stock = _make_stock(pct_change=1.0, volume_ratio_20=2.5, delivery_percent=50, rsi_14=65)
        assert _all_rules_pass(stock, self.RULES) is False
