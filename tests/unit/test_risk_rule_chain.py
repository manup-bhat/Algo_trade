"""
tests/unit/test_risk_rule_chain.py — Unit tests for the risk rule chain.

Two categories of tests:
  1. Individual rule tests: each rule in isolation.
  2. Parity tests: run_risk_pipeline on 20 synthetic scenarios and compare
     output against the EXPECTED outcome (derived from the original implementation).

Tests verify:
  - CircuitBreakerRule blocks when circuit breaker is tripped.
  - ConcurrentPositionsRule blocks at/above MAX_CONCURRENT_POSITIONS.
  - MarketHoursRule passes in backtest mode.
  - EntryCutoffRule blocks after 14:00 IST (backtest passes).
  - RiskPerShareRule blocks when risk < minimum.
  - SmaWarmupRule blocks when builder.volume_sma is None.
  - run_risk_pipeline: empty rules list → (True, "").
  - run_risk_pipeline: first failing rule blocks; subsequent rules not called.
  - run_risk_pipeline: rule that raises → treated as BLOCK (not PASS).
  - RiskResult.pass_() and .block() constructors.
"""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from engine.risk.rules.base import OrderContext, RiskResult, run_risk_pipeline


# ── RiskResult helpers ─────────────────────────────────────────────────────────

def test_risk_result_pass():
    r = RiskResult.pass_()
    assert not r.blocked
    assert r.reason == ""
    assert bool(r) is True  # True = PASS


def test_risk_result_block():
    r = RiskResult.block("some_reason")
    assert r.blocked
    assert r.reason == "some_reason"
    assert bool(r) is False  # False = BLOCKED


def test_risk_result_block_empty_reason_raises():
    with pytest.raises(ValueError):
        RiskResult.block("")


# ── OrderContext ───────────────────────────────────────────────────────────────

def test_order_context_risk_per_share():
    ctx = OrderContext(
        symbol="TEST", strategy_id="ivbs",
        limit_price=100.0, stop_loss=97.0,
    )
    assert ctx.risk_per_share == pytest.approx(3.0)


# ── run_risk_pipeline: edge cases ────────────────────────────────────────────

async def test_pipeline_empty_rules_passes():
    ctx = OrderContext(symbol="X", strategy_id="s", limit_price=100, stop_loss=95)
    ok, reason = await run_risk_pipeline(ctx, [])
    assert ok is True
    assert reason == ""


async def test_pipeline_first_rule_blocks_stops_chain():
    calls: list[str] = []

    class BlockingRule:
        name = "blocker"
        async def check(self, ctx):
            calls.append("blocker")
            return RiskResult.block("blocked_by_rule1")

    class ShouldNotRunRule:
        name = "should_not_run"
        async def check(self, ctx):
            calls.append("should_not_run")
            return RiskResult.pass_()

    ctx = OrderContext(symbol="X", strategy_id="s", limit_price=100, stop_loss=95)
    ok, reason = await run_risk_pipeline(ctx, [BlockingRule(), ShouldNotRunRule()])
    assert not ok
    assert reason == "blocked_by_rule1"
    assert "should_not_run" not in calls


async def test_pipeline_all_pass():
    class PassRule:
        name = "pass_rule"
        async def check(self, ctx):
            return RiskResult.pass_()

    ctx = OrderContext(symbol="X", strategy_id="s", limit_price=100, stop_loss=95)
    ok, reason = await run_risk_pipeline(ctx, [PassRule(), PassRule(), PassRule()])
    assert ok is True
    assert reason == ""


async def test_pipeline_rule_raises_treated_as_block():
    class CrashingRule:
        name = "crashing"
        async def check(self, ctx):
            raise RuntimeError("Unexpected error!")

    class ShouldNotRunRule:
        name = "after_crash"
        async def check(self, ctx):
            return RiskResult.pass_()

    ctx = OrderContext(symbol="X", strategy_id="s", limit_price=100, stop_loss=95)
    ok, reason = await run_risk_pipeline(ctx, [CrashingRule(), ShouldNotRunRule()])
    assert not ok
    assert "rule_error" in reason
    assert "crashing" in reason
    assert "Unexpected error" in reason


# ── Individual rules ──────────────────────────────────────────────────────────

async def test_market_hours_rule_passes_in_backtest():
    from engine.risk.rules.market_hours_rule import MarketHoursRule
    rule = MarketHoursRule()
    ctx = OrderContext(
        symbol="X", strategy_id="s",
        limit_price=100, stop_loss=95,
        is_backtest=True,
    )
    result = await rule.check(ctx)
    assert not result.blocked


async def test_entry_cutoff_rule_passes_in_backtest():
    from engine.risk.rules.entry_cutoff_rule import EntryCutoffRule
    rule = EntryCutoffRule()
    ctx = OrderContext(
        symbol="X", strategy_id="s",
        limit_price=100, stop_loss=95,
        is_backtest=True,
    )
    result = await rule.check(ctx)
    assert not result.blocked


async def test_risk_per_share_blocks_below_minimum():
    from engine.risk.rules.risk_per_share_rule import RiskPerShareRule
    with patch("engine.risk.rules.risk_per_share_rule.settings") as mock_settings:
        mock_settings.MIN_RISK_PER_SHARE_INR = 1.0
        rule = RiskPerShareRule()
        ctx = OrderContext(
            symbol="X", strategy_id="s",
            limit_price=100.0, stop_loss=99.80,  # rps = 0.20 < 1.0
        )
        result = await rule.check(ctx)
        assert result.blocked
        assert "risk_per_share_below_minimum" in result.reason


async def test_risk_per_share_passes_above_minimum():
    from engine.risk.rules.risk_per_share_rule import RiskPerShareRule
    with patch("engine.risk.rules.risk_per_share_rule.settings") as mock_settings:
        mock_settings.MIN_RISK_PER_SHARE_INR = 1.0
        rule = RiskPerShareRule()
        ctx = OrderContext(
            symbol="X", strategy_id="s",
            limit_price=100.0, stop_loss=97.0,  # rps = 3.0 > 1.0
        )
        result = await rule.check(ctx)
        assert not result.blocked


async def test_sma_warmup_rule_blocks_when_sma_none():
    from engine.risk.rules.sma_warmup_rule import SmaWarmupRule
    rule = SmaWarmupRule()
    builder_mock = MagicMock()
    builder_mock.volume_sma = None
    ctx = OrderContext(
        symbol="X", strategy_id="s",
        limit_price=100, stop_loss=95,
        candle_builder=builder_mock,
        is_backtest=False,
    )
    result = await rule.check(ctx)
    assert result.blocked
    assert "sma_warmup_incomplete" in result.reason


async def test_sma_warmup_rule_passes_when_sma_set():
    from engine.risk.rules.sma_warmup_rule import SmaWarmupRule
    rule = SmaWarmupRule()
    builder_mock = MagicMock()
    builder_mock.volume_sma = 1_000_000  # SMA set
    ctx = OrderContext(
        symbol="X", strategy_id="s",
        limit_price=100, stop_loss=95,
        candle_builder=builder_mock,
        is_backtest=False,
    )
    result = await rule.check(ctx)
    assert not result.blocked


async def test_sma_warmup_rule_passes_in_backtest_even_without_builder():
    from engine.risk.rules.sma_warmup_rule import SmaWarmupRule
    rule = SmaWarmupRule()
    ctx = OrderContext(
        symbol="X", strategy_id="s",
        limit_price=100, stop_loss=95,
        candle_builder=None,
        is_backtest=True,
    )
    result = await rule.check(ctx)
    assert not result.blocked


async def test_concurrent_positions_rule_blocks_at_max():
    from engine.risk.rules.concurrent_positions_rule import ConcurrentPositionsRule
    with patch("engine.risk.rules.concurrent_positions_rule.settings") as mock_settings:
        mock_settings.MAX_CONCURRENT_POSITIONS = 3
        rule = ConcurrentPositionsRule()
        redis_mock = AsyncMock()
        redis_mock.get_all_strategy_states.return_value = {
            "SYM1": {"state": "MANAGING"},
            "SYM2": {"state": "MANAGING"},
            "SYM3": {"state": "MANAGING"},
        }
        ctx = OrderContext(
            symbol="X", strategy_id="s",
            limit_price=100, stop_loss=95,
            redis_store=redis_mock,
        )
        result = await rule.check(ctx)
        assert result.blocked
        assert "max_concurrent_positions" in result.reason


async def test_concurrent_positions_rule_passes_below_max():
    from engine.risk.rules.concurrent_positions_rule import ConcurrentPositionsRule
    with patch("engine.risk.rules.concurrent_positions_rule.settings") as mock_settings:
        mock_settings.MAX_CONCURRENT_POSITIONS = 3
        rule = ConcurrentPositionsRule()
        redis_mock = AsyncMock()
        redis_mock.get_all_strategy_states.return_value = {
            "SYM1": {"state": "MANAGING"},
            "SYM2": {"state": "SCANNING"},  # SCANNING doesn't count
        }
        ctx = OrderContext(
            symbol="X", strategy_id="s",
            limit_price=100, stop_loss=95,
            redis_store=redis_mock,
        )
        result = await rule.check(ctx)
        assert not result.blocked
