"""
engine/risk/rules/capital_allocator_rule.py — Check 10: Per-strategy capital gate.

The 10th pre-trade check introduced in Part 2 §4.5 and re-prioritised to
Phase 0 in Part 3 §1 (pulling it forward before any second live strategy goes
live, since two strategies already share one Kite account).

Required context:
  - ctx.strategy_id: which strategy is requesting the trade
  - ctx.computed_quantity: set by QuantityRule (Check 6) — must run after it
  - ctx.extra["estimated_margin"]: caller may pre-populate if known; if absent
    the rule estimates margin = computed_quantity * limit_price * 0.20 (20% MIS
    margin proxy — conservative, avoids a Kite API call in the pre-trade path)

Design choice (INR absolute amounts):
  Allocations are fixed INR amounts, not percentages of account equity.
  Rationale: percentages would cause the cap to silently shift as intraday
  P&L moves account equity — a strategy could gain access to more capital
  mid-session simply because another strategy had a good trade.  That coupling
  is exactly what the ledger exists to prevent.
"""

from __future__ import annotations

import structlog

from engine.risk.rules.base import OrderContext, RiskResult

log = structlog.get_logger(__name__)

# Conservative MIS margin proxy when no pre-computed margin is available.
# NSE MIS margins are typically 15–25% of notional for equities.
# 20% is a safe overestimate — better to block a safe trade than allow
# an over-allocated one.
_MIS_MARGIN_PROXY = 0.20


class CapitalAllocatorRule:
    """
    Check 10 — strategy has sufficient free capital allocation.

    Requires `ctx.extra["capital_allocator"]` to be a CapitalAllocator instance.
    This is injected by PreTradeChecks at construction time.
    """

    name = "capital_allocator"

    async def check(self, ctx: OrderContext) -> RiskResult:
        # Skip in backtest mode — BacktestEngine.portfolio tracks its own capital
        if ctx.is_backtest:
            return RiskResult.pass_()

        allocator = ctx.extra.get("capital_allocator")
        if allocator is None:
            # No allocator wired → pass (backwards compatible with strategies that
            # haven't declared a manifest allocation yet).  Log a warning so the
            # operator knows this check is dormant for this strategy.
            log.warning(
                "capital_allocator_rule_skipped",
                strategy_id=ctx.strategy_id,
                symbol=ctx.symbol,
                reason="no_allocator_in_ctx_extra",
            )
            return RiskResult.pass_()

        # Estimate required margin
        if "estimated_margin" in ctx.extra:
            required_margin = float(ctx.extra["estimated_margin"])
        else:
            # Proxy: qty * price * MIS_margin_proxy
            qty = max(ctx.computed_quantity, 1)
            required_margin = qty * ctx.limit_price * _MIS_MARGIN_PROXY
            log.debug(
                "capital_allocator_margin_estimated",
                strategy_id=ctx.strategy_id,
                qty=qty,
                price=ctx.limit_price,
                estimated_margin=required_margin,
            )

        ok, reason = await allocator.check(ctx.strategy_id, required_margin)
        if not ok:
            return RiskResult.block(reason)
        return RiskResult.pass_()
