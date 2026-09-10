import pytest
from stockmon.backtester import evaluate_rule, _to_number, _parse_fraction_numerator


class TestFractionParsing:
    def test_parse_fraction_numerator_valid(self):
        assert _parse_fraction_numerator('6/8') == 6.0
        assert _parse_fraction_numerator('8/8') == 8.0
        assert _parse_fraction_numerator('0/8') == 0.0
        assert _parse_fraction_numerator('7/7') == 7.0

    def test_parse_fraction_numerator_invalid(self):
        assert _parse_fraction_numerator('abc') is None
        assert _parse_fraction_numerator('6') is None
        assert _parse_fraction_numerator('') is None
        assert _parse_fraction_numerator(None) is None
        assert _parse_fraction_numerator(42) is None

    def test_to_number_regular(self):
        assert _to_number(5) == 5.0
        assert _to_number(3.14) == 3.14
        assert _to_number('42') == 42.0

    def test_to_number_fraction(self):
        assert _to_number('6/8') == 6.0
        assert _to_number('7/7') == 7.0

    def test_to_number_invalid(self):
        assert _to_number(None) is None
        assert _to_number('abc') is None


class TestEvaluateRule:
    def test_numeric_greater(self):
        item = {'rsi_14': 65}
        assert evaluate_rule(item, {'field': 'rsi_14', 'op': '>=', 'value': 55}) is True
        assert evaluate_rule(item, {'field': 'rsi_14', 'op': '>=', 'value': 70}) is False

    def test_numeric_less(self):
        item = {'range_pct_5': 5.0}
        assert evaluate_rule(item, {'field': 'range_pct_5', 'op': '<=', 'value': 8.0}) is True
        assert evaluate_rule(item, {'field': 'range_pct_5', 'op': '<=', 'value': 3.0}) is False

    def test_string_equality(self):
        item = {'setup_strength': 'Strong'}
        assert evaluate_rule(item, {'field': 'setup_strength', 'op': '==', 'value': 'Strong'}) is True
        assert evaluate_rule(item, {'field': 'setup_strength', 'op': '==', 'value': 'Weak'}) is False

    def test_string_contains(self):
        item = {'setup': 'Price > SMA 20, MACD Bullish'}
        assert evaluate_rule(item, {'field': 'setup', 'op': 'contains', 'value': 'MACD'}) is True
        assert evaluate_rule(item, {'field': 'setup', 'op': 'contains', 'value': 'RSI'}) is False

    def test_fraction_comparison(self):
        item = {'confirmation_count': '7/8'}
        assert evaluate_rule(item, {'field': 'confirmation_count', 'op': '>=', 'value': 6}) is True
        assert evaluate_rule(item, {'field': 'confirmation_count', 'op': '>=', 'value': 8}) is False
        assert evaluate_rule(item, {'field': 'confirmation_count', 'op': '==', 'value': 7}) is True

    def test_fraction_different_denominators(self):
        assert evaluate_rule({'confirmation_count': '7/7'}, {'field': 'confirmation_count', 'op': '>=', 'value': 6}) is True
        assert evaluate_rule({'confirmation_count': '1/2'}, {'field': 'confirmation_count', 'op': '>=', 'value': 6}) is False

    def test_compare_field(self):
        item = {'close': 150.0, 'sma_20': 140.0, 'sma_50': 160.0}
        assert evaluate_rule(item, {'field': 'close', 'op': '>', 'compareField': 'sma_20'}) is True
        assert evaluate_rule(item, {'field': 'close', 'op': '>', 'compareField': 'sma_50'}) is False

    def test_between(self):
        item = {'rsi_14': 65}
        assert evaluate_rule(item, {'field': 'rsi_14', 'op': 'between', 'valueMin': 40, 'valueMax': 70}) is True
        assert evaluate_rule(item, {'field': 'rsi_14', 'op': 'between', 'valueMin': 70, 'valueMax': 80}) is False

    def test_array_contains(self):
        item = {'predictive_setups': ['silent_accumulation', 'vcp_breakout']}
        assert evaluate_rule(item, {'field': 'predictive_setups', 'op': 'contains', 'value': 'silent_accumulation'}) is True
        assert evaluate_rule(item, {'field': 'predictive_setups', 'op': 'contains', 'value': 'momentum_staircase'}) is False

    def test_missing_field_returns_false(self):
        item = {'close': 100}
        assert evaluate_rule(item, {'field': 'rsi_14', 'op': '>=', 'value': 50}) is False

    def test_none_item_returns_true(self):
        assert evaluate_rule(None, {'field': 'close', 'op': '>=', 'value': 50}) is True

    def test_empty_rule_returns_true(self):
        assert evaluate_rule({'close': 100}, {}) is True
        assert evaluate_rule({'close': 100}, None) is True

    def test_supertrend_dir_comparison(self):
        # supertrend_dir can be string or number
        assert evaluate_rule({'supertrend_dir': 1}, {'field': 'supertrend_dir', 'op': '==', 'value': 1}) is True
        assert evaluate_rule({'supertrend_dir': '1'}, {'field': 'supertrend_dir', 'op': '==', 'value': 1}) is True
        assert evaluate_rule({'supertrend_dir': 0}, {'field': 'supertrend_dir', 'op': '==', 'value': 1}) is False
