"""
tests/unit/test_mis_intraday_rule.py — Unit tests for MISIntradayRule (Check 12).

Covers:
    - Backtest mode: always passes
    - Paper mode: always passes
    - Live mode, correct product (MIS): passes session check
    - Live mode, wrong product (NRML for equity): blocks
    - F&O (NFO exchange): skips product check, passes
    - Session window: before 09:15 blocks, 09:15-15:20 passes, 15:20+ blocks
    - Circuit limit: within 2% of upper → blocks; within 2% of lower → blocks; normal → passes
"""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from engine.risk.rules.base import OrderContext
from engine.risk.rules.mis_intraday_rule import MISIntradayRule


IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

# Representative IST times for test scenarios
_PRE_OPEN   = datetime.datetime(2026, 9, 11, 9,  5, tzinfo=IST)   # 09:05 — pre-open
_MARKET_ON  = datetime.datetime(2026, 9, 11, 11, 0, tzinfo=IST)   # 11:00 — session open
_POST_CLOSE = datetime.datetime(2026, 9, 11, 15, 25, tzinfo=IST)  # 15:25 — post close


def _ctx(**kw) -> OrderContext:
    defaults = dict(
        symbol="RELIANCE",
        strategy_id="test",
        limit_price=500.0,
        stop_loss=460.0,
        is_paper_trade=False,
        is_backtest=False,
        computed_quantity=10,
        extra={"exchange": "NSE", "product": "MIS"},
    )
    defaults.update(kw)
    return OrderContext(**defaults)


@pytest.fixture
def rule():
    return MISIntradayRule()


# ── Backtest / Paper mode ─────────────────────────────────────────────────────

class TestBypassModes:
    @pytest.mark.asyncio
    async def test_backtest_always_passes(self, rule):
        ctx = _ctx(is_backtest=True)
        result = await rule.check(ctx)
        assert not result.blocked

    @pytest.mark.asyncio
    async def test_paper_always_passes(self, rule):
        ctx = _ctx(is_paper_trade=True)
        result = await rule.check(ctx)
        assert not result.blocked


# ── Product type sub-check ────────────────────────────────────────────────────

class TestProductType:
    @pytest.mark.asyncio
    async def test_nrml_on_nse_blocks(self, rule):
        with patch(
            "engine.risk.rules.mis_intraday_rule.datetime"
        ) as mdt:
            mdt.datetime.now.return_value = _MARKET_ON
            ctx = _ctx(extra={"exchange": "NSE", "product": "NRML"})
            result = await rule.check(ctx)
        assert result.blocked
        assert "MIS" in result.reason

    @pytest.mark.asyncio
    async def test_mis_on_nse_passes(self, rule):
        with patch(
            "engine.risk.rules.mis_intraday_rule.datetime"
        ) as mdt:
            mdt.datetime.now.return_value = _MARKET_ON
            ctx = _ctx(extra={"exchange": "NSE", "product": "MIS"})
            result = await rule.check(ctx)
        assert not result.blocked

    @pytest.mark.asyncio
    async def test_nrml_on_nfo_passes(self, rule):
        """F&O orders use NRML — product check must be skipped."""
        with patch(
            "engine.risk.rules.mis_intraday_rule.datetime"
        ) as mdt:
            mdt.datetime.now.return_value = _MARKET_ON
            ctx = _ctx(extra={"exchange": "NFO", "product": "NRML"})
            result = await rule.check(ctx)
        assert not result.blocked


# ── Session window sub-check ──────────────────────────────────────────────────

class TestSessionWindow:
    @pytest.mark.asyncio
    async def test_pre_open_blocks(self, rule):
        with patch(
            "engine.risk.rules.mis_intraday_rule.datetime"
        ) as mdt:
            mdt.datetime.now.return_value = _PRE_OPEN
            ctx = _ctx()
            result = await rule.check(ctx)
        assert result.blocked
        assert "before_0915" in result.reason

    @pytest.mark.asyncio
    async def test_market_hours_passes(self, rule):
        with patch(
            "engine.risk.rules.mis_intraday_rule.datetime"
        ) as mdt:
            mdt.datetime.now.return_value = _MARKET_ON
            ctx = _ctx()
            result = await rule.check(ctx)
        assert not result.blocked

    @pytest.mark.asyncio
    async def test_post_close_blocks(self, rule):
        with patch(
            "engine.risk.rules.mis_intraday_rule.datetime"
        ) as mdt:
            mdt.datetime.now.return_value = _POST_CLOSE
            ctx = _ctx()
            result = await rule.check(ctx)
        assert result.blocked
        assert "after_1520" in result.reason

    @pytest.mark.asyncio
    async def test_exactly_at_market_open_passes(self, rule):
        at_open = datetime.datetime(2026, 9, 11, 9, 15, tzinfo=IST)
        with patch(
            "engine.risk.rules.mis_intraday_rule.datetime"
        ) as mdt:
            mdt.datetime.now.return_value = at_open
            ctx = _ctx()
            result = await rule.check(ctx)
        assert not result.blocked

    @pytest.mark.asyncio
    async def test_exactly_at_cutoff_blocks(self, rule):
        at_cutoff = datetime.datetime(2026, 9, 11, 15, 20, tzinfo=IST)
        with patch(
            "engine.risk.rules.mis_intraday_rule.datetime"
        ) as mdt:
            mdt.datetime.now.return_value = at_cutoff
            ctx = _ctx()
            result = await rule.check(ctx)
        assert result.blocked


# ── Circuit limit sub-check ───────────────────────────────────────────────────

class TestCircuitLimit:
    @pytest.mark.asyncio
    async def test_within_2pct_of_upper_circuit_blocks(self, rule):
        """Price >= upper_circuit * 0.98 → block."""
        mock_kite = MagicMock()
        # quote returns dict with upper_circuit_limit
        mock_kite.quote = AsyncMock(return_value={
            "NSE:RELIANCE": {
                "upper_circuit_limit": 600.0,
                "lower_circuit_limit": 400.0,
            }
        })
        with patch("engine.risk.rules.mis_intraday_rule.datetime") as mdt:
            mdt.datetime.now.return_value = _MARKET_ON
            ctx = _ctx(limit_price=592.0, kite=mock_kite)  # 592/600 = 98.7% → within 2%
            result = await rule.check(ctx)
        assert result.blocked
        assert "upper circuit" in result.reason

    @pytest.mark.asyncio
    async def test_within_2pct_of_lower_circuit_blocks(self, rule):
        """Price <= lower_circuit * 1.02 → block."""
        mock_kite = MagicMock()
        mock_kite.quote = AsyncMock(return_value={
            "NSE:RELIANCE": {
                "upper_circuit_limit": 600.0,
                "lower_circuit_limit": 400.0,
            }
        })
        with patch("engine.risk.rules.mis_intraday_rule.datetime") as mdt:
            mdt.datetime.now.return_value = _MARKET_ON
            ctx = _ctx(limit_price=407.0, kite=mock_kite)  # 407/400 = 101.8% → within 2%
            result = await rule.check(ctx)
        assert result.blocked
        assert "lower circuit" in result.reason

    @pytest.mark.asyncio
    async def test_price_within_normal_range_passes(self, rule):
        mock_kite = MagicMock()
        mock_kite.quote = AsyncMock(return_value={
            "NSE:RELIANCE": {
                "upper_circuit_limit": 600.0,
                "lower_circuit_limit": 400.0,
            }
        })
        with patch("engine.risk.rules.mis_intraday_rule.datetime") as mdt:
            mdt.datetime.now.return_value = _MARKET_ON
            ctx = _ctx(limit_price=500.0, kite=mock_kite)  # midpoint — safe
            result = await rule.check(ctx)
        assert not result.blocked

    @pytest.mark.asyncio
    async def test_no_kite_skips_circuit_check(self, rule):
        """Paper mode (kite=None) → circuit check skipped."""
        with patch("engine.risk.rules.mis_intraday_rule.datetime") as mdt:
            mdt.datetime.now.return_value = _MARKET_ON
            ctx = _ctx(kite=None)
            result = await rule.check(ctx)
        assert not result.blocked

    @pytest.mark.asyncio
    async def test_quote_api_failure_passes_through(self, rule):
        """API failure on circuit check → passes (can't verify → allow)."""
        mock_kite = MagicMock()
        mock_kite.quote = AsyncMock(side_effect=Exception("network error"))
        with patch("engine.risk.rules.mis_intraday_rule.datetime") as mdt:
            mdt.datetime.now.return_value = _MARKET_ON
            ctx = _ctx(kite=mock_kite)
            result = await rule.check(ctx)
        # API failure → fall-through to PASS (circuit check non-blocking on API error)
        assert not result.blocked
