"""
engine/orders/order_service.py — All order placement, modification, and cancellation.

Handles the full exception hierarchy from kiteconnect:
  - InputException, PermissionException, OrderException → NON-RETRYABLE → return None
  - TokenException → NON-RETRYABLE CRITICAL → log CRITICAL, return None
  - NetworkException, GeneralException → RETRYABLE → exponential backoff (3 attempts)
  - HTTP 429 → wait 1.0s before retry
  - Any other Exception → log EXCEPTION with full traceback, return None

Paper mode:
  - place_entry() simulates fill immediately and calls sm.on_order_filled() directly
  - All real-order methods are available but gated behind is_paper_trade checks

Retry schedule (spec §9.5):
  attempt 1: immediate
  attempt 2: sleep 0.5s
  attempt 3: sleep 1.0s
  After 3 attempts: return None, log ERROR
"""

from __future__ import annotations

import asyncio
import datetime
import functools
import time
from typing import TYPE_CHECKING, Any

import structlog

from app.core.config import settings

if TYPE_CHECKING:
    from engine.kite.client import AsyncKiteClient
    from engine.orders.order_group import OrderGroup, OrderLeg
    from engine.strategy.state_machine import SymbolStateMachine

log = structlog.get_logger(__name__)
IST_TZ = __import__("pytz").timezone("Asia/Kolkata")

# Retry delays: attempt 0 = immediate, 1 = 0.5s, 2 = 1.0s
_RETRY_DELAYS = [0.0, 0.5, 1.0]
_RATE_LIMIT_DELAY = 1.0


def _is_kite_available() -> bool:
    """Return True if kiteconnect is installed (may not be in dev/test environments)."""
    try:
        import kiteconnect  # noqa: F401
        return True
    except ImportError:
        return False


def _get_kite_exceptions() -> tuple[type, ...]:
    """Import kite exception classes lazily — returns empty tuple if not installed."""
    try:
        from kiteconnect.exceptions import (
            InputException, PermissionException, OrderException,
            NetworkException, GeneralException, TokenException,
        )
        return (
            InputException, PermissionException, OrderException,
            NetworkException, GeneralException, TokenException,
        )
    except ImportError:
        return ()


async def _call_with_retry(
    kite: "AsyncKiteClient",
    method_name: str,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """
    Call a kite API method with retryable exception handling.

    Non-retryable exceptions (InputException, PermissionException, OrderException,
    TokenException) immediately return None.

    Retryable exceptions (NetworkException, GeneralException) are retried up to
    ORDER_MAX_RETRIES times with exponential backoff.
    """
    # Lazy import of kite exceptions to allow dev/test without kiteconnect installed
    try:
        from kiteconnect.exceptions import (
            InputException, PermissionException, OrderException,
            NetworkException, GeneralException, TokenException,
        )
        has_kite_exc = True
    except ImportError:
        has_kite_exc = False

    method = getattr(kite, method_name)
    last_exc: Exception | None = None

    for attempt in range(settings.ORDER_MAX_RETRIES):
        # Exponential backoff (except first attempt)
        if attempt > 0:
            delay = _RETRY_DELAYS[attempt] if attempt < len(_RETRY_DELAYS) else 1.0
            await asyncio.sleep(delay)

        try:
            result = await method(*args, **kwargs)
            return result

        except Exception as exc:
            exc_type = type(exc).__name__
            last_exc = exc

            if has_kite_exc:
                if isinstance(exc, TokenException):
                    log.critical(
                        "kite_token_expired_reauthenticate",
                        method=method_name,
                        error=str(exc),
                    )
                    return None  # Non-retryable, critical

                if isinstance(exc, (InputException, PermissionException, OrderException)):
                    log.error(
                        "kite_order_rejected_non_retryable",
                        method=method_name,
                        exception_type=exc_type,
                        error=str(exc),
                    )
                    return None  # Non-retryable

                if isinstance(exc, (NetworkException, GeneralException)):
                    log.warning(
                        "kite_retryable_error",
                        method=method_name,
                        attempt=attempt + 1,
                        max_retries=settings.ORDER_MAX_RETRIES,
                        error=str(exc),
                    )
                    # Handle HTTP 429 rate limiting
                    if "429" in str(exc) or "rate limit" in str(exc).lower():
                        log.warning("kite_rate_limited_sleeping", seconds=_RATE_LIMIT_DELAY)
                        await asyncio.sleep(_RATE_LIMIT_DELAY)
                    continue  # Retry

            # Unknown exception class — log and abort
            log.exception(
                "kite_unexpected_error",
                method=method_name,
                exception_type=exc_type,
                error=str(exc),
            )
            return None

    # All retries exhausted
    log.error(
        "kite_max_retries_exhausted",
        method=method_name,
        attempts=settings.ORDER_MAX_RETRIES,
        last_error=str(last_exc),
    )
    return None


class OrderService:
    """
    All order placement, modification, and cancellation.

    One instance shared across all state machines.
    Injected into SymbolStateMachine at construction time.
    Paper mode: simulates fills immediately without calling Kite API.
    """

    def __init__(self, kite: "AsyncKiteClient | None" = None) -> None:
        self._kite = kite

    def set_kite(self, kite: "AsyncKiteClient") -> None:
        """Wire in the Kite client (called after auth at startup)."""
        self._kite = kite

    # ── Entry Order (LIMIT BUY) ───────────────────────────────────────────────

    async def place_entry(
        self,
        symbol: str,
        limit_price: float,
        quantity: int,
        sm: "SymbolStateMachine | None" = None,
        exchange: str = "NSE",
        product: str = "MIS",
        tag: str = "IVBS",
    ) -> str | None:
        """
        Place a LIMIT BUY entry order.

        Paper mode: simulates fill immediately at limit_price × 1.001 and calls
        sm.on_order_filled() directly. Returns a fake PAPER_ order ID.

        Live mode: places a real Kite LIMIT order. Returns order_id or None on failure.

        Args:
            symbol:       NSE trading symbol.
            limit_price:  Entry limit price (close × 1.003 per spec §9.1).
            quantity:     Number of shares.
            sm:           SymbolStateMachine to call on_order_filled() in paper mode.

        Returns:
            order_id string on success, None on failure.
        """
        if settings.is_paper_trade:
            return await self._paper_entry(symbol, limit_price, quantity, sm)

        if self._kite is None:
            log.error("order_service_no_kite_client", symbol=symbol, method="place_entry")
            return None

        log.info(
            "placing_entry_order",
            symbol=symbol,
            limit=limit_price,
            qty=quantity,
        )

        result = await _call_with_retry(
            self._kite,
            "place_order",
            tradingsymbol=symbol,
            exchange=exchange,
            transaction_type="BUY",
            order_type="LIMIT",
            product=product,
            validity="DAY",
            quantity=quantity,
            price=limit_price,
            tag=tag,
            autoslice=True,
            variety="regular",
        )

        if result:
            log.info(
                "entry_order_placed",
                symbol=symbol,
                order_id=result,
                limit=limit_price,
                qty=quantity,
            )
        return result

    async def _paper_entry(
        self,
        symbol: str,
        limit_price: float,
        quantity: int,
        sm: "SymbolStateMachine | None",
    ) -> str | None:
        """
        Simulate a fill using REAL market data.

        Fill price is based on the current live LTP from the WebSocket stream.
        If no live LTP is available, falls back to limit_price × 1.001 (0.1% slippage).

        Research basis for slippage model:
          - NSE equity intraday: normal slippage 0.0-0.2% for liquid stocks
          - For less liquid stocks: slippage can be 0.2-0.5%
          - We use 0.1% as a conservative average for paper trade simulation
          - The live LTP always produces a more realistic fill than a fixed multiplier

        The paper trade simulates real execution conditions so that performance
        metrics (win rate, avg loss, drawdown) are meaningful when compared
        to live trading results.
        """
        import time as _time

        # Try to get the real current LTP from the WebSocket feed
        fill_price: float
        ltp: float | None = None  # initialise before the try block (name-before-assignment guard)
        try:
            # Redis is injected into the module via the engine runner startup.
            # Import here to avoid circular dependency at module load time.
            from engine.store.redis_store import RedisStore
            from app.store.redis_client import get_redis
            redis_client = get_redis()
            if redis_client is not None:
                rs = RedisStore(redis_client)
                ltp = await rs.get_last_ltp(symbol)
                if ltp is not None and ltp > 0:
                    # Use live LTP with realistic slippage: 0.05% for paper simulation
                    # This represents the typical bid-ask spread + small adverse selection
                    fill_price = round(ltp * 1.0005, 2)
                else:
                    fill_price = round(limit_price * 1.001, 2)
            else:
                fill_price = round(limit_price * 1.001, 2)
        except Exception:
            # Fallback: limit_price with conservative slippage
            fill_price = round(limit_price * 1.001, 2)

        order_id = f"PAPER_{symbol}_{int(_time.time())}"

        log.info(
            "paper_entry_simulated",
            symbol=symbol,
            limit=limit_price,
            fill=fill_price,
            qty=quantity,
            order_id=order_id,
        )

        # Write paper order event to DB
        try:
            from engine.store.db_writer import db_writer
            await db_writer.write_order_event(
                order_id=order_id,
                symbol=symbol,
                event_type="PAPER_ENTRY",
                event_time=datetime.datetime.now(IST_TZ),
                status="PAPER_FILLED",
                price=fill_price,
                quantity=quantity,
                filled_quantity=quantity,
                average_price=fill_price,
                status_message=f"Paper fill at LTP={ltp or limit_price}",
                trade_mode="PAPER",
            )
        except Exception:
            pass

        if sm is not None:
            # Simulate fill asynchronously (preserves event loop flow)
            await sm.on_order_filled(
                order_id=order_id,
                fill_price=fill_price,
                fill_qty=quantity,
                fill_time=datetime.datetime.now(IST_TZ),
            )

        return order_id

    # ── Stop Loss Order (SL-M SELL) ───────────────────────────────────────────

    async def place_stop_loss(
        self,
        symbol: str,
        quantity: int,
        trigger_price: float,
        exchange: str = "NSE",
        product: str = "MIS",
        tag: str = "IVBS_SL",
    ) -> str | None:
        """
        Place an SL-M (stop-loss market) SELL order.

        CRITICAL: SL-M has NO price field — omitting it is spec-mandated (§9.2).
        Including a price field would silently downgrade to SL-Limit on Kite.

        IMPORTANT: Callers MUST pass `exchange` and `product` explicitly for any
        asset class other than NSE equity. Defaults are NSE/MIS which work for
        IVBS equity intraday only. For NFO (options/futures) pass exchange="NFO"
        and product="MIS" or "NRML" as appropriate — using the wrong exchange
        will cause Kite to reject the order.

        Paper mode: returns a fake SL order ID. SL checking happens via on_tick().
        """
        if settings.is_paper_trade:
            order_id = f"PAPER_SL_{symbol}_{int(time.time())}"
            log.info(
                "paper_sl_order_registered",
                symbol=symbol,
                trigger=trigger_price,
                qty=quantity,
                order_id=order_id,
            )
            return order_id

        if self._kite is None:
            log.error("order_service_no_kite_client", symbol=symbol, method="place_stop_loss")
            return None

        log.info(
            "placing_sl_order",
            symbol=symbol,
            trigger=trigger_price,
            qty=quantity,
        )

        result = await _call_with_retry(
            self._kite,
            "place_order",
            tradingsymbol=symbol,
            exchange=exchange,
            transaction_type="SELL",
            order_type="SL-M",
            product=product,
            validity="DAY",
            quantity=quantity,
            trigger_price=trigger_price,
            tag=tag,
            variety="regular",
            market_protection=-1,
            # NO price field for SL-M (spec §9.2)
        )

        if result:
            log.info("sl_order_placed", symbol=symbol, order_id=result, trigger=trigger_price)
        return result

    # ── SL Modification (Trailing) ────────────────────────────────────────────

    async def modify_stop_loss(
        self,
        order_id: str,
        new_trigger: float,
        symbol: str = "",
        sm: "SymbolStateMachine | None" = None,
    ) -> bool:
        """
        Modify the trigger price of an existing SL-M order.

        Paper mode: just log the trail — actual SL check happens via on_tick().

        On InputException during live modify:
          The SL may have already triggered (race condition).
          Per spec §9.3: log warning and fetch order status to determine actual state.
          If COMPLETE → treat as SL hit and route to sm.on_sl_triggered().

        Returns True on success, False on failure.
        """
        if settings.is_paper_trade:
            log.info(
                "paper_sl_modified",
                order_id=order_id,
                new_trigger=new_trigger,
            )
            return True

        if self._kite is None:
            log.error("order_service_no_kite_client", method="modify_stop_loss")
            return False

        try:
            await _call_with_retry(
                self._kite,
                "modify_order",
                variety="regular",
                order_id=order_id,
                trigger_price=new_trigger,
                # NO price field for SL-M modification (spec §9.3)
            )
            log.info("sl_modified", order_id=order_id, new_trigger=new_trigger)
            return True

        except Exception as exc:
            # InputException on modify → SL may have already been triggered
            log.warning(
                "sl_modify_failed_may_have_triggered",
                order_id=order_id,
                symbol=symbol,
                error=str(exc),
            )
            # Check actual order status
            if sm is not None and self._kite is not None:
                await self._handle_sl_modify_race(order_id, symbol, sm)
            return False

    async def _handle_sl_modify_race(
        self,
        order_id: str,
        symbol: str,
        sm: "SymbolStateMachine",
    ) -> None:
        """Check if SL was already triggered when modify failed."""
        try:
            orders = await _call_with_retry(self._kite, "orders")  # type: ignore[arg-type]
            if not orders:
                return
            for order in orders:
                if order.get("order_id") == order_id:
                    if order.get("status") == "COMPLETE":
                        avg_price = order.get("average_price", 0.0)
                        log.info(
                            "sl_triggered_detected_via_order_check",
                            order_id=order_id,
                            avg_price=avg_price,
                        )
                        await sm.on_sl_triggered(order_id, avg_price)
                    break
        except Exception as exc:
            log.error("sl_modify_race_check_failed", error=str(exc))

    # ── Exit Market Order (MARKET SELL) ───────────────────────────────────────

    async def place_exit_market(
        self,
        symbol: str,
        quantity: int,
        reason: str = "exit",
        exchange: str = "NSE",
        product: str = "MIS",
        tag: str = "IVBS_EXIT",
    ) -> str | None:
        """
        Place a MARKET SELL exit order.

        Paper mode: returns a fake exit order ID. P&L settlement happens in SM.

        Returns order_id on success, None on failure.
        """
        if settings.is_paper_trade:
            order_id = f"PAPER_EXIT_{symbol}_{int(time.time())}"
            log.info(
                "paper_exit_simulated",
                symbol=symbol,
                qty=quantity,
                reason=reason,
                order_id=order_id,
            )
            return order_id

        if self._kite is None:
            log.error("order_service_no_kite_client", symbol=symbol, method="place_exit_market")
            return None

        log.info("placing_exit_market_order", symbol=symbol, qty=quantity, reason=reason)

        result = await _call_with_retry(
            self._kite,
            "place_order",
            tradingsymbol=symbol,
            exchange=exchange,
            transaction_type="SELL",
            order_type="MARKET",
            product=product,
            validity="DAY",
            quantity=quantity,
            tag=tag,
            variety="regular",
            market_protection=-1,
        )

        if result:
            log.info("exit_order_placed", symbol=symbol, order_id=result, reason=reason)
        return result

    # ── Entry Order Modification (limit widen) ────────────────────────────────

    async def modify_entry_order(self, order_id: str, price: float) -> bool:
        """
        Modify the limit price of an existing entry order (used for limit widen at +5s).

        Paper mode: always succeeds (no exchange order to modify).
        Live mode: calls kite.modify_order() with retry wrapper.

        Returns True on success, False on failure.
        """
        if settings.is_paper_trade:
            log.info("paper_entry_order_widen_skipped", order_id=order_id, price=price)
            return True

        if self._kite is None:
            log.error("order_service_no_kite_client", method="modify_entry_order")
            return False

        result = await _call_with_retry(
            self._kite,
            "modify_order",
            variety="regular",
            order_id=order_id,
            price=price,
        )
        if result is not None:
            log.info("entry_order_widened", order_id=order_id, new_price=price)
            return True
        log.warning("entry_order_widen_failed", order_id=order_id, price=price)
        return False

    # ── Cancel Order ──────────────────────────────────────────────────────────

    async def cancel_order(self, order_id: str, symbol: str = "") -> bool:
        """
        Cancel an open order by order_id.

        Paper mode: always succeeds (just log).
        Live mode: calls kite.cancel_order() with retry.

        Returns True on success, False on failure (order may already be filled/cancelled).
        """
        if settings.is_paper_trade:
            log.info("paper_order_cancelled", order_id=order_id)
            return True

        if self._kite is None:
            log.error("order_service_no_kite_client", method="cancel_order")
            return False

        result = await _call_with_retry(
            self._kite,
            "cancel_order",
            variety="regular",
            order_id=order_id,
        )

        success = result is not None
        if success:
            log.info("order_cancelled", order_id=order_id, symbol=symbol)
        else:
            log.warning("order_cancel_failed", order_id=order_id, symbol=symbol)
        return success


    # ── Market Exit (EOD / Emergency) ────────────────────────────────────────

    async def place_exit_market(
        self,
        symbol: str,
        quantity: int,
        reason: str = "eod_squareoff",
        exchange: str = "NSE",
        product: str = "MIS",
        variety: str = "regular",
        tag: str = "EOD",
    ) -> str | None:
        """
        Place a MARKET SELL exit order.

        Used by EODSquareOffService for force-close and emergency exits.
        Does NOT require a SymbolStateMachine — it's a direct market order.

        Paper mode: logs the exit, returns a fake PAPER_ order ID.
        Live mode: places a real MARKET SELL via Kite API.

        Args:
            symbol:   NSE/NFO tradingsymbol.
            quantity: Number of shares/lots to sell.
            reason:   Log annotation for audit trail.
            exchange: "NSE" or "NFO".
            product:  "MIS" (intraday) or "NRML" (F&O overnight).
            variety:  "regular" or "amo" (after-market order).
            tag:      Kite order tag (max 20 chars).

        Returns:
            order_id string or None on failure.
        """
        if settings.is_paper_trade:
            fake_id = f"PAPER_EXIT_{symbol}_{reason}"
            log.info(
                "paper_exit_market_placed",
                symbol=symbol, quantity=quantity, reason=reason,
            )
            return fake_id

        if self._kite is None:
            log.error("order_service_no_kite_client", symbol=symbol, method="place_exit_market")
            return None

        log.info(
            "placing_exit_market_order",
            symbol=symbol, quantity=quantity, reason=reason,
            variety=variety, exchange=exchange, product=product,
        )

        result = await _call_with_retry(
            self._kite,
            "place_order",
            variety=variety,
            tradingsymbol=symbol,
            exchange=exchange,
            transaction_type="SELL",
            order_type="MARKET",
            product=product,
            validity="DAY",
            quantity=quantity,
            tag=tag[:20],  # Kite tag max 20 chars
        )

        if result:
            log.info(
                "exit_market_order_placed",
                symbol=symbol, order_id=result, reason=reason,
            )
        else:
            log.critical(
                "exit_market_order_failed",
                symbol=symbol, quantity=quantity, reason=reason,
            )
        return result

    # ── Multi-Leg Order Group ────────────────────────────────────────────────

    async def place_order_group(
        self,
        group: "OrderGroup",
        db_writer: Any = None,
    ) -> "OrderGroup":
        """
        Place all legs of an OrderGroup sequentially and track status.

        Leg ordering: BUY legs first, then SELL legs (reduces unhedged window).
        On any leg failure: checks group.on_unhedged policy and either:
          - FLATTEN: places a market exit for filled legs (auto-flatten).
          - ALERT_ONLY: logs CRITICAL + marks group PARTIAL.

        Args:
            group:     OrderGroup with all legs defined.
            db_writer: Optional DbWriter to record order_group_id on events.

        Returns:
            The same OrderGroup with legs' order_ids and statuses updated.
        """
        from engine.orders.order_group import OnUnhedged, GroupStatus

        # Sort: BUY legs first (reduces unhedged window for spreads)
        ordered = sorted(group.legs, key=lambda l: (0 if l.side == "BUY" else 1))

        for leg in ordered:
            order_id = await self._place_single_leg(leg, group.group_id)
            leg.order_id = order_id

            if order_id is None:
                leg.status = "REJECTED"
                leg.filled_quantity = 0
            else:
                # Paper mode: immediate fill; live: async fill via postback
                if settings.is_paper_trade:
                    leg.status = "COMPLETE"
                    leg.filled_quantity = leg.quantity
                    leg.average_price = leg.price or 0.0
                else:
                    leg.status = "OPEN"

        group.update_status()

        # Handle unhedged legs
        unhedged = group.unhedged_legs
        if unhedged:
            if group.on_unhedged == OnUnhedged.FLATTEN:
                await self._flatten_unhedged(group, unhedged)
            else:
                log.critical(
                    "order_group_unhedged_position",
                    group_id=group.group_id,
                    strategy_id=group.strategy_id,
                    unhedged_leg_indices=unhedged,
                    policy=group.on_unhedged,
                )
                from engine.store.redis_store import RedisStore
                from app.core.config import settings
                r = RedisStore(host=settings.REDIS_HOST)
                await r.publish_alert({
                    "level": "error",
                    "message": f"UNHEDGED POSITION ALERT: Strategy {group.strategy_id} has unhedged legs in group {group.group_id}!",
                    "source": "order_service"
                })
        log.info(
            "order_group_placed",
            group_id=group.group_id,
            strategy_id=group.strategy_id,
            leg_count=len(group.legs),
            status=group.status,
        )
        return group

    async def _place_single_leg(
        self, leg: "OrderLeg", group_id: str
    ) -> str | None:
        """Place one leg of a group. Returns order_id or None."""
        if settings.is_paper_trade:
            fake_id = f"PAPER_GRP_{group_id[:8]}_{leg.symbol}_{leg.side}"
            log.info(
                "paper_group_leg_placed",
                group_id=group_id,
                symbol=leg.symbol,
                side=leg.side,
                qty=leg.quantity,
                order_id=fake_id,
            )
            return fake_id

        if self._kite is None:
            log.error("order_service_no_kite_client", method="_place_single_leg")
            return None

        kwargs: dict[str, Any] = dict(
            variety=leg.variety,
            tradingsymbol=leg.symbol,
            exchange=leg.exchange,
            transaction_type=leg.side,
            order_type=leg.order_type,
            product=leg.product,
            validity="DAY",
            quantity=leg.quantity,
            tag=(leg.tag or group_id[:8])[:20],
        )
        if leg.order_type in ("LIMIT", "SL") and leg.price is not None:
            kwargs["price"] = leg.price
        if leg.order_type in ("SL-M", "SL") and leg.trigger_price is not None:
            kwargs["trigger_price"] = leg.trigger_price

        return await _call_with_retry(self._kite, "place_order", **kwargs)

    async def _flatten_unhedged(
        self,
        group: "OrderGroup",
        unhedged_indices: list[int],
    ) -> None:
        """Auto-flatten legs that are filled but whose counterpart failed."""
        for i in unhedged_indices:
            leg = group.legs[i]
            if leg.filled_quantity > 0:
                log.warning(
                    "order_group_auto_flatten",
                    group_id=group.group_id,
                    symbol=leg.symbol,
                    qty=leg.filled_quantity,
                    side=leg.counterpart_side,
                )
                await self.place_exit_market(
                    symbol=leg.symbol,
                    quantity=leg.filled_quantity,
                    reason=f"auto_flatten:group_{group.group_id[:8]}",
                    exchange=leg.exchange,
                    product=leg.product,
                    tag="FLATTEN",
                )


    # ── Freeze-quantity splitting ──────────────────────────────────────────────

    def _split_for_freeze(self, symbol: str, qty: int) -> list[int]:
        """
        Split *qty* into sub-orders each ≤ NSE freeze quantity for *symbol*.

        Returns a list of leg sizes that together sum to *qty*.
        If qty <= freeze_qty, returns [qty] (no split needed).

        Example:
            freeze_qty = 1800, qty = 4200
            → [1800, 1800, 600]

        Edge cases:
            - qty == 0: returns [0] (upstream Quantity rule will block this)
            - InstrumentMaster not loaded: freeze_qty defaults to conservative value
        """
        try:
            from engine.market.instrument_master import instrument_master
            freeze_qty = instrument_master.get_freeze_quantity(symbol)
        except Exception:
            freeze_qty = 2_500  # Conservative fallback if master not available

        if qty <= freeze_qty:
            return [qty]

        splits: list[int] = []
        remaining = qty
        while remaining > 0:
            chunk = min(remaining, freeze_qty)
            splits.append(chunk)
            remaining -= chunk
        return splits


# Module-level singleton — wire kite client in at startup via order_service.set_kite()
order_service = OrderService()
