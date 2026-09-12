"""
tests/unit/test_pre_trade_checks.py — Unit tests for all 9 PreTradeChecks.

Each test exercises exactly one check failure. The autouse paper_trade_mode 
fixture from conftest ensures settings.is_paper_trade=True throughout.

Spec §13.1.
"""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, patch

import pytest
import pytz

IST_TZ = pytz.timezone("Asia/Kolkata")

# Timestamps for patching
_MARKET_TIME = datetime.datetime(2025, 4, 7, 10, 30, 0, tzinfo=IST_TZ)
_CUTOFF_TIME = datetime.datetime(2025, 4, 7, 14, 1, 0, tzinfo=IST_TZ)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def warmed_builder():
    """CandleBuilder with 500 completed candles (fully warmed up)."""
    from engine.market.candle_builder import CandleBuilder
    b = CandleBuilder("TEST", sma_period=500)
    b.load_history([50_000] * 500)
    assert b.is_warmed_up
    return b


@pytest.fixture
def cold_builder():
    """CandleBuilder with no history (warming up)."""
    from engine.market.candle_builder import CandleBuilder
    return CandleBuilder("TEST", sma_period=500)


@pytest.fixture
def live_kite():
    """AsyncMock kite returning valid margin data for live-mode tests."""
    k = AsyncMock()
    k.order_margins.return_value = [{"initial": {"total": 10_000.0}}]
    k.get_available_balance.return_value = 200_000.0
    k.quote.return_value = {}
    return k


# ── Helper ────────────────────────────────────────────────────────────────────

async def check(redis_store, builder, kite=None, limit=500.0, sl=460.0):
    """Run PreTradeChecks with patched market-hours datetime.
    
    The conftest autouse fixture sets PAPER_TRADE=True for all tests.
    For live-mode tests, callers must monkeypatch settings.PAPER_TRADE=False.
    """
    from engine.risk.pre_trade_checks import PreTradeChecks

    # After the RiskRule refactor, datetime.now is used in entry_cutoff_rule.py
    # and mis_intraday_rule.py — both must be patched to _MARKET_TIME so tests
    # pass regardless of what hour the test suite is run.
    with patch("engine.risk.rules.entry_cutoff_rule.datetime") as mock_dt, \
         patch("engine.risk.rules.mis_intraday_rule.datetime") as mock_mis_dt, \
         patch("engine.market.calendar.is_market_open", return_value=True):
        mock_dt.datetime.now.return_value = _MARKET_TIME
        mock_mis_dt.datetime.now.return_value = _MARKET_TIME
        c = PreTradeChecks()
        return await c.run(
            symbol="TEST",
            limit_price=limit,
            stop_loss=sl,
            candle_builder=builder,
            redis_store=redis_store,
            kite=kite,
        )




async def check_paper(redis_store, builder, **kw):
    """Alias for check() — paper mode is default from conftest autouse."""
    return await check(redis_store, builder, **kw)


# ── §13.1 Tests — each check in isolation ────────────────────────────────────

class TestAllNinePass:
    async def test_paper_mode(self, redis_store, warmed_builder):
        ok, reason = await check_paper(redis_store, warmed_builder)
        assert ok, f"All 9 should pass in paper mode, got: {reason}"

    async def test_live_mode(self, redis_store, warmed_builder, live_kite, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.PAPER_TRADE", False)
        monkeypatch.setattr("app.core.config.settings.TRADE_MODE", "LIVE")
        ok, reason = await check(redis_store, warmed_builder, kite=live_kite)
        assert ok, f"All 9 should pass in live mode with mocked kite, got: {reason}"


class TestCheck1CircuitBreaker:
    async def test_tripped_in_redis(self, redis_store, warmed_builder):
        await redis_store.set_circuit_breaker(True)
        ok, reason = await check_paper(redis_store, warmed_builder)
        assert not ok
        assert "circuit_breaker" in reason

    async def test_tripped_in_memory(self, redis_store, warmed_builder):
        from engine.risk.circuit_breaker import circuit_breaker as _cb
        _cb._tripped = True
        ok, reason = await check_paper(redis_store, warmed_builder)
        assert not ok
        assert "circuit_breaker" in reason


class TestCheck2ConcurrentPositions:
    async def test_at_max(self, redis_store, warmed_builder):
        from app.core.config import settings
        for i in range(settings.MAX_CONCURRENT_POSITIONS):
            await redis_store.set_strategy_state(f"SYM{i}", {"state": "MANAGING"})
        ok, reason = await check_paper(redis_store, warmed_builder)
        assert not ok
        assert "max_concurrent" in reason

    async def test_one_below_max(self, redis_store, warmed_builder):
        """One open position but max is 2 → should still pass."""
        from app.core.config import settings
        if settings.MAX_CONCURRENT_POSITIONS < 2:
            pytest.skip("MAX_CONCURRENT_POSITIONS < 2")
        await redis_store.set_strategy_state("SYM0", {"state": "MANAGING"})
        ok, _ = await check_paper(redis_store, warmed_builder)
        assert ok


class TestCheck3MarketClosed:
    async def test_market_closed(self, redis_store, warmed_builder):
        from engine.risk.pre_trade_checks import PreTradeChecks
        with patch("engine.risk.rules.entry_cutoff_rule.datetime") as mock_dt, \
             patch("engine.market.calendar.is_market_open", return_value=False):
            mock_dt.datetime.now.return_value = _MARKET_TIME
            ok, reason = await PreTradeChecks().run(
                symbol="TEST", limit_price=500.0, stop_loss=460.0,
                candle_builder=warmed_builder, redis_store=redis_store)
        assert not ok
        assert "market_closed" in reason


class TestCheck4EntryCutoff:
    async def test_after_cutoff_fails(self, redis_store, warmed_builder):
        from engine.risk.pre_trade_checks import PreTradeChecks
        with patch("engine.risk.rules.entry_cutoff_rule.datetime") as mock_dt, \
             patch("engine.market.calendar.is_market_open", return_value=True):
            mock_dt.datetime.now.return_value = _CUTOFF_TIME
            ok, reason = await PreTradeChecks().run(
                symbol="TEST", limit_price=500.0, stop_loss=460.0,
                candle_builder=warmed_builder, redis_store=redis_store)
        assert not ok
        assert "cutoff" in reason

    async def test_before_cutoff_passes(self, redis_store, warmed_builder):
        ok, _ = await check_paper(redis_store, warmed_builder)
        assert ok  # _MARKET_TIME = 10:30 is before 14:00


class TestCheck5RiskPerShare:
    async def test_small_risk_fails(self, redis_store, warmed_builder):
        ok, reason = await check_paper(redis_store, warmed_builder, limit=500.0, sl=498.0)
        assert not ok
        assert "risk_per_share" in reason


class TestCheck6Quantity:
    async def test_zero_capital_fails(self, redis_store, warmed_builder):
        await redis_store.set_capital(0.0)
        ok, reason = await check_paper(redis_store, warmed_builder)
        assert not ok
        assert "insufficient_capital" in reason


class TestCheck7And8Margin:
    async def test_insufficient_margin_fails(self, redis_store, warmed_builder, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.PAPER_TRADE", False)
        monkeypatch.setattr("app.core.config.settings.TRADE_MODE", "LIVE")
        kite = AsyncMock()
        kite.order_margins.return_value = [{"initial": {"total": 200_000.0}}]
        kite.get_available_balance.return_value = 50_000.0
        ok, reason = await check(redis_store, warmed_builder, kite=kite)
        assert not ok
        assert "margin" in reason

    async def test_peak_margin_exceeded_fails(self, redis_store, warmed_builder, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.PAPER_TRADE", False)
        monkeypatch.setattr("app.core.config.settings.TRADE_MODE", "LIVE")
        monkeypatch.setattr("app.core.config.settings.PEAK_MARGIN_SAFETY_BUFFER_PCT", 15.0)
        kite = AsyncMock()
        kite.order_margins.return_value = [{"initial": {"total": 90_000.0}}]
        kite.get_available_balance.return_value = 100_000.0  # safe=85k < 90k needed
        ok, reason = await check(redis_store, warmed_builder, kite=kite)
        assert not ok
        assert "peak_margin" in reason

    async def test_skipped_in_paper_mode(self, redis_store, warmed_builder):
        kite = AsyncMock()
        kite.order_margins.side_effect = Exception("Should not be called in paper mode")
        ok, reason = await check_paper(redis_store, warmed_builder, kite=kite)
        assert ok, f"Paper mode bypasses margin checks; got: {reason}"


class TestCheck9SmaWarmup:
    async def test_cold_builder_fails(self, redis_store, cold_builder):
        ok, reason = await check_paper(redis_store, cold_builder)
        assert not ok
        assert "sma_warmup_incomplete" in reason

    async def test_warm_builder_passes(self, redis_store, warmed_builder):
        ok, _ = await check_paper(redis_store, warmed_builder)
        assert ok
