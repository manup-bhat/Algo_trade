"""
engine/risk/rules/risk_per_share_rule.py — Check 5: Minimum risk per share ≥ ₹1.

Ensures the distance between limit_price and stop_loss is large enough that
the position sizing formula produces a meaningful quantity.  A tiny R-distance
(e.g. 0.05) would require enormous share counts to risk even ₹1,000.
"""

from __future__ import annotations

from app.core.config import settings
from engine.risk.rules.base import OrderContext, RiskResult


class RiskPerShareRule:
    """Check 5 — limit_price - stop_loss >= MIN_RISK_PER_SHARE_INR."""

    name = "risk_per_share"

    async def check(self, ctx: OrderContext) -> RiskResult:
        rps = ctx.risk_per_share
        if rps < settings.MIN_RISK_PER_SHARE_INR:
            return RiskResult.block(
                f"risk_per_share_below_minimum:{rps:.2f}<{settings.MIN_RISK_PER_SHARE_INR}"
            )
        return RiskResult.pass_()
