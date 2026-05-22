"""
engine/orders/order_tracker.py — In-flight order registry and postback routing.

Maintains two registries:
  entry_order_registry: dict[order_id → symbol] for all LIMIT BUY entry orders
  sl_order_registry:    dict[order_id → symbol] for all SL-M SELL orders
    exit_order_registry:  dict[order_id → (symbol, close_reason)] for MARKET exit orders

On postback from AsyncKiteTicker.on_order_update:
  1. Identify order type by checking both registries
  2. Route to the appropriate SM method
  3. Write raw postback to order_events table in DB
  4. Remove from registry after final status (COMPLETE, REJECTED, CANCELLED)

Terminal statuses (Kite API v3 confirmed):
  COMPLETE, REJECTED, CANCELLED, CANCELLED AMO

Missing postback safety (spec §12.2):
  The 5-minute reconciliation loop in runner.py catches any missed postbacks.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from engine.store.db_writer import DbWriter
    from engine.strategy.coordinator import Coordinator

log = structlog.get_logger(__name__)

# Statuses that remove an order from the registry
_TERMINAL_STATUSES = frozenset({"COMPLETE", "REJECTED", "CANCELLED", "CANCELLED AMO"})


class OrderTracker:
    """
    Routes Kite WebSocket order postbacks to the correct SymbolStateMachine.

    Usage:
        order_tracker.register_entry(order_id, symbol)
        order_tracker.register_sl(order_id, symbol)
        order_tracker.register_exit(order_id, symbol, close_reason)
        await order_tracker.on_postback(postback_msg, coordinator, db_writer)
    """

    def __init__(self) -> None:
        self.entry_order_registry: dict[str, str] = {}  # order_id → symbol
        self.sl_order_registry: dict[str, str] = {}      # order_id → symbol
        self.exit_order_registry: dict[str, tuple[str, str]] = {}  # order_id → (symbol, reason)

    # ── Registry management ────────────────────────────────────────────────

    def register_entry(self, order_id: str, symbol: str) -> None:
        """Register a new entry order. Called immediately after place_entry()."""
        self.entry_order_registry[order_id] = symbol
        log.debug("entry_registered", order_id=order_id, symbol=symbol)

    def register_sl(self, order_id: str, symbol: str) -> None:
        """Register a new SL order. Called immediately after place_stop_loss()."""
        self.sl_order_registry[order_id] = symbol
        log.debug("sl_registered", order_id=order_id, symbol=symbol)

    def register_exit(self, order_id: str, symbol: str, close_reason: str) -> None:
        """Register a live exit MARKET order that should close on fill postback."""
        self.exit_order_registry[order_id] = (symbol, close_reason)
        log.debug(
            "exit_registered",
            order_id=order_id,
            symbol=symbol,
            close_reason=close_reason,
        )

    def unregister(self, order_id: str) -> str | None:
        """Remove an order from both registries. Returns the symbol if found."""
        symbol = self.entry_order_registry.pop(order_id, None)
        if symbol is None:
            symbol = self.sl_order_registry.pop(order_id, None)
        if symbol is None:
            meta = self.exit_order_registry.pop(order_id, None)
            symbol = meta[0] if meta else None
        return symbol

    def is_entry(self, order_id: str) -> bool:
        return order_id in self.entry_order_registry

    def is_sl(self, order_id: str) -> bool:
        return order_id in self.sl_order_registry

    def is_exit(self, order_id: str) -> bool:
        return order_id in self.exit_order_registry

    # ── Postback routing ──────────────────────────────────────────────────

    async def on_postback(
        self,
        message: dict[str, Any],
        coordinator: "Coordinator",
        db_writer: "DbWriter",
    ) -> None:
        """
        Route an order postback from AsyncKiteTicker.on_order_update().

        Message is the raw Kite kws.on_order_update dict.
        """
        order_id: str = message.get("order_id", "")
        status: str = message.get("status", "")
        symbol: str = message.get("tradingsymbol", "")

        log.debug(
            "order_postback_received",
            order_id=order_id,
            status=status,
            symbol=symbol,
        )

        # Always write raw postback to DB (spec §7.16)
        try:
            await db_writer.write_order_event(
                order_id=order_id,
                symbol=symbol,
                event_type=f"WS_POSTBACK_{status}",
                event_time=datetime.datetime.now(
                    __import__("pytz").timezone("Asia/Kolkata")
                ),
                average_price=message.get("average_price"),
                filled_quantity=message.get("filled_quantity"),
                status=status,
                status_message=message.get("status_message"),
                raw_payload=message,
            )
        except Exception as exc:
            log.warning("order_event_write_failed", order_id=order_id, error=str(exc))

        # Route to state machine
        if self.is_entry(order_id):
            await self._handle_entry_postback(order_id, status, message, coordinator)
        elif self.is_sl(order_id):
            await self._handle_sl_postback(order_id, status, message, coordinator)
        elif self.is_exit(order_id):
            await self._handle_exit_postback(order_id, status, message, coordinator)
        else:
            log.debug("postback_unknown_order", order_id=order_id, status=status)

        # Cleanup terminal status
        if status in _TERMINAL_STATUSES:
            removed_symbol = self.unregister(order_id)
            if removed_symbol:
                log.debug("order_deregistered", order_id=order_id, symbol=removed_symbol)

    async def _handle_entry_postback(
        self,
        order_id: str,
        status: str,
        message: dict[str, Any],
        coordinator: "Coordinator",
    ) -> None:
        """Route entry order postback to correct SM method."""
        symbol = self.entry_order_registry.get(order_id)
        if not symbol:
            return

        sm = coordinator.active_state_machines.get(symbol)
        if sm is None:
            log.warning("postback_sm_not_found", order_id=order_id, symbol=symbol)
            return

        if status == "COMPLETE":
            avg_price = float(message.get("average_price", 0.0))
            filled_qty = int(message.get("filled_quantity", 0))
            # Use exchange timestamp if available
            fill_time_raw = message.get("exchange_update_timestamp") or message.get("order_timestamp")
            try:
                fill_time = datetime.datetime.fromisoformat(str(fill_time_raw)) if fill_time_raw else datetime.datetime.now()
            except (ValueError, TypeError):
                fill_time = datetime.datetime.now()

            log.info(
                "entry_filled",
                order_id=order_id,
                symbol=symbol,
                avg_price=avg_price,
                filled_qty=filled_qty,
            )
            await sm.on_order_filled(order_id, avg_price, filled_qty, fill_time)

        elif status in ("REJECTED", "CANCELLED", "CANCELLED AMO"):
            status_msg = message.get("status_message", "")
            log.warning(
                "entry_rejected_or_cancelled",
                order_id=order_id,
                symbol=symbol,
                status=status,
                message=status_msg,
            )
            await sm.on_order_rejected(order_id, status_msg)

    async def _handle_sl_postback(
        self,
        order_id: str,
        status: str,
        message: dict[str, Any],
        coordinator: "Coordinator",
    ) -> None:
        """Route SL order postback to correct SM method."""
        symbol = self.sl_order_registry.get(order_id)
        if not symbol:
            return

        sm = coordinator.active_state_machines.get(symbol)
        if sm is None:
            log.warning("sl_postback_sm_not_found", order_id=order_id, symbol=symbol)
            return

        if status == "COMPLETE":
            avg_price = float(message.get("average_price", 0.0))
            log.info(
                "sl_triggered",
                order_id=order_id,
                symbol=symbol,
                avg_price=avg_price,
            )
            await sm.on_sl_triggered(order_id, avg_price)

        elif status == "REJECTED":
            # Critical: SL was rejected — position is UNPROTECTED.
            # DO NOT wait for the 5-minute reconciliation loop — fire immediate market sell.
            status_msg = message.get("status_message", "")
            log.critical(
                "sl_rejected_position_unprotected_emergency_close",
                order_id=order_id,
                symbol=symbol,
                message=status_msg,
            )
            sm = coordinator.active_state_machines.get(symbol)
            if sm is not None and sm.position is not None and coordinator._order_service is not None:
                retry_id = await coordinator._order_service.place_exit_market(
                    symbol=symbol,
                    quantity=sm.position.quantity,
                    reason="sl_rejected_emergency",
                )
                if retry_id:
                    self.register_exit(retry_id, symbol, "sl_rejected_emergency")
                    log.info(
                        "sl_rejection_emergency_exit_placed",
                        symbol=symbol,
                        exit_order_id=retry_id,
                    )

    async def _handle_exit_postback(
        self,
        order_id: str,
        status: str,
        message: dict[str, Any],
        coordinator: "Coordinator",
    ) -> None:
        """Route MARKET exit postbacks to SM close path."""
        meta = self.exit_order_registry.get(order_id)
        if not meta:
            return

        symbol, close_reason = meta
        sm = coordinator.active_state_machines.get(symbol)
        if sm is None:
            log.warning("exit_postback_sm_not_found", order_id=order_id, symbol=symbol)
            return

        if status == "COMPLETE":
            avg_price = float(message.get("average_price", 0.0))
            log.info(
                "exit_filled",
                order_id=order_id,
                symbol=symbol,
                avg_price=avg_price,
                reason=close_reason,
            )
            await sm._close_position(avg_price, order_id, close_reason or "CLOSED_MANUAL")

        elif status in ("REJECTED", "CANCELLED", "CANCELLED AMO"):
            status_msg = message.get("status_message", "")
            log.critical(
                "exit_rejected_or_cancelled",
                order_id=order_id,
                symbol=symbol,
                status=status,
                reason=close_reason,
                message=status_msg,
            )

            if coordinator._order_service is not None and sm.position is not None:
                retry_id = await coordinator._order_service.place_exit_market(
                    symbol=symbol,
                    quantity=sm.position.quantity,
                    reason=close_reason or "CLOSED_ERROR",
                )
                if retry_id:
                    self.register_exit(retry_id, symbol, close_reason or "CLOSED_ERROR")

    # ── Diagnostics ───────────────────────────────────────────────────────

    @property
    def monitored_order_count(self) -> int:
        return (
            len(self.entry_order_registry)
            + len(self.sl_order_registry)
            + len(self.exit_order_registry)
        )

    def __repr__(self) -> str:
        return (
            f"OrderTracker(entry={len(self.entry_order_registry)} "
            f"sl={len(self.sl_order_registry)} "
            f"exit={len(self.exit_order_registry)})"
        )


# Module-level singleton
order_tracker = OrderTracker()
