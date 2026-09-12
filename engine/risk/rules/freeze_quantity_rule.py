"""
engine/risk/rules/freeze_quantity_rule.py — Check 11: Freeze Quantity Guard.

NSE imposes a per-contract order size limit ("freeze quantity") on F&O instruments
to prevent large accidental orders. Submitting a single order exceeding this limit
results in an exchange rejection.

This rule:
  1. Looks up the freeze quantity for ctx.symbol via InstrumentMaster.
  2. If ctx.computed_quantity > freeze_qty: BLOCK with a clear reason.
  3. For equity (no F&O freeze), freeze_qty is effectively infinite — PASS.

Integrated at position 11 in the pre-trade risk pipeline:
    [CircuitBreaker, ConcurrentPositions, MarketHours, EntryCutoff,
     RiskPerShare, Quantity, MarginAvailability, SmaWarmup,
     CapitalAllocator, FreezeQuantity ← here]

Note: OrderService._split_for_freeze() handles multi-leg splitting when called
from place_order_group(). This rule is a safety gate for single-leg orders placed
directly via place_entry() — it blocks rather than auto-splits, forcing the caller
to use place_order_group() for large orders.
"""

from __future__ import annotations

import structlog

from engine.risk.rules.base import OrderContext, RiskResult

log = structlog.get_logger(__name__)

# Lazy import to avoid circular deps at module load
_instrument_master = None


def _get_master():
    global _instrument_master
    if _instrument_master is None:
        from engine.market.instrument_master import instrument_master
        _instrument_master = instrument_master
    return _instrument_master


class FreezeQuantityRule:
    """
    Check 11 — Freeze Quantity Guard.

    Blocks single-leg orders that exceed NSE's per-contract freeze quantity.
    For equity instruments the freeze quantity is ~999,999 (no practical limit).

    Edge cases:
        - ctx.computed_quantity == 0: passes (will be caught by QuantityRule earlier).
        - NFO dump not loaded: InstrumentMaster returns category-default → still safe.
        - Symbol not recognized: default freeze used (conservative).
        - Backtest mode: check is skipped (no exchange submission).
    """

    name = "freeze_quantity"

    async def check(self, ctx: OrderContext) -> RiskResult:
        # Skip in backtest — no exchange rejection risk
        if ctx.is_backtest:
            return RiskResult.pass_()

        qty = ctx.computed_quantity
        if qty <= 0:
            return RiskResult.pass_()  # QuantityRule already blocks zero qty

        master = _get_master()
        freeze_qty = master.get_freeze_quantity(ctx.symbol)

        if qty > freeze_qty:
            log.warning(
                "freeze_quantity_rule_blocked",
                symbol=ctx.symbol,
                computed_qty=qty,
                freeze_qty=freeze_qty,
                hint=(
                    "Use order_service.place_order_group() with _split_for_freeze() "
                    "to auto-split this order into compliant legs."
                ),
            )
            return RiskResult.block(
                f"qty {qty} exceeds NSE freeze limit {freeze_qty} for {ctx.symbol}. "
                f"Use place_order_group() for auto-splitting."
            )

        return RiskResult.pass_()
