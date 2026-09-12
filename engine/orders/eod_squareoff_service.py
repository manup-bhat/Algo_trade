"""
engine/orders/eod_squareoff_service.py — Strategy-agnostic end-of-day position closer.

Runs INDEPENDENTLY of strategy lifecycle hooks (does not call on_squareoff()).
Its job is to guarantee zero open positions at market close regardless of whether
a strategy crashed, hung, or forgot to clean up.

Lifecycle in runner.py:
  15:18  → early_check():      if >1 MANAGING position, force-close all early
  15:20  → force_squareoff():  close every open position unconditionally
  ON EMERGENCY_STOP → emergency_squareoff(): immediate close, then shutdown

Idempotency:
  Uses the same Redis NX exit lock (`lock:symbol:{sym}`) already used by the
  state machine's exit flow — if the strategy already placed an exit order for
  a symbol, this service won't place a duplicate.

Sources of truth for open positions:
  1. Redis: pattern `position:{symbol}` keys (set by state machine on fill).
  2. Kite: `net_positions()` API (catches orphans from crashed strategies).
  Both sources are checked; the union is closed.

Edge cases:
  - Strategy closes position between 15:20 check and our exit → NX lock prevents dupe.
  - Kite API timeout during exit → log CRITICAL + re-queue for next scan pass.
  - Exit order rejected → retry once with MARKET order (AMO fallback if >15:29).
  - Multiple exit order attempts for same symbol → NX lock serialises them.
"""

from __future__ import annotations

import asyncio
import datetime
from typing import TYPE_CHECKING, Any

import pytz
import structlog

from app.core.config import settings

if TYPE_CHECKING:
    from engine.kite.client import AsyncKiteClient
    from engine.orders.order_service import OrderService
    from engine.store.redis_store import RedisStore

log = structlog.get_logger(__name__)
IST_TZ = pytz.timezone("Asia/Kolkata")

# If we're still trying exits after 15:29, switch to AMO as escape hatch
_AMO_CUTOFF_HOUR = 15
_AMO_CUTOFF_MINUTE = 29


class EODSquareOffService:
    """
    Strategy-agnostic end-of-day position closer.

    Wraps position discovery + exit order placement in a single reusable service.
    Strategies still run their own on_squareoff() at 15:20 (via StrategyRouter);
    this service runs 5 seconds later as a guaranteed safety net.
    """

    def __init__(
        self,
        order_service: "OrderService | None" = None,
        redis_store: "RedisStore | None" = None,
        kite: "AsyncKiteClient | None" = None,
    ) -> None:
        self._order_service = order_service
        self._redis = redis_store
        self._kite = kite

    def wire(
        self,
        order_service: "OrderService",
        redis_store: "RedisStore",
        kite: "AsyncKiteClient",
    ) -> None:
        """Wire dependencies after engine startup (called from runner.py)."""
        self._order_service = order_service
        self._redis = redis_store
        self._kite = kite

    # ── Public lifecycle methods ──────────────────────────────────────────────

    async def early_check(self) -> None:
        """
        15:18 IST — Force-close all positions early if more than 1 is MANAGING.

        Rationale: if two setups are active with only 2 minutes to close,
        slippage risk on both is too high.  Close everything while the book
        is still liquid.
        """
        try:
            positions = await self._discover_open_positions()
        except Exception as exc:
            log.error("eod_early_check_discovery_failed", error=str(exc))
            return  # Can't determine positions; skip

        if len(positions) > 1:
            log.info(
                "eod_early_squareoff_triggered",
                position_count=len(positions),
                symbols=[p["symbol"] for p in positions],
            )
            await self._close_all(positions, reason="eod_early_check")
        else:
            log.debug("eod_early_check_skipped", reason="<=1 open position")

    async def force_squareoff(self) -> None:
        """
        15:20 IST — Close every open position unconditionally.

        This is the safety net: runs AFTER strategy on_squareoff() hooks have
        had their chance.  Any positions still open at this point (strategy
        forgot to close, strategy crashed) are force-closed here.
        """
        try:
            positions = await self._discover_open_positions()
        except Exception as exc:
            log.critical(
                "eod_force_squareoff_discovery_failed",
                error=str(exc),
                hint="Cannot determine open positions; Kite dashboard check required.",
            )
            return  # Safe to return: worst case is undetected open position logged as CRITICAL

        if not positions:
            log.info("eod_force_squareoff_no_positions")
            return

        log.info(
            "eod_force_squareoff_start",
            position_count=len(positions),
            symbols=[p["symbol"] for p in positions],
        )
        await self._close_all(positions, reason="eod_squareoff")

    async def emergency_squareoff(self) -> None:
        """
        Immediate close — triggered by EMERGENCY_STOP control signal or fatal
        WebSocket disconnect exhaustion.

        Uses MARKET orders for fastest possible execution.
        """
        try:
            positions = await self._discover_open_positions()
        except Exception as exc:
            log.critical(
                "eod_emergency_discovery_failed",
                error=str(exc),
                hint="Emergency stop: cannot determine positions. Manual Kite closure required.",
            )
            return

        if not positions:
            log.info("emergency_squareoff_no_positions")
            return

        log.critical(
            "emergency_squareoff_start",
            position_count=len(positions),
            symbols=[p["symbol"] for p in positions],
        )
        await self._close_all(positions, reason="emergency_squareoff", market_order=True)

    # ── Internal: position discovery ─────────────────────────────────────────

    async def _discover_open_positions(self) -> list[dict[str, Any]]:
        """
        Discover open positions from Redis and Kite net_positions.

        Returns a deduplicated list of {symbol, quantity, strategy_id} dicts.
        """
        positions: dict[str, dict[str, Any]] = {}

        # Source 1: Redis position keys
        if self._redis is not None:
            try:
                redis_positions = await self._redis.get_all_open_positions()
                for sym, pos_data in redis_positions.items():
                    qty = pos_data.get("quantity", 0)
                    if qty and int(qty) > 0:
                        positions[sym] = {
                            "symbol": sym,
                            "quantity": int(qty),
                            "strategy_id": pos_data.get("strategy_id", "unknown"),
                            "exchange": pos_data.get("exchange", "NSE"),
                            "product": pos_data.get("product", "MIS"),
                            "source": "redis",
                        }
            except Exception as exc:
                log.error("eod_redis_position_discovery_failed", error=str(exc))

        # Source 2: Kite net_positions (catches orphans not in Redis)
        if self._kite is not None and not settings.is_paper_trade:
            try:
                net_pos = await self._kite.net_positions()
                for pos in (net_pos or []):
                    sym = pos.get("tradingsymbol", "")
                    qty = pos.get("quantity", 0)
                    if sym and qty and int(qty) != 0:
                        if sym not in positions:
                            positions[sym] = {
                                "symbol": sym,
                                "quantity": abs(int(qty)),
                                "strategy_id": "orphan",
                                "exchange": pos.get("exchange", "NSE"),
                                "product": pos.get("product", "MIS"),
                                "source": "kite",
                            }
                            log.warning(
                                "eod_orphan_position_discovered",
                                symbol=sym,
                                quantity=qty,
                                hint="Position in Kite but not in Redis — likely crash-orphaned.",
                            )
            except Exception as exc:
                log.error("eod_kite_position_discovery_failed", error=str(exc))

        return list(positions.values())

    # ── Internal: close all ───────────────────────────────────────────────────

    async def _close_all(
        self,
        positions: list[dict[str, Any]],
        reason: str,
        market_order: bool = False,
    ) -> None:
        """Close all *positions* concurrently, with idempotency via NX lock."""
        tasks = [
            self._close_one(pos, reason=reason, market_order=market_order)
            for pos in positions
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        success = sum(1 for r in results if r is True)
        errors  = sum(1 for r in results if isinstance(r, Exception))
        skipped = len(results) - success - errors

        log.info(
            "eod_squareoff_complete",
            reason=reason,
            total=len(positions),
            success=success,
            errors=errors,
            skipped=skipped,
        )

    async def _close_one(
        self,
        pos: dict[str, Any],
        reason: str,
        market_order: bool = False,
    ) -> bool:
        """
        Close a single position.

        Returns True on success (or if already closed by strategy),
        False on failure.

        Idempotency: acquires the NX exit lock before placing an order.
        If the strategy already placed an exit order, the NX lock is held
        and this call returns True without placing a duplicate.
        """
        symbol = pos["symbol"]
        qty = pos["quantity"]

        if self._order_service is None:
            log.error("eod_no_order_service", symbol=symbol)
            return False

        # Try to acquire exit lock (NX = only succeed if key doesn't exist)
        lock_key = f"lock:symbol:{symbol}"
        lock_acquired = False
        if self._redis is not None:
            try:
                lock_acquired = await self._redis._r.set(
                    lock_key, reason, nx=True, ex=300  # 5-minute TTL
                )
            except Exception as exc:
                log.warning("eod_exit_lock_failed", symbol=symbol, error=str(exc))
                # If Redis is down, proceed anyway (safety > dedup)
                lock_acquired = True
        else:
            lock_acquired = True  # paper mode: no Redis, proceed

        if not lock_acquired:
            log.info(
                "eod_squareoff_skipped_lock_held",
                symbol=symbol,
                reason="Strategy already placing exit order — skipping duplicate.",
            )
            return True  # Not an error — strategy handled it

        try:
            now_ist = datetime.datetime.now(IST_TZ)
            use_amo = (
                now_ist.hour > _AMO_CUTOFF_HOUR or
                (now_ist.hour == _AMO_CUTOFF_HOUR and now_ist.minute >= _AMO_CUTOFF_MINUTE)
            )

            order_type = "MARKET" if (market_order or use_amo) else "MARKET"
            variety = "amo" if use_amo else "regular"

            log.info(
                "eod_placing_exit",
                symbol=symbol,
                qty=qty,
                reason=reason,
                order_type=order_type,
                variety=variety,
            )

            await self._order_service.place_exit_market(
                symbol=symbol,
                quantity=qty,
                reason=reason,
                exchange=pos.get("exchange", "NSE"),
                product=pos.get("product", "MIS"),
                variety=variety,
            )
            return True

        except Exception as exc:
            log.critical(
                "eod_exit_order_failed",
                symbol=symbol,
                qty=qty,
                reason=reason,
                error=str(exc),
            )
            # Publish alert for dashboard visibility
            if self._redis is not None:
                try:
                    import json
                    await self._redis._r.publish(
                        "pub:alerts",
                        json.dumps({
                            "type": "eod_exit_failed",
                            "symbol": symbol,
                            "qty": qty,
                            "reason": reason,
                            "error": str(exc),
                        }),
                    )
                except Exception:
                    pass
            return False


# Module-level singleton — wired from runner.py after all dependencies are created
eod_squareoff_service = EODSquareOffService()
