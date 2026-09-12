"""
engine/risk/rules/entry_cutoff_rule.py — Check 4: Before 14:00 IST entry cutoff.

No new entries after 14:00 IST — insufficient time for the multi-phase setup
to complete before EOD square-off at 15:20.  Passes in backtest mode.
"""

from __future__ import annotations

import datetime

import pytz

from app.core.config import settings
from engine.risk.rules.base import OrderContext, RiskResult

IST_TZ = pytz.timezone("Asia/Kolkata")


class EntryCutoffRule:
    """Check 4 — current time < 14:00 IST."""

    name = "entry_cutoff"

    async def check(self, ctx: OrderContext) -> RiskResult:
        if ctx.is_backtest:
            return RiskResult.pass_()

        now_ist = datetime.datetime.now(IST_TZ)
        if now_ist.time() >= settings.max_entry_time:
            return RiskResult.block("after_entry_cutoff")
        return RiskResult.pass_()
