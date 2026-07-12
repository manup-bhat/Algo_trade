"""
tests/unit/test_position_sizer_lots.py — compute_lots (F&O lot-based sizing, Phase 4).

RISK_PER_TRADE_PCT defaults to 1.0, so risk_amount = capital * 0.01.
"""

from __future__ import annotations

from engine.risk.position_sizer import compute_lots


class TestComputeLots:
    def test_basic_lot_rounding(self):
        # 5L * 1% = 5000 risk; risk/unit = 36; 5000/36 = 138 units; //75 = 1 lot
        assert compute_lots(500000, 120, 84, 75) == 75

    def test_exposure_cap_not_binding(self):
        # risk/unit=12 → 5000/12=416 units → 5 lots (375); exposure 10% allows 16 → 375
        assert compute_lots(500000, 40, 28, 75, max_premium_exposure_pct=10) == 375

    def test_max_lots_cap(self):
        assert compute_lots(500000, 40, 28, 75, max_lots=2) == 150

    def test_exposure_cap_binds(self):
        # 1 lot by risk, but exposure 0.1% → max_cost 500 < 1 lot premium (9000) → 0
        assert compute_lots(500000, 120, 84, 75, max_premium_exposure_pct=0.1) == 0

    def test_cannot_fund_one_lot_returns_zero(self):
        # tiny capital: 1000*1% = 10 risk; risk/unit 400 → 0.025 units → 0 lots
        assert compute_lots(1000, 500, 100, 75) == 0

    def test_invalid_inputs_return_zero(self):
        assert compute_lots(0, 120, 84, 75) == 0
        assert compute_lots(500000, 120, 120, 75) == 0   # risk_per_unit <= 0
        assert compute_lots(500000, 120, 130, 75) == 0   # stop above entry
        assert compute_lots(500000, 120, 84, 0) == 0     # invalid lot size

    def test_risk_pct_override(self):
        # 2% → 10000 risk; /36 = 277 units → 3 lots (225)
        assert compute_lots(500000, 120, 84, 75, risk_pct=2.0) == 225
