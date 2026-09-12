"""
tests/unit/test_broker_registry.py — Tests for Broker Registry and Broker Adapters.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
import pytest

from engine.core.broker_registry import (
    BrokerAdapter,
    broker_registry,
    get_broker_adapter,
)
from engine.core.broker_adapters.paper_adapter import PaperBrokerAdapter
from engine.core.broker_adapters.zerodha_adapter import ZerodhaBrokerAdapter
from engine.core.instrument import AssetClass, Exchange, Instrument, OptionType, Product
from engine.core.order_gateway import OrderRequest, OrderSide, OrderType, OrderValidity


@pytest.fixture
def sample_instrument():
    return Instrument(
        instrument_token=738561,
        tradingsymbol="RELIANCE",
        exchange=Exchange.NSE,
        asset_class=AssetClass.EQUITY,
        lot_size=1,
        tick_size=0.05,
    )


@pytest.fixture
def sample_request(sample_instrument):
    return OrderRequest(
        instrument=sample_instrument,
        side=OrderSide.BUY,
        quantity=10,
        order_type=OrderType.LIMIT,
        product=Product.MIS,
        price=2500.0,
        trigger_price=None,
        validity=OrderValidity.DAY,
        tag="IVBS_TEST",
    )


def test_registry_has_defaults():
    assert "paper" in broker_registry.list_keys()
    assert "zerodha" in broker_registry.list_keys()
    paper = get_broker_adapter("paper")
    assert isinstance(paper, PaperBrokerAdapter)
    assert paper.key == "paper"


@pytest.mark.asyncio
async def test_paper_adapter_place_modify_cancel(sample_request):
    adapter = PaperBrokerAdapter(initial_capital=500_000.0)
    res = await adapter.place_order(sample_request)
    assert res.ok
    assert res.order_id is not None
    assert res.is_paper

    mod_ok = await adapter.modify_order(res.order_id, price=2510.0, quantity=15)
    assert mod_ok
    assert adapter._orders[res.order_id]["price"] == 2510.0
    assert adapter._orders[res.order_id]["quantity"] == 15

    cancel_ok = await adapter.cancel_order(res.order_id)
    assert cancel_ok
    assert adapter._orders[res.order_id]["status"] == "CANCELLED"

    # Non-existent order
    assert not await adapter.modify_order("NON_EXISTENT", price=100.0)
    assert not await adapter.cancel_order("NON_EXISTENT")

    # Margins and positions
    margins = await adapter.get_margins()
    assert margins["equity"]["available"]["cash"] == 500_000.0
    positions = await adapter.get_positions()
    assert isinstance(positions, list)


@pytest.mark.asyncio
async def test_zerodha_adapter_place_modify_cancel(sample_request):
    mock_kite = AsyncMock()
    mock_kite.place_order.return_value = "23091100012345"
    mock_kite.modify_order.return_value = "23091100012345"
    mock_kite.cancel_order.return_value = "23091100012345"
    mock_kite.positions.return_value = {"net": [{"symbol": "RELIANCE", "quantity": 10}]}
    mock_kite.margins.return_value = {"equity": {"available": {"cash": 100_000.0}}}

    adapter = ZerodhaBrokerAdapter(mock_kite)
    res = await adapter.place_order(sample_request)
    assert res.ok
    assert res.order_id == "23091100012345"
    assert not res.is_paper

    mod_ok = await adapter.modify_order("23091100012345", price=2510.0)
    assert mod_ok

    cancel_ok = await adapter.cancel_order("23091100012345")
    assert cancel_ok

    positions = await adapter.get_positions()
    assert len(positions) == 1
    assert positions[0]["symbol"] == "RELIANCE"

    margins = await adapter.get_margins()
    assert margins["equity"]["available"]["cash"] == 100_000.0


@pytest.mark.asyncio
async def test_zerodha_adapter_unconfigured(sample_request):
    adapter = ZerodhaBrokerAdapter(None)
    res = await adapter.place_order(sample_request)
    assert not res.ok
    assert "not configured" in res.error

    assert not await adapter.modify_order("123", price=100.0)
    assert not await adapter.cancel_order("123")
    assert await adapter.get_positions() == []
    assert await adapter.get_margins() == {}
