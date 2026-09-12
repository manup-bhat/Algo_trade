"""
engine/risk/rules/market_hours_rule.py — Check 3: Market is currently open.

Passes unconditionally in backtest mode (the backtest engine only feeds
candles during simulated market hours — it doesn't need a real-time gate).
"""

from __future__ import annotations

from engine.market import calendar as mkt_calendar
from engine.risk.rules.base import OrderContext, RiskResult


class MarketHoursRule:
    """Check 3 — market is open (09:15–15:30 IST)."""

    name = "market_hours"

    async def check(self, ctx: OrderContext) -> RiskResult:
        if ctx.is_backtest:
            return RiskResult.pass_()

        if not mkt_calendar.is_market_open():
            return RiskResult.block("market_closed")
        return RiskResult.pass_()
