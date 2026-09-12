"""
engine/risk/rules/sma_warmup_rule.py — Check 9: SMA warmup complete.

Blocks entries for a symbol whose volume SMA has not been fully warmed up
(less than 500 candles in the rolling deque).  Trading against an incomplete
SMA produces unreliable spike multiples — a 10x spike against a 50-candle
partial average is not the same as 10x against a full 500-minute baseline.

Uses ctx.candle_builder which is injected by the call site (pre_trade_checks.py).
In backtest mode the candle_builder is always provided and its SMA state is
known — pass the check.
"""

from __future__ import annotations

from engine.risk.rules.base import OrderContext, RiskResult


class SmaWarmupRule:
    """Check 9 — symbol's volume SMA builder is fully warmed up."""

    name = "sma_warmup"

    async def check(self, ctx: OrderContext) -> RiskResult:
        if ctx.is_backtest:
            return RiskResult.pass_()

        if ctx.candle_builder is None:
            return RiskResult.block("sma_warmup:candle_builder_not_provided")

        if ctx.candle_builder.volume_sma is None:
            return RiskResult.block("sma_warmup_incomplete")

        return RiskResult.pass_()
