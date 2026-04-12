"""
engine/risk/circuit_breaker.py — Daily loss kill switch.

Trips when: daily_net_pnl <= -(capital × DAILY_LOSS_LIMIT_PCT / 100)
Resets at: 9:00 AM each trading day (called by runner.py pre-market job).

Design: in-memory flag for fast check(), Redis for persistence + cross-process visibility.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from app.core.config import settings

if TYPE_CHECKING:
    from engine.store.redis_store import RedisStore

log = structlog.get_logger(__name__)


class CircuitBreaker:
    """
    Daily loss kill switch.

    Usage:
        ok, reason = await circuit_breaker.check(redis_store)
        if not ok:
            # halt engine
    """

    def __init__(self) -> None:
        self._tripped: bool = False  # In-memory fast path

    async def check(self, redis_store: "RedisStore") -> tuple[bool, str]:
        """
        Returns (True, "") if trading may proceed.
        Returns (False, reason) if breaker is tripped.

        Once tripped in-memory, skips Redis read for speed.
        """
        if self._tripped:
            return False, "circuit_breaker_already_tripped"

        # Read from Redis (authoritative for cross-process awareness)
        try:
            tripped = await redis_store.is_circuit_breaker_tripped()
            if tripped:
                self._tripped = True
                return False, "circuit_breaker_tripped_in_redis"

            # Compute from daily P&L and capital
            daily_pnl = await redis_store.get_daily_pnl()
            capital = await redis_store.get_capital()

            if capital > 0:
                loss_limit = -(capital * settings.DAILY_LOSS_LIMIT_PCT / 100)
                if daily_pnl <= loss_limit:
                    await self.trip(redis_store, f"pnl={daily_pnl:.2f}_<=_limit={loss_limit:.2f}")
                    return False, f"daily_loss_limit_breached:{daily_pnl:.2f}"

        except Exception as exc:
            log.error("circuit_breaker_check_error", error=str(exc))
            # Fail-safe: if we can't check, allow trading (don't false-halt)
            return True, ""

        return True, ""

    async def trip(self, redis_store: "RedisStore", reason: str = "") -> None:
        """Trip the circuit breaker and persist to Redis."""
        self._tripped = True
        await redis_store.set_circuit_breaker(True)
        log.critical("circuit_breaker_tripped", reason=reason)

    async def reset(self, redis_store: "RedisStore") -> None:
        """Reset at 9:00 AM for a new trading day."""
        self._tripped = False
        await redis_store.set_circuit_breaker(False)
        log.info("circuit_breaker_reset")


# Module-level singleton
circuit_breaker = CircuitBreaker()
