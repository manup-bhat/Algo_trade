"""
tests/unit/test_fno_order_params.py — asset-aware order routing (Phase 4).

Verifies OrderService place_* methods forward exchange/product/tag for F&O while
defaulting to the equity NSE/MIS/IVBS behavior when not specified.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from engine.orders.order_service import OrderService


def _kite_mock(order_id: str = "FNO_1") -> AsyncMock:
    kite = AsyncMock()
    kite.place_order.return_value = order_id
    return kite


class TestFnoOrderParams:
    @pytest.mark.asyncio
    async def test_entry_routes_fno_params(self):
        kite = _kite_mock("NFO_ENTRY")
        with patch("engine.orders.order_service.settings") as s:
            s.is_paper_trade = False
            s.ORDER_MAX_RETRIES = 3
            svc = OrderService(kite=kite)
            oid = await svc.place_entry(
                "NIFTY24000CE", 120.0, 75,
                exchange="NFO", product="NRML", tag="opt_momentum",
            )
        assert oid == "NFO_ENTRY"
        kw = kite.place_order.call_args.kwargs
        assert kw["exchange"] == "NFO"
        assert kw["product"] == "NRML"
        assert kw["tag"] == "opt_momentum"
        assert kw["tradingsymbol"] == "NIFTY24000CE"
        assert kw["transaction_type"] == "BUY"

    @pytest.mark.asyncio
    async def test_entry_defaults_equity_params(self):
        kite = _kite_mock("EQ_ENTRY")
        with patch("engine.orders.order_service.settings") as s:
            s.is_paper_trade = False
            s.ORDER_MAX_RETRIES = 3
            svc = OrderService(kite=kite)
            await svc.place_entry("RELIANCE", 2500.0, 5)
        kw = kite.place_order.call_args.kwargs
        assert kw["exchange"] == "NSE"
        assert kw["product"] == "MIS"
        assert kw["tag"] == "IVBS"

    @pytest.mark.asyncio
    async def test_stop_loss_routes_fno_params(self):
        kite = _kite_mock("NFO_SL")
        with patch("engine.orders.order_service.settings") as s:
            s.is_paper_trade = False
            s.ORDER_MAX_RETRIES = 3
            svc = OrderService(kite=kite)
            await svc.place_stop_loss(
                "NIFTY24000CE", 75, 84.0,
                exchange="NFO", product="NRML", tag="opt_SL",
            )
        kw = kite.place_order.call_args.kwargs
        assert kw["exchange"] == "NFO"
        assert kw["product"] == "NRML"
        assert kw["order_type"] == "SL-M"
        assert kw["transaction_type"] == "SELL"
        assert "price" not in kw  # SL-M must not carry a price

    @pytest.mark.asyncio
    async def test_exit_market_routes_fno_params(self):
        kite = _kite_mock("NFO_EXIT")
        with patch("engine.orders.order_service.settings") as s:
            s.is_paper_trade = False
            s.ORDER_MAX_RETRIES = 3
            svc = OrderService(kite=kite)
            await svc.place_exit_market(
                "NIFTY24000CE", 75, reason="target",
                exchange="NFO", product="NRML", tag="opt_EXIT",
            )
        kw = kite.place_order.call_args.kwargs
        assert kw["exchange"] == "NFO"
        assert kw["order_type"] == "MARKET"
        assert kw["transaction_type"] == "SELL"
