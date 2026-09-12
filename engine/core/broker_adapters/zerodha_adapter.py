"""
engine/core/broker_adapters/zerodha_adapter.py — Zerodha KiteConnect Broker Adapter.

Adapts OrderRequest/BrokerAdapter protocol to live Zerodha KiteConnect API
calls via AsyncKiteClient.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from engine.core.order_gateway import OrderRequest, OrderResult

if TYPE_CHECKING:
    from engine.kite.client import AsyncKiteClient

log = structlog.get_logger(__name__)


class ZerodhaBrokerAdapter:
    """Live broker adapter connecting to Zerodha KiteConnect API."""

    key = "zerodha"

    def __init__(self, kite_client: "AsyncKiteClient | None" = None) -> None:
        self._kite = kite_client

    def set_client(self, kite_client: "AsyncKiteClient") -> None:
        self._kite = kite_client

    async def place_order(self, request: OrderRequest) -> OrderResult:
        """Place a live order via Zerodha KiteConnect."""
        if self._kite is None:
            return OrderResult(ok=False, error="Zerodha client not configured / None")

        params: dict[str, Any] = {
            "exchange": request.instrument.exchange.value if hasattr(request.instrument.exchange, "value") else str(request.instrument.exchange),
            "tradingsymbol": request.instrument.symbol,
            "transaction_type": request.side.value,
            "quantity": request.quantity,
            "order_type": request.order_type.value,
            "product": request.product.value,
            "validity": request.validity.value,
        }
        if request.price is not None:
            params["price"] = request.price
        if request.trigger_price is not None:
            params["trigger_price"] = request.trigger_price
        if request.tag:
            params["tag"] = request.tag

        try:
            order_id = await self._kite.place_order(**params)
            return OrderResult(ok=True, order_id=str(order_id), is_paper=False)
        except Exception as exc:
            log.error(
                "zerodha_place_order_failed",
                symbol=request.instrument.symbol,
                side=request.side.value,
                error=str(exc),
            )
            return OrderResult(ok=False, error=str(exc), is_paper=False)

    async def modify_order(
        self,
        order_id: str,
        *,
        price: float | None = None,
        trigger_price: float | None = None,
        quantity: int | None = None,
    ) -> bool:
        """Modify an open order via Kite."""
        if self._kite is None:
            return False

        params: dict[str, Any] = {}
        if price is not None:
            params["price"] = price
        if trigger_price is not None:
            params["trigger_price"] = trigger_price
        if quantity is not None:
            params["quantity"] = quantity

        try:
            await self._kite.modify_order(order_id=order_id, **params)
            return True
        except Exception as exc:
            log.error("zerodha_modify_order_failed", order_id=order_id, error=str(exc))
            return False

    async def cancel_order(self, order_id: str, *, variety: str = "regular") -> bool:
        """Cancel an open order via Kite."""
        if self._kite is None:
            return False

        try:
            await self._kite.cancel_order(order_id=order_id)
            return True
        except Exception as exc:
            log.error("zerodha_cancel_order_failed", order_id=order_id, error=str(exc))
            return False

    async def get_positions(self) -> list[dict[str, Any]]:
        """Return current positions from Kite."""
        if self._kite is None:
            return []
        try:
            pos = await self._kite.positions()
            return pos.get("net", []) if isinstance(pos, dict) else []
        except Exception as exc:
            log.error("zerodha_get_positions_failed", error=str(exc))
            return []

    async def get_margins(self) -> dict[str, Any]:
        """Return margins from Kite."""
        if self._kite is None:
            return {}
        try:
            return await self._kite.margins()
        except Exception as exc:
            log.error("zerodha_get_margins_failed", error=str(exc))
            return {}
