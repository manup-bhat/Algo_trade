"""
engine/orders/fill_timeout.py — Cancel unfilled entry orders after ORDER_FILL_TIMEOUT_SECONDS.

Spec §7.17:
  - start_timeout(): creates a named asyncio.Task (Python 3.12+ name arg)
  - If SM is still ACTION_PENDING after timeout → cancel the order
  - cancel_timeout(): called when fill postback arrives (cleanup)

Named tasks appear in asyncio.all_tasks() — useful for debugging hung entries.

Paper mode: timeout is bypassed because fills are simulated immediately.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog

from app.core.config import settings

if TYPE_CHECKING:
    from engine.orders.order_service import OrderService
    from engine.strategy.state_machine import StrategyState, SymbolStateMachine

log = structlog.get_logger(__name__)


class FillTimeoutManager:
    """
    Manages per-order fill timeout tasks.

    One instance shared across all state machines.
    All tasks are tracked in _tasks dict so they can be cancelled on fill.

    Usage:
        task = fill_timeout_manager.start_timeout(order_id, sm, order_service)
        fill_timeout_manager.cancel_timeout(order_id)  # on fill/reject postback
    """

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}

    def start_timeout(
        self,
        order_id: str,
        sm: "SymbolStateMachine",
        order_service: "OrderService",
    ) -> asyncio.Task:
        """
        Start a background timeout task for an entry order.
        The task will cancel the order if SM is still ACTION_PENDING after timeout.

        Paper mode: issues warning but doesn't cancel (fills are immediate).
        """
        task = asyncio.create_task(
            self._timeout_handler(order_id, sm, order_service),
            name=f"fill_timeout_{order_id}",
        )
        self._tasks[order_id] = task
        log.debug(
            "fill_timeout_started",
            order_id=order_id,
            symbol=sm.symbol,
            timeout_sec=settings.ORDER_FILL_TIMEOUT_SECONDS,
        )
        return task

    async def _timeout_handler(
        self,
        order_id: str,
        sm: "SymbolStateMachine",
        order_service: "OrderService",
    ) -> None:
        """
        Background task: wait for timeout then cancel if unfilled.
        Cleans itself from _tasks on completion.
        """
        try:
            await asyncio.sleep(settings.ORDER_FILL_TIMEOUT_SECONDS)

            # Import here to avoid circular
            from engine.strategy.state_machine import StrategyState

            if sm.state == StrategyState.ACTION_PENDING:
                log.warning(
                    "fill_timeout_triggered",
                    order_id=order_id,
                    symbol=sm.symbol,
                    timeout_sec=settings.ORDER_FILL_TIMEOUT_SECONDS,
                )
                cancel_ok = await order_service.cancel_order(order_id, symbol=sm.symbol)
                if cancel_ok:
                    await sm._handle_fill_timeout(order_id)
                else:
                    log.error(
                        "fill_timeout_cancel_failed",
                        order_id=order_id,
                        symbol=sm.symbol,
                    )
            else:
                log.debug(
                    "fill_timeout_elapsed_but_state_changed",
                    order_id=order_id,
                    symbol=sm.symbol,
                    current_state=sm.state.value,
                )
        except asyncio.CancelledError:
            # Expected — cancel_timeout() was called (fill arrived)
            pass
        finally:
            self._tasks.pop(order_id, None)

    def cancel_timeout(self, order_id: str) -> None:
        """
        Cancel the pending timeout task for an order that has been filled or rejected.
        Safe to call if no timeout exists for the order (no-op).
        """
        task = self._tasks.pop(order_id, None)
        if task is not None and not task.done():
            task.cancel()
            log.debug("fill_timeout_cancelled", order_id=order_id)

    def cancel_all(self) -> None:
        """Cancel all pending timeouts. Called on emergency stop / squareoff."""
        for order_id, task in list(self._tasks.items()):
            if not task.done():
                task.cancel()
        self._tasks.clear()

    @property
    def pending_count(self) -> int:
        return len(self._tasks)


# Module-level singleton
fill_timeout_manager = FillTimeoutManager()
