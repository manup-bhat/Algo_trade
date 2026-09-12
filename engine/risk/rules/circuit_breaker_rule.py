"""
engine/risk/rules/circuit_breaker_rule.py — Check 1: Daily drawdown kill switch.

Blocks any new order if the daily circuit breaker has been tripped (i.e. the
daily net loss limit has been breached for the session).

Mirrors the first check in the original pre_trade_checks.py, extracted into
an independently testable unit.
"""

from __future__ import annotations

import structlog

from engine.risk.circuit_breaker import circuit_breaker
from engine.risk.rules.base import OrderContext, RiskResult

log = structlog.get_logger(__name__)


class CircuitBreakerRule:
    """Check 1 — circuit breaker not tripped."""

    name = "circuit_breaker"

    async def check(self, ctx: OrderContext) -> RiskResult:
        if ctx.redis_store is None:
            # In backtest mode there is no Redis — circuit breaker is inactive.
            if ctx.is_backtest:
                return RiskResult.pass_()
            return RiskResult.block("circuit_breaker:no_redis_store")

        ok, reason = await circuit_breaker.check(ctx.redis_store)
        if not ok:
            return RiskResult.block(reason)
        return RiskResult.pass_()
