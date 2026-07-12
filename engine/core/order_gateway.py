"""
engine/core/order_gateway.py — Broker-agnostic, asset-aware order interface.

Today all order placement is hard-wired to NSE equity in order_service.py
(exchange="NSE", product="MIS", SELL SL-M, tag="IVBS_*"). To trade futures &
options the placement layer must vary exchange / product / quantity-in-lots per
instrument. This module defines the abstraction that decouples strategies and the
execution engine from those broker specifics.

Phase 1 provides the contract only (enums + request/result value objects + the
`OrderGateway` ABC). Phase 4/5 implement it (a Kite-backed adapter that also
carries the paper-trade simulation) and migrate order_service onto it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from engine.core.instrument import Instrument, Product


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"      # stop-loss limit
    SL_M = "SL-M"  # stop-loss market


class OrderValidity(str, Enum):
    DAY = "DAY"
    IOC = "IOC"
    TTL = "TTL"


@dataclass(slots=True)
class OrderRequest:
    """A single order to place, expressed in instrument-relative terms."""

    instrument: Instrument
    side: OrderSide
    quantity: int                       # absolute units (lots * lot_size for F&O)
    order_type: OrderType
    product: Product
    price: float | None = None          # required for LIMIT / SL
    trigger_price: float | None = None  # required for SL / SL-M
    validity: OrderValidity = OrderValidity.DAY
    tag: str | None = None              # carries strategy_id for postback routing
    # Idempotency key (maps to Kite's `guid`) to avoid duplicate submissions.
    client_order_id: str | None = None


@dataclass(slots=True)
class OrderResult:
    """Outcome of an order-placement attempt."""

    ok: bool
    order_id: str | None = None
    error: str | None = None
    is_paper: bool = False


class OrderGateway(ABC):
    """Abstract order gateway. Concrete impls wrap Kite (live) and simulate (paper)."""

    @abstractmethod
    async def place(self, request: OrderRequest) -> OrderResult:
        """Place an order. Must be safe to retry with the same client_order_id."""
        raise NotImplementedError

    @abstractmethod
    async def modify(
        self,
        order_id: str,
        *,
        price: float | None = None,
        trigger_price: float | None = None,
        quantity: int | None = None,
    ) -> bool:
        """Modify an open order's price / trigger / quantity. Returns success."""
        raise NotImplementedError

    @abstractmethod
    async def cancel(self, order_id: str, *, variety: str = "regular") -> bool:
        """Cancel an open order. Returns success."""
        raise NotImplementedError
