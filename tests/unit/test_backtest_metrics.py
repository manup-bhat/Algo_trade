"""tests/unit/test_backtest_metrics.py — backtest performance metrics (Phase 6)."""

from __future__ import annotations

from engine.backtest.metrics import compute_metrics


class TestComputeMetrics:
    def test_empty(self):
        m = compute_metrics([])
        assert m["num_trades"] == 0
        assert m["win_rate"] == 0.0
        assert m["profit_factor"] is None
        assert m["max_drawdown"] == 0.0

    def test_mixed_series(self):
        m = compute_metrics([100, -50, 200, -30, 0])
        assert m["num_trades"] == 5
        assert m["wins"] == 2
        assert m["losses"] == 2
        assert m["breakeven"] == 1
        assert m["net_pnl"] == 220
        assert m["gross_profit"] == 300
        assert m["gross_loss"] == 80
        assert m["profit_factor"] == round(300 / 80, 3)
        assert m["win_rate"] == 0.4
        assert m["expectancy"] == 44.0
        assert m["largest_win"] == 200
        assert m["largest_loss"] == -50

    def test_max_drawdown(self):
        # equity path 0→100→50→250→220→220: peak 100 then 250; worst dd = 100-50 = 50
        m = compute_metrics([100, -50, 200, -30, 0])
        assert m["max_drawdown"] == 50

    def test_all_wins_profit_factor_undefined(self):
        m = compute_metrics([10, 20, 30])
        assert m["profit_factor"] is None
        assert m["max_drawdown"] == 0.0
        assert m["win_rate"] == 1.0

    def test_all_losses(self):
        m = compute_metrics([-10, -20])
        assert m["profit_factor"] == 0.0
        assert m["net_pnl"] == -30
        assert m["max_drawdown"] == 30
