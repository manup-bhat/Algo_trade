"""
engine/risk/pre_trade_checks.py — Nine sequential pre-trade safety checks.

All 9 checks must pass; fail on first failure (spec §13.1).
Paper mode bypasses checks 7 and 8 (margin API calls).

Check order:
  1. Circuit breaker not tripped
  2. Concurrent positions < MAX_CONCURRENT_POSITIONS
  3. Market is open
  4. Before entry cutoff (14:00 IST)
  5. risk_per_share >= MIN_RISK_PER_SHARE_INR
  6. Quantity >= 1
  7. Margin available for this trade
  8. Peak margin safety buffer maintained
  9. SMA warmup complete for this symbol
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import pytz
import structlog

from app.core.config import settings
from engine.market import calendar as mkt_calendar
from engine.risk.circuit_breaker import circuit_breaker
from engine.risk.position_sizer import compute

if TYPE_CHECKING:
    from engine.kite.client import AsyncKiteClient
    from engine.market.candle_builder import CandleBuilder
    from engine.store.redis_store import RedisStore

log = structlog.get_logger(__name__)
IST_TZ = pytz.timezone("Asia/Kolkata")


class PreTradeChecks:
    """
    Runs all 9 pre-trade checks in sequence.

    Usage:
        ok, reason = await pre_trade_checks.run(
            symbol, limit_price, stop_loss,
            quantity, candle_builder, redis_store, kite
        )
    """

    async def run(
        self,
        symbol: str,
        limit_price: float,
        stop_loss: float,
        candle_builder: "CandleBuilder",
        redis_store: "RedisStore",
        kite: "AsyncKiteClient | None" = None,
    ) -> tuple[bool, str]:
        """
        Run all nine pre-trade checks.
        Returns (True, "") if all pass; (False, reason) on first failure.
        """

        # ── Check 1: Circuit breaker ──────────────────────────────────
        ok, reason = await circuit_breaker.check(redis_store)
        if not ok:
            return False, reason

        # ── Check 2: Concurrent positions ─────────────────────────────
        states = await redis_store.get_all_strategy_states()
        managing_count = sum(
            1 for s in states.values()
            if s.get("state") == "MANAGING"
        )
        if managing_count >= settings.MAX_CONCURRENT_POSITIONS:
            return False, f"max_concurrent_positions:{managing_count}>={settings.MAX_CONCURRENT_POSITIONS}"

        # ── Check 3: Market open ──────────────────────────────────────
        if not mkt_calendar.is_market_open():
            return False, "market_closed"

        # ── Check 4: Entry cutoff ─────────────────────────────────────
        now_ist = datetime.datetime.now(IST_TZ)
        if now_ist.time() >= settings.max_entry_time:
            return False, "after_entry_cutoff"

        # ── Check 5: Risk per share minimum ───────────────────────────
        risk_per_share = limit_price - stop_loss
        if risk_per_share < settings.MIN_RISK_PER_SHARE_INR:
            return False, (
                f"risk_per_share_below_minimum:"
                f"{risk_per_share:.2f}<{settings.MIN_RISK_PER_SHARE_INR}"
            )

        # ── Check 6: Quantity >= 1 ─────────────────────────────────────
        capital = await redis_store.get_capital()
        quantity = compute(capital, limit_price, stop_loss)
        if quantity < 1:
            return False, "insufficient_capital_for_quantity"

        # ── Check 7 + 8: Margin (skipped in paper mode) ───────────────
        if settings.is_paper_trade:
            log.debug("pre_trade_margin_skipped_paper_mode", symbol=symbol)
        else:
            if kite is None:
                return False, "kite_client_not_provided_live_mode"
            try:
                # Estimate margin via kite.order_margins() API
                order_params = [{
                    "exchange": "NSE",
                    "tradingsymbol": symbol,
                    "transaction_type": "BUY",
                    "variety": "regular",
                    "product": "MIS",
                    "order_type": "LIMIT",
                    "quantity": quantity,
                    "price": limit_price,
                }]
                margin_resp = await kite.order_margins(order_params)
                new_required = margin_resp[0].get("initial", {}).get("total", 0.0)
                available = await kite.get_available_balance()
                blocked = await redis_store.get_blocked_margin()

                # Check 7: raw availability
                if (blocked + new_required) > available:
                    return False, (
                        f"insufficient_available_margin:"
                        f"need={blocked + new_required:.0f} avail={available:.0f}"
                    )

                # Check 8: peak margin buffer
                buffer_factor = 1.0 - (settings.PEAK_MARGIN_SAFETY_BUFFER_PCT / 100)
                safe_limit = available * buffer_factor
                if (blocked + new_required) > safe_limit:
                    return False, (
                        f"peak_margin_buffer_exceeded:"
                        f"need={blocked + new_required:.0f} safe={safe_limit:.0f}"
                    )

            except Exception as exc:
                log.error("margin_check_api_error", symbol=symbol, error=str(exc))
                return False, f"margin_check_failed:{exc!s}"

        # ── Check 9: SMA warmup complete ──────────────────────────────
        if candle_builder.volume_sma is None:
            return False, "sma_warmup_incomplete"

        # All 9 checks passed
        log.debug(
            "pre_trade_checks_passed",
            symbol=symbol,
            limit=limit_price,
            sl=stop_loss,
            rps=risk_per_share,
            qty=quantity,
        )
        return True, ""


# Module-level singleton
pre_trade_checks = PreTradeChecks()
