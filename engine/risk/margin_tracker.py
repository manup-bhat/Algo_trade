"""
engine/risk/margin_tracker.py — Tracks blocked margin for SEBI peak margin compliance.

Maintains running sum of margin committed to open positions in Redis.
Refreshes from kite.positions() every 30 minutes.

Redis key: engine:blocked_margin
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from app.core.config import settings

if TYPE_CHECKING:
    from engine.kite.client import AsyncKiteClient
    from engine.store.redis_store import RedisStore

log = structlog.get_logger(__name__)


class MarginTracker:
    """
    Tracks blocked margin for peak margin compliance.

    Usage:
        await margin_tracker.increment(margin_amount, redis_store)
        await margin_tracker.decrement(margin_amount, redis_store)
        ok = await margin_tracker.check_available(new_required, kite, redis_store)
    """

    async def increment(self, amount: float, redis_store: "RedisStore") -> None:
        """Add margin blocked by a new entry fill."""
        await redis_store.increment_blocked_margin(amount)
        log.debug("margin_blocked", amount=amount)

    async def decrement(self, amount: float, redis_store: "RedisStore") -> None:
        """Release margin when a position closes."""
        await redis_store.decrement_blocked_margin(amount)
        log.debug("margin_released", amount=amount)

    async def check_available(
        self,
        new_required: float,
        redis_store: "RedisStore",
        available_balance: float,
    ) -> tuple[bool, str]:
        """
        Check if opening a new position is within margin safety limits.

        Spec §13.1 checks 7 and 8:
          7. (blocked_margin + new_required) <= available_balance
          8. margin buffer: (blocked + new) <= available × (1 - BUFFER_PCT/100)

        Returns (True, "") if safe, (False, reason) if not.
        """
        blocked = await redis_store.get_blocked_margin()
        total_required = blocked + new_required

        # Check 7: raw available
        if total_required > available_balance:
            reason = (
                f"insufficient_margin: need={total_required:.0f} "
                f"available={available_balance:.0f}"
            )
            log.warning("margin_check_failed", reason=reason)
            return False, reason

        # Check 8: safety buffer
        buffer_factor = 1.0 - (settings.PEAK_MARGIN_SAFETY_BUFFER_PCT / 100)
        safe_limit = available_balance * buffer_factor
        if total_required > safe_limit:
            reason = (
                f"peak_margin_buffer_exceeded: need={total_required:.0f} "
                f"safe_limit={safe_limit:.0f}"
            )
            log.warning("margin_buffer_exceeded", reason=reason)
            return False, reason

        return True, ""

    async def refresh_from_broker(
        self,
        kite: "AsyncKiteClient",
        redis_store: "RedisStore",
    ) -> None:
        """
        Refresh blocked margin from broker positions every 30 minutes.
        Calculates margin from current open positions to correct any drift.
        """
        try:
            positions = await kite.positions()
            day_positions = positions.get("day", [])
            total_blocked = sum(
                abs(p.get("value", 0))
                for p in day_positions
                if p.get("quantity", 0) != 0
            )
            await redis_store.set_blocked_margin(total_blocked)
            log.info("margin_refreshed", blocked=total_blocked)
        except Exception as exc:
            log.error("margin_refresh_failed", error=str(exc))


# Module-level singleton
margin_tracker = MarginTracker()
