"""
engine/risk/rules/stale_data_rule.py — Check 13: Stale Data Guard.

Prevents the engine from executing entry signals based on old data if the
WebSocket disconnects or the feed stops ticking for >60s.
Cases without real API data (outages) will be blocked safely.
"""

from __future__ import annotations

import datetime
import json

import structlog

from engine.risk.rules.base import OrderContext, RiskResult

log = structlog.get_logger(__name__)


class StaleDataRule:
    """Check 13 — Data freshness guard. Rejects trades if tick age > 60s."""

    name = "stale_data"

    async def check(self, ctx: OrderContext) -> RiskResult:
        if ctx.is_backtest:
            return RiskResult.pass_()

        if ctx.redis_store is None:
            return RiskResult.pass_()

        try:
            raw = await ctx.redis_store._r.hget("livetick_hash", ctx.symbol)
            if not raw:
                # If there's no tick at all, we can't judge staleness, so we block.
                # A symbol being traded should have ticks.
                return RiskResult.block(f"stale_data:no_tick_data_for_{ctx.symbol}")

            tick = json.loads(raw)
            last_trade_time = tick.get("last_trade_time") or tick.get("exchange_timestamp")
            if not last_trade_time:
                return RiskResult.pass_()

            import dateutil.parser as _dp
            import pytz as _pytz

            last_dt = _dp.parse(str(last_trade_time))
            if last_dt.tzinfo is None:
                last_dt = _pytz.utc.localize(last_dt)

            now_utc = datetime.datetime.now(datetime.UTC)
            age_sec = (now_utc - last_dt).total_seconds()

            if age_sec > 60:
                log.warning(
                    "stale_data_entry_blocked",
                    symbol=ctx.symbol,
                    tick_age_sec=age_sec
                )
                return RiskResult.block(f"stale_data:tick_age_{int(age_sec)}s>60s")

        except Exception as exc:
            log.warning("stale_data_rule_error", symbol=ctx.symbol, error=str(exc))
            return RiskResult.block("stale_data:tick_parse_error")

        return RiskResult.pass_()
