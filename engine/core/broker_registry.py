"""
engine/core/broker_registry.py — Broker Adapter Protocol & Registry.

Decouples order execution and account queries from Kite-specific shapes
(Ports & Adapters / Hexagonal Architecture per Part 3 §3.1 and §4).

Supported adapters:
    "paper"   — In-memory simulated execution (zero exchange submission).
    "zerodha" — Live KiteConnect execution via AsyncKiteClient / KiteConnect.

Usage:
    adapter = broker_registry.get("paper")
    result = await adapter.place_order(request)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

import structlog

from engine.core.order_gateway import OrderRequest, OrderResult
from engine.core.registry import Registry

if TYPE_CHECKING:
    pass

log = structlog.get_logger(__name__)


# ── BrokerAdapter Protocol ───────────────────────────────────────────────────

@runtime_checkable
class BrokerAdapter(Protocol):
    """
    Interface that every broker adapter must satisfy.
    """

    key: str  # "paper", "zerodha", "upstox", etc.

    async def place_order(self, request: OrderRequest) -> OrderResult:
        """Place an order through the broker adapter."""
        ...

    async def modify_order(
        self,
        order_id: str,
        *,
        price: float | None = None,
        trigger_price: float | None = None,
        quantity: int | None = None,
    ) -> bool:
        """Modify an existing open order."""
        ...

    async def cancel_order(self, order_id: str, *, variety: str = "regular") -> bool:
        """Cancel an open order."""
        ...

    async def get_positions(self) -> list[dict[str, Any]]:
        """Return active positions from the broker."""
        ...

    async def get_margins(self) -> dict[str, Any]:
        """Return available/used margin information from the broker."""
        ...


# ── Registry singleton ────────────────────────────────────────────────────────

broker_registry: Registry[BrokerAdapter] = Registry()


def _register_default_adapters() -> None:
    try:
        from engine.core.broker_adapters.paper_adapter import PaperBrokerAdapter
        from engine.core.broker_adapters.zerodha_adapter import ZerodhaBrokerAdapter

        broker_registry.register("paper", PaperBrokerAdapter())
        broker_registry.register("zerodha", ZerodhaBrokerAdapter())
    except Exception as exc:
        log.warning("broker_registry_default_register_failed", error=str(exc))


_register_default_adapters()


def get_broker_adapter(key: str) -> BrokerAdapter:
    """Convenience lookup returning the adapter or raising KeyError."""
    return broker_registry.get(key)
