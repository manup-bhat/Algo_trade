"""
tests/unit/test_order_group.py — Unit tests for OrderGroup and OrderLeg.

Tests cover:
  - OrderGroup.create() generates a group_id.
  - add_leg() appends legs.
  - is_complete when all legs filled.
  - is_failed when any leg rejected.
  - unhedged_legs: leg 0 filled + leg 1 rejected → [0].
  - unhedged_legs: both filled → [].
  - update_status() correct GroupStatus for each combination.
  - any_partial: partial fill detection.
  - total_filled_quantity_by_symbol: correct aggregation.
  - OrderLeg validation: side must be BUY/SELL.
  - OrderLeg validation: quantity >= 1.
  - OrderLeg validation: LIMIT order requires price.
  - OrderLeg validation: SL-M requires trigger_price.
  - GroupStatus.FAILED when all legs rejected.
"""

from __future__ import annotations

import pytest
from engine.orders.order_group import (
    GroupStatus, OnUnhedged, OrderGroup, OrderLeg,
)


def make_leg(
    symbol: str = "RELIANCE",
    side: str = "BUY",
    quantity: int = 10,
    order_type: str = "MARKET",
    status: str = "PENDING",
    filled_quantity: int = 0,
) -> OrderLeg:
    leg = OrderLeg(symbol=symbol, side=side, quantity=quantity, order_type=order_type)
    leg.status = status
    leg.filled_quantity = filled_quantity
    return leg


# ── OrderGroup creation ───────────────────────────────────────────────────────

def test_create_generates_group_id():
    g = OrderGroup.create("ivbs")
    assert len(g.group_id) == 36  # UUID4 format


def test_create_two_groups_different_ids():
    g1 = OrderGroup.create("ivbs")
    g2 = OrderGroup.create("ivbs")
    assert g1.group_id != g2.group_id


def test_create_strategy_id():
    g = OrderGroup.create("options_momentum")
    assert g.strategy_id == "options_momentum"


def test_create_default_on_unhedged():
    g = OrderGroup.create("s")
    assert g.on_unhedged == OnUnhedged.FLATTEN


def test_create_custom_on_unhedged():
    g = OrderGroup.create("s", on_unhedged=OnUnhedged.ALERT_ONLY)
    assert g.on_unhedged == OnUnhedged.ALERT_ONLY


# ── add_leg / legs ────────────────────────────────────────────────────────────

def test_add_leg_appends():
    g = OrderGroup.create("s")
    g.add_leg(make_leg("A", "BUY")).add_leg(make_leg("B", "SELL"))
    assert len(g.legs) == 2


def test_add_leg_returns_self_for_chaining():
    g = OrderGroup.create("s")
    returned = g.add_leg(make_leg())
    assert returned is g


# ── is_complete ───────────────────────────────────────────────────────────────

def test_is_complete_all_filled():
    g = OrderGroup.create("s")
    g.add_leg(make_leg(status="COMPLETE", filled_quantity=10))
    g.add_leg(make_leg(status="COMPLETE", filled_quantity=10))
    assert g.is_complete


def test_is_complete_one_pending():
    g = OrderGroup.create("s")
    g.add_leg(make_leg(status="COMPLETE", filled_quantity=10))
    g.add_leg(make_leg(status="PENDING"))
    assert not g.is_complete


def test_is_complete_empty_group():
    g = OrderGroup.create("s")
    assert not g.is_complete  # No legs → not complete


# ── is_failed ─────────────────────────────────────────────────────────────────

def test_is_failed_any_rejected():
    g = OrderGroup.create("s")
    g.add_leg(make_leg(status="COMPLETE", filled_quantity=10))
    g.add_leg(make_leg(status="REJECTED"))
    assert g.is_failed


def test_is_failed_false_when_all_pending():
    g = OrderGroup.create("s")
    g.add_leg(make_leg(status="PENDING"))
    assert not g.is_failed


# ── unhedged_legs ─────────────────────────────────────────────────────────────

def test_unhedged_leg_0_filled_leg_1_rejected():
    g = OrderGroup.create("s")
    g.add_leg(make_leg("CE", "BUY", status="COMPLETE", filled_quantity=10))
    g.add_leg(make_leg("PE", "BUY", status="REJECTED"))
    assert g.unhedged_legs == [0]


def test_unhedged_leg_1_filled_leg_0_rejected():
    g = OrderGroup.create("s")
    g.add_leg(make_leg("CE", "BUY", status="REJECTED"))
    g.add_leg(make_leg("PE", "BUY", status="COMPLETE", filled_quantity=10))
    assert g.unhedged_legs == [1]


def test_no_unhedged_when_both_filled():
    g = OrderGroup.create("s")
    g.add_leg(make_leg(status="COMPLETE", filled_quantity=10))
    g.add_leg(make_leg(status="COMPLETE", filled_quantity=10))
    assert g.unhedged_legs == []


def test_no_unhedged_when_both_pending():
    g = OrderGroup.create("s")
    g.add_leg(make_leg(status="PENDING"))
    g.add_leg(make_leg(status="PENDING"))
    assert g.unhedged_legs == []


def test_unhedged_not_2_legs_returns_empty():
    """unhedged_legs only meaningful for 2-leg groups."""
    g = OrderGroup.create("s")
    g.add_leg(make_leg(status="COMPLETE", filled_quantity=10))
    g.add_leg(make_leg(status="COMPLETE", filled_quantity=10))
    g.add_leg(make_leg(status="REJECTED"))
    assert g.unhedged_legs == []  # 3-leg group → empty


# ── update_status ─────────────────────────────────────────────────────────────

def test_update_status_all_filled():
    g = OrderGroup.create("s")
    g.add_leg(make_leg(status="COMPLETE", filled_quantity=10))
    g.add_leg(make_leg(status="COMPLETE", filled_quantity=10))
    assert g.update_status() == GroupStatus.FILLED


def test_update_status_all_failed():
    g = OrderGroup.create("s")
    g.add_leg(make_leg(status="REJECTED"))
    g.add_leg(make_leg(status="CANCELLED"))
    assert g.update_status() == GroupStatus.FAILED


def test_update_status_partial_fill_and_failed():
    g = OrderGroup.create("s")
    g.add_leg(make_leg(status="COMPLETE", filled_quantity=10))
    g.add_leg(make_leg(status="REJECTED"))
    assert g.update_status() == GroupStatus.PARTIAL


def test_update_status_partial_fill_in_progress():
    g = OrderGroup.create("s")
    g.add_leg(make_leg(status="COMPLETE", filled_quantity=10))
    g.add_leg(make_leg(status="PENDING"))
    assert g.update_status() == GroupStatus.PARTIAL


def test_update_status_all_pending():
    g = OrderGroup.create("s")
    g.add_leg(make_leg(status="PENDING"))
    assert g.update_status() == GroupStatus.PENDING


# ── any_partial ───────────────────────────────────────────────────────────────

def test_any_partial_detected():
    g = OrderGroup.create("s")
    g.add_leg(make_leg(quantity=10, status="PENDING", filled_quantity=5))
    assert g.any_partial


def test_no_partial_when_all_complete():
    g = OrderGroup.create("s")
    g.add_leg(make_leg(quantity=10, status="COMPLETE", filled_quantity=10))
    assert not g.any_partial


# ── total_filled_quantity_by_symbol ──────────────────────────────────────────

def test_total_filled_quantity_aggregation():
    g = OrderGroup.create("s")
    g.add_leg(OrderLeg("NIFTY24900CE", "BUY", 2, status="COMPLETE", filled_quantity=2))
    g.add_leg(OrderLeg("NIFTY25100CE", "SELL", 2, status="COMPLETE", filled_quantity=1))
    total = g.total_filled_quantity_by_symbol
    assert total["NIFTY24900CE"] == 2
    assert total["NIFTY25100CE"] == 1


# ── OrderLeg validation ────────────────────────────────────────────────────────

def test_order_leg_invalid_side_raises():
    with pytest.raises(ValueError, match="BUY.*SELL"):
        OrderLeg("X", "HOLD", 10)


def test_order_leg_zero_qty_raises():
    with pytest.raises(ValueError, match="quantity"):
        OrderLeg("X", "BUY", 0)


def test_order_leg_limit_without_price_raises():
    with pytest.raises(ValueError, match="price"):
        OrderLeg("X", "BUY", 10, order_type="LIMIT", price=None)


def test_order_leg_slm_without_trigger_raises():
    with pytest.raises(ValueError, match="trigger_price"):
        OrderLeg("X", "BUY", 10, order_type="SL-M", trigger_price=None)


def test_order_leg_counterpart_side():
    buy_leg = make_leg(side="BUY")
    assert buy_leg.counterpart_side == "SELL"
    sell_leg = make_leg(side="SELL")
    assert sell_leg.counterpart_side == "BUY"


# ── Repr ──────────────────────────────────────────────────────────────────────

def test_repr_contains_strategy():
    g = OrderGroup.create("ivbs")
    g.add_leg(make_leg())
    assert "ivbs" in repr(g)
    assert g.group_id[:8] in repr(g)
