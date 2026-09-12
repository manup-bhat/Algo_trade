"""
engine/core/broker_adapters/paper_adapter.py — Paper Trading Broker Adapter.

Simulates order placement, fills, modifications, and cancellations in-memory
with zero outbound requests to external broker APIs.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog

from engine.core.order_gateway import OrderRequest, OrderResult

log = structlog.get_logger(__name__)


class PaperBrokerAdapter:
    """In-memory simulated broker adapter for paper trading and backtesting."""

    key = "paper"

    def __init__(self, initial_capital: float = 1_000_000.0) -> None:
        self._capital = initial_capital
        self._orders: dict[str, dict[str, Any]] = {}
        self._positions: dict[str, dict[str, Any]] = {}

    async def place_order(self, request: OrderRequest) -> OrderResult:
        """Simulate order placement with immediate acceptance."""
        order_id = f"PAPER_{uuid.uuid4().hex[:12].upper()}"
        self._orders[order_id] = {
            "order_id": order_id,
            "symbol": request.instrument.symbol,
            "side": request.side.value,
            "quantity": request.quantity,
            "order_type": request.order_type.value,
            "product": request.product.value,
            "price": request.price,
            "trigger_price": request.trigger_price,
            "status": "COMPLETE",
            "tag": request.tag,
        }
        log.info(
            "paper_order_placed",
            order_id=order_id,
            symbol=request.instrument.symbol,
            side=request.side.value,
            qty=request.quantity,
        )
        return OrderResult(ok=True, order_id=order_id, is_paper=True)

    async def modify_order(
        self,
        order_id: str,
        *,
        price: float | None = None,
        trigger_price: float | None = None,
        quantity: int | None = None,
    ) -> bool:
        """Modify an in-memory order."""
        if order_id not in self._orders:
            log.warning("paper_modify_order_not_found", order_id=order_id)
            return False
        rec = self._orders[order_id]
        if price is not None:
            rec["price"] = price
        if trigger_price is not None:
            rec["trigger_price"] = trigger_price
        if quantity is not None:
            rec["quantity"] = quantity
        log.info("paper_order_modified", order_id=order_id, price=price, trigger=trigger_price)
        return True

    async def cancel_order(self, order_id: str, *, variety: str = "regular") -> bool:
        """Cancel an in-memory order."""
        if order_id not in self._orders:
            log.warning("paper_cancel_order_not_found", order_id=order_id)
            return False
        self._orders[order_id]["status"] = "CANCELLED"
        log.info("paper_order_cancelled", order_id=order_id)
        return True

    async def get_positions(self) -> list[dict[str, Any]]:
        """Return in-memory paper positions."""
        return list(self._positions.values())

    async def get_margins(self) -> dict[str, Any]:
        """Return simulated margins."""
        return {
            "equity": {
                "available": {"cash": self._capital, "live_balance": self._capital},
                "utilised": {"debits": 0.0},
            }
        }
