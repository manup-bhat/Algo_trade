"""
engine/orders/order_group.py — Multi-order (multi-leg) construct.

General purpose — not F&O-specific.  Covers:
  - Spread orders (long CE + short CE)
  - Straddles (long CE + long PE)
  - Equity + hedge pairs
  - Any strategy-defined multi-leg structure

The OrderGroup tracks all legs together:
  - group_id: UUID, stored on each order_events row for blotter traceability.
  - Status: PENDING → PARTIAL → FILLED (all legs) or FAILED (any leg terminal failure).
  - Unhedged leg detection: if leg 1 fills and leg 2 rejects → auto-flatten or alert.

Usage (from a strategy's on_candle):
    group = OrderGroup.create("options_momentum")
    group.add_leg(OrderLeg("NIFTY24900CE", "BUY", qty=1, ..., exchange="NFO"))
    group.add_leg(OrderLeg("NIFTY25100CE", "SELL", qty=1, ..., exchange="NFO"))
    placed = await order_service.place_order_group(group)
    # placed.status will be FILLED, PARTIAL, or FAILED

Edge cases:
  - All legs rejected → FAILED, no position held.
  - First leg fills, second rejects → unhedged → auto-flatten first leg.
  - Partial fill on any leg → wait for fill_timeout, then cancel remainder.
  - Duplicate on_fill calls (reconcile race) → idempotent via leg_order_ids set check.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

log = structlog.get_logger(__name__)


class GroupStatus(str, Enum):
    """Lifecycle of an OrderGroup."""
    PENDING   = "PENDING"    # No legs filled yet
    PARTIAL   = "PARTIAL"    # Some legs filled, some pending
    FILLED    = "FILLED"     # All legs filled
    FAILED    = "FAILED"     # One or more legs terminally failed with no recovery
    CANCELLED = "CANCELLED"  # Explicitly cancelled before completion


class OnUnhedged(str, Enum):
    """What to do when a leg fills but its counterpart fails."""
    FLATTEN    = "flatten"      # Auto-place a market exit for the filled leg
    ALERT_ONLY = "alert_only"   # Log CRITICAL + pub:alerts, hold the position


@dataclass
class OrderLeg:
    """
    One leg of an OrderGroup.

    All fields required at construction time so the group can be fully
    specified before any API call is made (inspection, logging, dry-run).
    """
    symbol: str
    side: str              # "BUY" | "SELL"
    quantity: int
    order_type: str = "MARKET"         # "LIMIT" | "MARKET" | "SL-M" | "SL"
    price: float | None = None         # Required for LIMIT / SL orders
    trigger_price: float | None = None # Required for SL-M / SL orders
    exchange: str = "NSE"
    product: str = "MIS"
    tag: str = ""
    variety: str = "regular"           # "regular" | "amo"

    # Set by OrderService after placement
    order_id: str | None = None
    status: str = "PENDING"            # Mirrors Kite order status
    filled_quantity: int = 0
    average_price: float = 0.0

    def __post_init__(self) -> None:
        if self.side not in ("BUY", "SELL"):
            raise ValueError(f"OrderLeg.side must be 'BUY' or 'SELL', got {self.side!r}")
        if self.quantity < 1:
            raise ValueError(f"OrderLeg.quantity must be >= 1, got {self.quantity}")
        if self.order_type in ("LIMIT", "SL") and self.price is None:
            raise ValueError(f"OrderLeg.price required for order_type={self.order_type}")
        if self.order_type in ("SL-M", "SL") and self.trigger_price is None:
            raise ValueError(f"OrderLeg.trigger_price required for order_type={self.order_type}")

    @property
    def is_filled(self) -> bool:
        return self.status in ("COMPLETE", "FILLED")

    @property
    def is_failed(self) -> bool:
        return self.status in ("REJECTED", "CANCELLED")

    @property
    def is_partial(self) -> bool:
        return 0 < self.filled_quantity < self.quantity

    @property
    def counterpart_side(self) -> str:
        """The side needed to flatten this leg (for auto-flatten)."""
        return "SELL" if self.side == "BUY" else "BUY"


@dataclass
class OrderGroup:
    """
    A collection of OrderLegs treated as a single logical order.

    Create via OrderGroup.create(strategy_id) — never construct directly.
    """
    group_id: str
    strategy_id: str
    legs: list[OrderLeg] = field(default_factory=list)
    status: GroupStatus = GroupStatus.PENDING
    on_unhedged: OnUnhedged = OnUnhedged.FLATTEN
    metadata: dict[str, Any] = field(default_factory=dict)  # strategy-specific context

    # ── Factory ───────────────────────────────────────────────────────────────

    @classmethod
    def create(
        cls,
        strategy_id: str,
        on_unhedged: OnUnhedged = OnUnhedged.FLATTEN,
        metadata: dict[str, Any] | None = None,
    ) -> "OrderGroup":
        """Create a new OrderGroup with a generated group_id."""
        return cls(
            group_id=str(uuid.uuid4()),
            strategy_id=strategy_id,
            on_unhedged=on_unhedged,
            metadata=metadata or {},
        )

    # ── Leg management ────────────────────────────────────────────────────────

    def add_leg(self, leg: OrderLeg) -> "OrderGroup":
        """Add an OrderLeg. Returns self for chaining."""
        self.legs.append(leg)
        return self

    # ── Status queries ────────────────────────────────────────────────────────

    @property
    def is_complete(self) -> bool:
        """True if every leg is filled (COMPLETE status)."""
        return bool(self.legs) and all(leg.is_filled for leg in self.legs)

    @property
    def is_failed(self) -> bool:
        """True if any leg has terminally failed."""
        return any(leg.is_failed for leg in self.legs)

    @property
    def unhedged_legs(self) -> list[int]:
        """
        Return indices of legs that are filled but whose counterpart has failed.

        Example: leg[0] filled (BUY), leg[1] rejected (SELL) → unhedged = [0].
        Only meaningful for 2-leg groups (spreads, straddles).
        """
        if len(self.legs) != 2:
            return []
        filled = [i for i, leg in enumerate(self.legs) if leg.is_filled]
        failed = [i for i, leg in enumerate(self.legs) if leg.is_failed]
        return [i for i in filled if (1 - i) in failed]

    @property
    def any_partial(self) -> bool:
        """True if any leg has a partial fill (some qty filled, some pending)."""
        return any(leg.is_partial for leg in self.legs)

    @property
    def total_filled_quantity_by_symbol(self) -> dict[str, int]:
        """Return {symbol: total_filled_quantity} across all legs."""
        result: dict[str, int] = {}
        for leg in self.legs:
            result[leg.symbol] = result.get(leg.symbol, 0) + leg.filled_quantity
        return result

    def update_status(self) -> GroupStatus:
        """
        Recompute and set self.status from leg states.
        Called after any leg status update.
        """
        if not self.legs:
            self.status = GroupStatus.PENDING
            return self.status

        all_filled = all(leg.is_filled for leg in self.legs)
        any_failed = any(leg.is_failed for leg in self.legs)
        any_filled = any(leg.is_filled for leg in self.legs)

        if all_filled:
            self.status = GroupStatus.FILLED
        elif any_failed and not any_filled:
            self.status = GroupStatus.FAILED   # All failed — no partial exposure
        elif any_failed and any_filled:
            # Partial exposure — unhedged state; status set by the reconciler
            self.status = GroupStatus.PARTIAL
        elif any_filled:
            self.status = GroupStatus.PARTIAL
        else:
            self.status = GroupStatus.PENDING

        return self.status

    def __repr__(self) -> str:
        leg_summary = ", ".join(
            f"{l.side}:{l.symbol}×{l.quantity}@{l.status}" for l in self.legs
        )
        return f"OrderGroup({self.group_id[:8]} [{self.strategy_id}] {self.status} legs=[{leg_summary}])"
