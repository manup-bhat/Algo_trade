"""
engine/risk/rules/concurrent_positions_rule.py — Check 2: Max concurrent positions.

Blocks a new entry if the number of symbols currently in MANAGING state
equals or exceeds MAX_CONCURRENT_POSITIONS.

Note: this is a global cap across ALL strategies (the same as the original
check).  Per-strategy caps are enforced separately via the CapitalAllocatorRule.
"""

from __future__ import annotations

import structlog

from app.core.config import settings
from engine.risk.rules.base import OrderContext, RiskResult

log = structlog.get_logger(__name__)


class ConcurrentPositionsRule:
    """Check 2 — concurrent MANAGING positions < MAX_CONCURRENT_POSITIONS."""

    name = "concurrent_positions"

    async def check(self, ctx: OrderContext) -> RiskResult:
        if ctx.redis_store is None:
            if ctx.is_backtest:
                return RiskResult.pass_()
            return RiskResult.block("concurrent_positions:no_redis_store")

        states = await ctx.redis_store.get_all_strategy_states()
        managing_count = sum(
            1 for s in states.values() if s.get("state") == "MANAGING"
        )
        if managing_count >= settings.MAX_CONCURRENT_POSITIONS:
            return RiskResult.block(
                f"max_concurrent_positions:{managing_count}>={settings.MAX_CONCURRENT_POSITIONS}"
            )
        return RiskResult.pass_()
