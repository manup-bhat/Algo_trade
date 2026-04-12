"""
tests/unit/test_position_sizer.py — Position sizer unit tests (spec §16.1).

Spec test cases:
  - capital=100000, risk=1%, entry=500, sl=460 → qty = floor(1000/40) = 25
  - risk_per_share=0 → returns 0 (zero division guard)
  - risk_per_share < MIN_RISK_PER_SHARE → returns 0
  - capital=0 → returns 0
"""

from __future__ import annotations

import pytest

from engine.risk.position_sizer import compute


class TestPositionSizer:
    def test_standard_case(self):
        """Spec §16.1: capital=100000, risk=1%, entry=500, sl=460 → qty=25."""
        qty = compute(capital=100_000, limit_price=500.0, stop_loss=460.0)
        # risk_amount = 100_000 × 1% = 1_000
        # risk_per_share = 500 - 460 = 40
        # quantity = floor(1_000 / 40) = 25
        assert qty == 25

    def test_minimum_quantity_is_1(self):
        """Even with large risk_per_share, minimum quantity is 1."""
        # capital=1000, risk=1% → risk_amount=10
        # risk_per_share=500 → qty=floor(10/500)=0 → floor to max(1,0)=1
        qty = compute(capital=1_000, limit_price=600.0, stop_loss=100.0)
        assert qty == 1

    def test_zero_capital_returns_zero(self):
        """Spec §16.1: capital=0 → returns 0."""
        qty = compute(capital=0, limit_price=500.0, stop_loss=460.0)
        assert qty == 0

    def test_negative_capital_returns_zero(self):
        qty = compute(capital=-1000, limit_price=500.0, stop_loss=460.0)
        assert qty == 0

    def test_zero_risk_per_share_returns_zero(self):
        """Spec §16.1: risk_per_share=0 → returns 0 (zero division guard)."""
        qty = compute(capital=100_000, limit_price=500.0, stop_loss=500.0)
        assert qty == 0

    def test_negative_risk_per_share_returns_zero(self):
        """SL above entry price → invalid, returns 0."""
        qty = compute(capital=100_000, limit_price=500.0, stop_loss=510.0)
        assert qty == 0

    def test_below_min_risk_per_share_returns_zero(self):
        """Spec §16.1: risk_per_share < MIN_RISK_PER_SHARE_INR → returns 0."""
        # MIN_RISK_PER_SHARE_INR = 5.0
        # risk_per_share = 500.01 - 500.00 = 0.01 < 5
        qty = compute(capital=100_000, limit_price=500.01, stop_loss=500.00)
        assert qty == 0

    def test_exactly_at_min_risk_per_share_passes(self):
        """risk_per_share = MIN_RISK_PER_SHARE_INR exactly → NOT 0."""
        # MIN_RISK_PER_SHARE_INR = 5.0
        qty = compute(capital=100_000, limit_price=500.0, stop_loss=495.0)
        # risk_per_share = 5.0 (exactly at minimum — should pass)
        assert qty > 0

    def test_large_capital_scales_correctly(self):
        """With ₹10L capital, risk=1% → ₹10,000 risk."""
        qty = compute(capital=10_00_000, limit_price=500.0, stop_loss=460.0)
        # risk_amount = 10_000
        # risk_per_share = 40
        # qty = 250
        assert qty == 250

    def test_quantity_is_integer(self):
        """Return value is always an integer."""
        qty = compute(capital=100_000, limit_price=500.0, stop_loss=460.0)
        assert isinstance(qty, int)

    def test_fractional_rps_floors_correctly(self):
        """Fractional quantity is floored (not rounded)."""
        # capital=100_000, risk=1% → risk_amount=1_000
        # entry=500, sl=457 → rps=43
        # qty = floor(1000/43) = floor(23.255) = 23
        qty = compute(capital=100_000, limit_price=500.0, stop_loss=457.0)
        assert qty == 23
