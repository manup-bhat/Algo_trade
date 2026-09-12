"""
engine/risk/rules/margin_availability_rule.py — Checks 7 + 8: Margin gates.

Check 7: (blocked_margin + new_required) <= available_cash
Check 8: (blocked_margin + new_required) <= available_cash * (1 - buffer_pct)

Both checks are skipped in paper mode (no real margin to check) and in
backtest mode (simulated capital is tracked by BacktestEngine.portfolio).

Uses ctx.computed_quantity populated by QuantityRule — must run after it.
"""

from __future__ import annotations

import structlog

from app.core.config import settings
from engine.risk.rules.base import OrderContext, RiskResult

log = structlog.get_logger(__name__)


class MarginAvailabilityRule:
    """Checks 7 + 8 — margin availability and peak-margin buffer."""

    name = "margin_availability"

    async def check(self, ctx: OrderContext) -> RiskResult:
        # Skip in paper / backtest mode
        if ctx.is_paper_trade or ctx.is_backtest:
            log.debug("margin_check_skipped", mode="paper_or_backtest", symbol=ctx.symbol)
            return RiskResult.pass_()

        if ctx.kite is None:
            return RiskResult.block("margin_availability:kite_client_not_provided")

        if ctx.redis_store is None:
            return RiskResult.block("margin_availability:no_redis_store")

        if ctx.computed_quantity < 1:
            # Should have been caught by QuantityRule — defensive guard
            return RiskResult.block("margin_availability:quantity_not_computed")

        try:
            order_params = [{
                "exchange": ctx.extra.get("exchange", "NSE"),
                "tradingsymbol": ctx.symbol,
                "transaction_type": "BUY",
                "variety": "regular",
                "product": ctx.extra.get("product", "MIS"),
                "order_type": "LIMIT",
                "quantity": ctx.computed_quantity,
                "price": ctx.limit_price,
            }]
            margin_resp = await ctx.kite.order_margins(order_params)
            new_required = margin_resp[0].get("initial", {}).get("total", 0.0)
            available = await ctx.kite.get_available_balance()
            blocked = await ctx.redis_store.get_blocked_margin()

            # Check 7: raw availability
            total_needed = blocked + new_required
            if total_needed > available:
                return RiskResult.block(
                    f"insufficient_available_margin:need={total_needed:.0f} avail={available:.0f}"
                )

            # Check 8: peak margin buffer (safety headroom)
            buffer_factor = 1.0 - (settings.PEAK_MARGIN_SAFETY_BUFFER_PCT / 100)
            safe_limit = available * buffer_factor
            if total_needed > safe_limit:
                return RiskResult.block(
                    f"peak_margin_buffer_exceeded:need={total_needed:.0f} safe={safe_limit:.0f}"
                )

        except Exception as exc:
            log.error("margin_check_api_error", symbol=ctx.symbol, error=str(exc))
            return RiskResult.block(f"margin_check_failed:{exc!s}")

        return RiskResult.pass_()
