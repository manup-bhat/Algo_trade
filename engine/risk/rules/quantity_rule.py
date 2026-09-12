"""
engine/risk/rules/quantity_rule.py — Check 6: Computed quantity >= 1.

Computes the position size using the 1%-risk formula and stores it in
ctx.computed_quantity so downstream rules (margin, capital allocator) can
reuse it without recomputing.

Side effect: mutates ctx.computed_quantity.  This is intentional and
documented — OrderContext is the shared state object for one pipeline run.
"""

from __future__ import annotations

import structlog

from engine.risk.position_sizer import compute
from engine.risk.rules.base import OrderContext, RiskResult

log = structlog.get_logger(__name__)


class QuantityRule:
    """Check 6 — computed quantity >= 1; also stores result in ctx."""

    name = "quantity"

    async def check(self, ctx: OrderContext) -> RiskResult:
        # Fetch capital: in backtest mode, BacktestEngine stores capital in Redis
        # (via redis.set_capital) so we try Redis first, then ctx.extra as fallback.
        # In live/paper mode, only Redis is used (never None when trading).
        if ctx.redis_store is not None:
            capital = await ctx.redis_store.get_capital()
            if capital <= 0.0:
                # Try ctx.extra fallback (unit-test injection without Redis)
                capital = float(ctx.extra.get("capital", 0.0))
        elif ctx.is_backtest:
            # Backtest without Redis — use injected capital from ctx.extra
            capital = float(ctx.extra.get("capital", 0.0))
        else:
            return RiskResult.block("quantity:cannot_determine_capital")

        if capital <= 0.0:
            log.warning("position_sizer_zero_capital")
            return RiskResult.block("insufficient_capital_for_quantity")

        quantity = compute(capital, ctx.limit_price, ctx.stop_loss)

        # Store for downstream rules (CapitalAllocatorRule, MarginAvailabilityRule)
        ctx.computed_quantity = quantity  # type: ignore[misc]  # dataclass frozen=False

        if quantity < 1:
            return RiskResult.block("insufficient_capital_for_quantity")
        return RiskResult.pass_()

