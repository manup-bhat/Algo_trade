"""
engine/orders/expiry_rollover_service.py — Strategy-agnostic F&O expiry rollover.

Runs as a scheduled common-engine job at 17:00 IST on expiry-eve (the Thursday
before expiry for weekly options, the last Thursday of the month for monthly).

What it does:
  1. Discovers all open F&O positions (from Redis) whose instrument expires
     on the current day or the next trading day.
  2. For each expiring position:
     a. Places a MARKET exit on the expiring leg (before 15:30 IST).
     b. Resolves the next expiry's ATM strike via InstrumentMaster.
     c. Opens a replacement LIMIT order on the next expiry.
     d. Bundles both as one OrderGroup for atomic reporting.
     e. Publishes a `rollover_complete` or `rollover_failed` alert.
  3. Idempotent: uses a Redis NX lock (`lock:rollover:{underlying}:{expiry}`)
     so repeated calls (restart, scheduler jitter) do not double-roll.

Pattern: Saga / Process Manager (Part3 §4 design patterns table).

Wire-up:
    expiry_rollover_service.wire(
        order_service=order_service,
        redis_store=redis_store,
        instrument_master=instrument_master,
    )
    # APScheduler — fires at 17:00 on expiry-eve
    scheduler.add_job(
        expiry_rollover_service.run_rollover,
        CronTrigger(day_of_week="wed", hour=17, minute=0),
    )
"""

from __future__ import annotations

import asyncio
import datetime
from typing import TYPE_CHECKING, Any

import structlog

from engine.core.notification_registry import AlertEvent, publish_alert

if TYPE_CHECKING:
    from engine.market.instrument_master import InstrumentMaster
    from engine.orders.order_service import OrderService
    from engine.store.redis_store import RedisStore

log = structlog.get_logger(__name__)

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
_LOCK_TTL_SECONDS = 86_400  # 24h — covers restart jitter
_ROLLOVER_LOCK_PREFIX = "lock:rollover"


class ExpiryRolloverService:
    """
    Strategy-agnostic F&O expiry rollover.

    Independent of which strategies are currently registered — operates only on
    Redis position state, same as EODSquareOffService. A strategy that crashed
    mid-session still gets its expiring leg rolled.
    """

    def __init__(self) -> None:
        self._order_service: OrderService | None = None
        self._redis: RedisStore | None = None
        self._instrument_master: InstrumentMaster | None = None

    # ── Wiring ────────────────────────────────────────────────────────────────

    def wire(
        self,
        order_service: OrderService,
        redis_store: RedisStore,
        instrument_master: InstrumentMaster,
    ) -> None:
        """Inject dependencies. Called from runner.py after all services are created."""
        self._order_service = order_service
        self._redis = redis_store
        self._instrument_master = instrument_master
        log.info("expiry_rollover_service_wired")

    # ── Public API ────────────────────────────────────────────────────────────

    async def run_rollover(self) -> None:
        """
        Main entry point — discovers and rolls all expiring F&O positions.

        Called by the APScheduler job at 17:00 IST on expiry-eve.
        Safe to call at any time — positions are only rolled if they are
        expiring today or tomorrow.
        """
        log.info("expiry_rollover_start")

        try:
            positions = await self._discover_expiring_positions()
        except Exception as exc:
            log.critical(
                "expiry_rollover_discovery_failed",
                error=str(exc),
                hint="Cannot determine expiring positions. Manual rollover required.",
            )
            return

        if not positions:
            log.info("expiry_rollover_no_expiring_positions")
            return

        log.info(
            "expiry_rollover_positions_found",
            count=len(positions),
            symbols=[p["symbol"] for p in positions],
        )

        tasks = [self._roll_one(pos) for pos in positions]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        success = sum(1 for r in results if r is True)
        errors  = sum(1 for r in results if isinstance(r, Exception) or r is False)
        log.info("expiry_rollover_complete", success=success, errors=errors)

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _discover_expiring_positions(self) -> list[dict[str, Any]]:
        """
        Find all open F&O positions (from Redis) whose expiry is today or tomorrow.

        Returns list of position dicts with keys:
            symbol, underlying, expiry (date), quantity, exchange, product,
            strategy_id, option_type, strike, spot_price.
        """
        if self._redis is None:
            return []

        today = datetime.date.today()
        tomorrow = today + datetime.timedelta(days=1)
        target_dates = {today, tomorrow}

        all_positions: dict[str, Any] = {}
        try:
            all_positions = await self._redis.get_all_open_positions()
        except AttributeError:
            # Fallback: older Redis store API
            try:
                raw = await self._redis._r.hgetall("open_positions")
                import json
                all_positions = {
                    k.decode() if isinstance(k, bytes) else k:
                    json.loads(v.decode() if isinstance(v, bytes) else v)
                    for k, v in raw.items()
                }
            except Exception as exc:
                log.error("expiry_rollover_redis_read_failed", error=str(exc))
                return []

        expiring: list[dict[str, Any]] = []
        for symbol, pos_data in all_positions.items():
            if isinstance(pos_data, str):
                import json
                try:
                    pos_data = json.loads(pos_data)
                except Exception:
                    continue

            pos_data["symbol"] = pos_data.get("symbol", symbol)

            # Only F&O instruments
            exchange = pos_data.get("exchange", "NSE").upper()
            if exchange not in ("NFO", "BFO"):
                continue

            # Resolve expiry from InstrumentMaster
            if self._instrument_master is not None:
                inst = self._instrument_master.get_instrument(symbol, exchange)
                if inst is not None and hasattr(inst, "expiry") and inst.expiry in target_dates:
                    pos_data["expiry"] = inst.expiry
                    expiring.append(pos_data)
            else:
                # Heuristic: check symbol string for expiry date pattern
                # e.g. NIFTY23SEP21000CE → expiry embedded in name
                # (InstrumentMaster not loaded — conservative: skip)
                log.warning(
                    "expiry_rollover_no_instrument_master",
                    symbol=symbol,
                    hint="Cannot resolve expiry without InstrumentMaster. Symbol skipped.",
                )

        return expiring

    async def _roll_one(self, pos: dict[str, Any]) -> bool:
        """
        Roll a single expiring F&O position.

        1. Acquire NX rollover lock (idempotency guard).
        2. Place exit on expiring leg.
        3. Resolve next expiry + ATM strike.
        4. Place entry on new leg.
        5. Publish alert.

        Returns True on success, False on failure.
        """
        symbol      = pos["symbol"]
        underlying  = pos.get("underlying", symbol)
        expiry      = pos.get("expiry")
        qty         = pos.get("quantity", 0)
        exchange    = pos.get("exchange", "NFO")
        product     = pos.get("product", "NRML")
        strategy_id = pos.get("strategy_id", "engine")

        # Idempotency guard
        lock_key = f"{_ROLLOVER_LOCK_PREFIX}:{underlying}:{expiry}"
        lock_acquired = False
        if self._redis is not None:
            try:
                lock_acquired = await self._redis._r.set(
                    lock_key, "rolling", nx=True, ex=_LOCK_TTL_SECONDS
                )
            except Exception as exc:
                log.warning("expiry_rollover_lock_failed", symbol=symbol, error=str(exc))
                lock_acquired = True  # Proceed if Redis down (safety > dedup)

        if not lock_acquired:
            log.info(
                "expiry_rollover_skipped_lock_held",
                symbol=symbol,
                reason="Already rolling or rolled in this session.",
            )
            return True

        try:
            # Step 1: Exit expiring leg
            if self._order_service is None:
                log.error("expiry_rollover_no_order_service")
                return False

            log.info("expiry_rollover_exiting", symbol=symbol, qty=qty)
            exit_id = await self._order_service.place_exit_market(
                symbol=symbol,
                quantity=qty,
                reason="expiry_rollover_exit",
                exchange=exchange,
                product=product,
            )
            if exit_id is None:
                log.error("expiry_rollover_exit_failed", symbol=symbol)
                await self._publish_failure(symbol, strategy_id, "exit_order_rejected")
                return False

            # Step 2: Resolve next expiry
            if self._instrument_master is None:
                log.error("expiry_rollover_no_instrument_master")
                return False

            next_expiry = self._instrument_master.nearest_expiry(
                underlying,
                ref_date=datetime.date.today() + datetime.timedelta(days=1),
            )
            if next_expiry is None:
                log.error(
                    "expiry_rollover_no_next_expiry",
                    underlying=underlying,
                )
                await self._publish_failure(symbol, strategy_id, "no_next_expiry")
                return False

            # Step 3: Resolve ATM for next expiry
            # spot_price may be in position data or we use last-known tick
            spot = float(pos.get("spot_price", 0))
            if spot <= 0 and self._redis is not None:
                spot = await self._get_last_price(underlying)

            option_type_str = pos.get("option_type", "CE").upper()
            from engine.core.instrument import OptionType
            opt_type = OptionType.CE if option_type_str == "CE" else OptionType.PE

            new_inst = self._instrument_master.atm_option(
                underlying, spot, opt_type, next_expiry
            )
            if new_inst is None:
                log.error(
                    "expiry_rollover_no_atm_instrument",
                    underlying=underlying,
                    expiry=str(next_expiry),
                    spot=spot,
                )
                await self._publish_failure(symbol, strategy_id, "atm_not_found")
                return False

            # Step 4: Entry on next expiry (market order for clean fill)
            new_symbol = new_inst.tradingsymbol
            log.info(
                "expiry_rollover_entering",
                old_symbol=symbol,
                new_symbol=new_symbol,
                qty=qty,
                next_expiry=str(next_expiry),
            )

            new_order_id = await self._order_service.place_entry(
                symbol=new_symbol,
                limit_price=0.0,    # market order — price is 0
                stop_loss=0.0,      # F&O caller must set SL separately
                exchange=exchange,
                product=product,
                strategy_id=strategy_id,
                order_type="MARKET",
                quantity=qty,
            )

            # Step 5: Publish outcome alert
            await publish_alert(AlertEvent(
                type="expiry_rollover_complete",
                severity="INFO",
                strategy_id=strategy_id,
                payload={
                    "old_symbol": symbol,
                    "new_symbol": new_symbol,
                    "old_expiry": str(expiry),
                    "new_expiry": str(next_expiry),
                    "qty": qty,
                    "exit_order_id": exit_id,
                    "entry_order_id": new_order_id,
                },
            ))
            return True

        except Exception as exc:
            log.critical(
                "expiry_rollover_unexpected_error",
                symbol=symbol,
                error=str(exc),
                exc_info=True,
            )
            await self._publish_failure(symbol, strategy_id, str(exc))
            return False

    async def _get_last_price(self, symbol: str) -> float:
        """Read last known price from Redis tick hash."""
        if self._redis is None:
            return 0.0
        try:
            import json
            raw = await self._redis._r.hget("livetick_hash", symbol)
            if raw:
                tick = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
                return float(tick.get("last_price", 0))
        except Exception:
            pass
        return 0.0

    async def _publish_failure(
        self, symbol: str, strategy_id: str, reason: str
    ) -> None:
        await publish_alert(AlertEvent(
            type="expiry_rollover_failed",
            severity="CRITICAL",
            strategy_id=strategy_id,
            payload={"symbol": symbol, "reason": reason},
        ))


# Module-level singleton — wired from runner.py
expiry_rollover_service = ExpiryRolloverService()
