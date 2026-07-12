"""
engine/backtest/sim_broker.py — deterministic simulated broker for backtests.

Implements the subset of the OrderService interface that strategies/state machines
call, filling entries immediately at a controllable price (the current bar) and
invoking sm.on_order_filled() — mirroring the paper-mode fill callback. SL/exit
handling stays inside the strategy (paper style), so the broker only needs to
acknowledge those orders.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import pytz
import structlog

if TYPE_CHECKING:
    from engine.strategy.state_machine import SymbolStateMachine

log = structlog.get_logger(__name__)
IST_TZ = pytz.timezone("Asia/Kolkata")


class SimBroker:
    """Deterministic order fills for backtesting (OrderService-compatible subset)."""

    def __init__(self) -> None:
        self._fill_price: float | None = None
        self._fill_time: datetime.datetime | None = None
        self._seq = 0

    # ── Backtest driver controls ─────────────────────────────────────────────

    def set_fill(self, price: float, when: datetime.datetime | None = None) -> None:
        self._fill_price = price
        self._fill_time = when

    def set_kite(self, kite: object) -> None:  # OrderService parity — unused here
        return None

    def _next_id(self, prefix: str, symbol: str) -> str:
        self._seq += 1
        return f"BT_{prefix}_{symbol}_{self._seq}"

    # ── OrderService-compatible surface ──────────────────────────────────────

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
        order_id = self._next_id("ENTRY", symbol)
        fill = self._fill_price if self._fill_price is not None else limit_price
        fill_time = self._fill_time or datetime.datetime.now(IST_TZ)
        if sm is not None:
            await sm.on_order_filled(order_id, fill, quantity, fill_time)
        return order_id

    async def place_stop_loss(
        self,
        symbol: str,
        quantity: int,
        trigger_price: float,
        exchange: str = "NSE",
        product: str = "MIS",
        tag: str = "IVBS_SL",
    ) -> str | None:
        return self._next_id("SL", symbol)

    async def place_exit_market(
        self,
        symbol: str,
        quantity: int,
        reason: str = "exit",
        exchange: str = "NSE",
        product: str = "MIS",
        tag: str = "IVBS_EXIT",
    ) -> str | None:
        return self._next_id("EXIT", symbol)

    async def modify_stop_loss(
        self,
        order_id: str,
        new_trigger: float,
        symbol: str = "",
        sm: "SymbolStateMachine | None" = None,
    ) -> bool:
        return True

    async def modify_entry_order(self, order_id: str, price: float) -> bool:
        return True

    async def cancel_order(self, order_id: str, symbol: str = "") -> bool:
        return True
