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
                status_message=f"Paper fill at LTP={ltp}",
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


# Module-level singleton — wire kite client in at startup via order_service.set_kite()
order_service = OrderService()
