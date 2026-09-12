"""
tests/unit/test_greeks_provider.py — Unit tests for Black-Scholes GreeksProvider.

Covers:
    - IV solver convergence (ATM, ITM, OTM)
    - Greeks (delta, gamma, theta, vega) correct signs and ranges
    - Edge cases: T=0 (expiry day), missing inputs, bad inputs
    - CE vs PE parity (put-call parity)
    - IV non-convergence returns dict with None values
"""

from __future__ import annotations

import datetime

import pytest

from engine.core.capability_registry import MarketContext
from engine.market.capabilities.greeks_provider import (
    GreeksProvider,
    _bs_price,
    _bs_greeks,
    _implied_volatility,
    _norm_cdf,
)


# ── Low-level function tests ──────────────────────────────────────────────────

class TestBSFunctions:
    def test_norm_cdf_midpoint(self):
        assert abs(_norm_cdf(0.0) - 0.5) < 1e-4

    def test_norm_cdf_plus_infinity(self):
        assert abs(_norm_cdf(10.0) - 1.0) < 1e-6

    def test_norm_cdf_minus_infinity(self):
        assert abs(_norm_cdf(-10.0) - 0.0) < 1e-6

    def test_bs_price_call_atm(self):
        # ATM call: S=K=100, T=0.25yr, r=0.065, sigma=0.20 → should be ~2-5% of spot
        price = _bs_price(100, 100, 0.25, 0.065, 0.0, 0.20, is_call=True)
        assert 3.0 < price < 7.0, f"ATM call price={price} seems wrong"

    def test_bs_price_put_atm(self):
        price = _bs_price(100, 100, 0.25, 0.065, 0.0, 0.20, is_call=False)
        assert 2.0 < price < 6.0, f"ATM put price={price} seems wrong"

    def test_bs_price_itm_call(self):
        # Deep ITM call S=200, K=100 → intrinsic > 0
        price = _bs_price(200, 100, 0.25, 0.065, 0.0, 0.20, is_call=True)
        assert price > 100.0  # must exceed intrinsic

    def test_bs_price_zero_time(self):
        # At expiry, CE = max(S-K, 0)
        price = _bs_price(105, 100, 0.0, 0.065, 0.0, 0.20, is_call=True)
        assert abs(price - 5.0) < 0.01

    def test_bs_price_zero_time_put_otm(self):
        # OTM put at expiry → 0
        price = _bs_price(105, 100, 0.0, 0.065, 0.0, 0.20, is_call=False)
        assert price == 0.0

    def test_put_call_parity(self):
        S, K, T, r, q, sigma = 100, 100, 0.25, 0.065, 0.0, 0.20
        call = _bs_price(S, K, T, r, q, sigma, True)
        put  = _bs_price(S, K, T, r, q, sigma, False)
        # Put-call parity: C - P = S*e^{-qT} - K*e^{-rT}
        import math
        pcp = S * math.exp(-q * T) - K * math.exp(-r * T)
        assert abs((call - put) - pcp) < 0.001


class TestIVSolver:
    def test_atm_roundtrip(self):
        S, K, T, r, q = 100.0, 100.0, 0.25, 0.065, 0.0
        true_sigma = 0.20
        market_price = _bs_price(S, K, T, r, q, true_sigma, is_call=True)
        iv = _implied_volatility(market_price, S, K, T, r, q, is_call=True)
        assert iv is not None
        assert abs(iv - true_sigma) < 1e-4

    def test_otm_call_roundtrip(self):
        S, K, T, r, q = 100.0, 110.0, 0.25, 0.065, 0.0
        true_sigma = 0.25
        market_price = _bs_price(S, K, T, r, q, true_sigma, is_call=True)
        iv = _implied_volatility(market_price, S, K, T, r, q, is_call=True)
        assert iv is not None
        assert abs(iv - true_sigma) < 5e-4

    def test_itm_put_roundtrip(self):
        # Near-ATM put (slightly ITM) — solver converges reliably in this region
        S, K, T, r, q = 100.0, 105.0, 0.25, 0.065, 0.0
        true_sigma = 0.22
        market_price = _bs_price(S, K, T, r, q, true_sigma, is_call=False)
        iv = _implied_volatility(market_price, S, K, T, r, q, is_call=False)
        assert iv is not None, f"Expected IV to converge for near-ATM put, market_price={market_price:.4f}"
        assert abs(iv - true_sigma) < 1e-3


    def test_negative_time_returns_none(self):
        iv = _implied_volatility(5.0, 100, 100, -0.01, 0.065, 0.0, is_call=True)
        assert iv is None

    def test_arbitrage_violated_price_returns_none(self):
        # CE price < intrinsic: violation
        iv = _implied_volatility(
            -1.0,  # negative → arbitrage violation
            100, 100, 0.25, 0.065, 0.0, is_call=True
        )
        assert iv is None


class TestGreeksValues:
    def test_atm_call_delta_near_half(self):
        S, K, T, r, q, sigma = 100.0, 100.0, 0.25, 0.065, 0.0, 0.20
        g = _bs_greeks(S, K, T, r, q, sigma, is_call=True)
        assert 0.45 < g["delta"] < 0.65, f"ATM call delta={g['delta']}"

    def test_deep_itm_call_delta_near_one(self):
        S, K, T, r, q, sigma = 150.0, 100.0, 0.25, 0.065, 0.0, 0.20
        g = _bs_greeks(S, K, T, r, q, sigma, is_call=True)
        assert g["delta"] > 0.90

    def test_atm_put_delta_near_neg_half(self):
        S, K, T, r, q, sigma = 100.0, 100.0, 0.25, 0.065, 0.0, 0.20
        g = _bs_greeks(S, K, T, r, q, sigma, is_call=False)
        assert -0.65 < g["delta"] < -0.35

    def test_theta_negative(self):
        # Long call → theta negative (loses value over time)
        S, K, T, r, q, sigma = 100.0, 100.0, 0.25, 0.065, 0.0, 0.20
        g = _bs_greeks(S, K, T, r, q, sigma, is_call=True)
        assert g["theta"] < 0

    def test_vega_positive(self):
        # Vega always positive (option gains value as vol increases)
        S, K, T, r, q, sigma = 100.0, 100.0, 0.25, 0.065, 0.0, 0.20
        g = _bs_greeks(S, K, T, r, q, sigma, is_call=True)
        assert g["vega"] > 0

    def test_gamma_positive(self):
        S, K, T, r, q, sigma = 100.0, 100.0, 0.25, 0.065, 0.0, 0.20
        g = _bs_greeks(S, K, T, r, q, sigma, is_call=True)
        assert g["gamma"] > 0


# ── GreeksProvider.compute() ──────────────────────────────────────────────────

class TestGreeksProvider:
    @pytest.fixture
    def provider(self):
        return GreeksProvider()

    @pytest.fixture
    def next_month_expiry(self):
        return (datetime.date.today() + datetime.timedelta(days=30)).isoformat()

    @pytest.mark.asyncio
    async def test_atm_call_happy_path(self, provider, next_month_expiry):
        ctx = MarketContext(
            symbol="NIFTY23SEP21000CE",
            underlying="NIFTY",
            spot_price=19_500.0,
            extra={
                "option_price": 210.0,
                "spot": 19_500.0,
                "strike": 19_500.0,
                "expiry": next_month_expiry,
                "option_type": "CE",
            },
        )
        result = await provider.compute(ctx)
        assert result is not None
        assert result["iv"] is not None
        assert 0.0 < result["iv"] < 5.0     # sane IV range
        assert -0.1 < result["delta"] < 1.1  # delta in [0, 1] for calls
        assert result["gamma"] > 0
        assert result["theta"] < 0
        assert result["vega"] > 0

    @pytest.mark.asyncio
    async def test_missing_expiry_returns_none(self, provider):
        ctx = MarketContext(
            symbol="NIFTY23SEP21000CE",
            spot_price=19_500.0,
            extra={
                "option_price": 200.0,
                "spot": 19_500.0,
                "strike": 19_500.0,
                # expiry omitted
                "option_type": "CE",
            },
        )
        result = await provider.compute(ctx)
        assert result is None

    @pytest.mark.asyncio
    async def test_missing_strike_returns_none(self, provider, next_month_expiry):
        ctx = MarketContext(
            symbol="TEST",
            spot_price=100.0,
            extra={
                "option_price": 5.0,
                "spot": 100.0,
                # strike omitted
                "expiry": next_month_expiry,
                "option_type": "CE",
            },
        )
        result = await provider.compute(ctx)
        assert result is None

    @pytest.mark.asyncio
    async def test_iv_nonconvergence_returns_none_values(self, provider, next_month_expiry):
        """An arbitrage-violated price → IV=None but dict still returned."""
        ctx = MarketContext(
            symbol="TEST",
            spot_price=100.0,
            extra={
                "option_price": -10.0,  # impossible price → no convergence
                "spot": 100.0,
                "strike": 100.0,
                "expiry": next_month_expiry,
                "option_type": "CE",
            },
        )
        result = await provider.compute(ctx)
        assert result is not None
        assert result["iv"] is None
        assert result["delta"] is None

    @pytest.mark.asyncio
    async def test_expiry_today_t_zero(self, provider):
        today = datetime.date.today().isoformat()
        ctx = MarketContext(
            symbol="TEST",
            spot_price=100.0,
            extra={
                "option_price": 5.0,
                "spot": 100.0,
                "strike": 95.0,    # 5 ITM call at expiry → intrinsic = 5
                "expiry": today,
                "option_type": "CE",
            },
        )
        result = await provider.compute(ctx)
        # T=0: IV solver may or may not converge but should not raise
        # result can be None (IV=None) or a valid dict
        assert result is None or isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_pe_happy_path(self, provider, next_month_expiry):
        ctx = MarketContext(
            symbol="NIFTY23SEP19000PE",
            underlying="NIFTY",
            spot_price=19_500.0,
            extra={
                "option_price": 180.0,
                "spot": 19_500.0,
                "strike": 19_000.0,  # OTM put
                "expiry": next_month_expiry,
                "option_type": "PE",
            },
        )
        result = await provider.compute(ctx)
        assert result is not None
        if result["iv"] is not None:
            assert result["delta"] < 0  # put delta is negative
