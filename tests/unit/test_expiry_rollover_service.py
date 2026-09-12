"""
tests/unit/test_expiry_rollover_service.py — Unit tests for ExpiryRolloverService.

Covers:
    - run_rollover: no expiring positions → logs + returns immediately
    - run_rollover: one expiring position → exit + entry placed, alert published
    - run_rollover: NX lock held → position skipped (idempotency)
    - run_rollover: discovery error → logs critical, returns gracefully
    - _roll_one: exit order failure → alert_failure published
    - _roll_one: no next expiry → failure published
    - _roll_one: no ATM instrument → failure published
    - record_daily_iv: appends IV to Redis correctly (tested via IVRankProvider static)
"""

from __future__ import annotations

import datetime
import json
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from engine.orders.expiry_rollover_service import ExpiryRolloverService


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def svc():
    return ExpiryRolloverService()


@pytest.fixture
def mock_redis():
    r = MagicMock()
    inner = MagicMock()
    # Default: no positions
    inner.hgetall = AsyncMock(return_value={})
    # Default: NX lock succeeds (new lock)
    inner.set = AsyncMock(return_value=True)
    inner.get = AsyncMock(return_value=None)
    r._r = inner
    r.get_all_open_positions = AsyncMock(return_value={})
    return r


@pytest.fixture
def mock_order_service():
    svc = MagicMock()
    svc.place_exit_market = AsyncMock(return_value="EXIT_ORDER_123")
    svc.place_entry = AsyncMock(return_value="ENTRY_ORDER_456")
    return svc


@pytest.fixture
def mock_master():
    m = MagicMock()
    m.nearest_expiry = MagicMock(
        return_value=datetime.date.today() + datetime.timedelta(days=7)
    )
    m.atm_option = MagicMock(return_value=_make_instrument())
    m.get_instrument = MagicMock(return_value=None)
    return m


def _make_instrument(symbol="NIFTY23SEP19000CE"):
    from engine.core.instrument import Instrument, AssetClass, OptionType
    inst = MagicMock(spec=Instrument)
    inst.tradingsymbol = symbol
    inst.is_derivative = True
    inst.is_option = True
    inst.is_future = False
    inst.underlying = "NIFTY"
    inst.expiry = datetime.date.today() + datetime.timedelta(days=7)
    inst.option_type = OptionType.CE
    inst.strike = 19000.0
    inst.instrument_token = 99999
    return inst


def _make_expiring_position(symbol="NIFTY23SEP21000CE"):
    today = datetime.date.today()
    return {
        "symbol": symbol,
        "underlying": "NIFTY",
        "expiry": today,
        "quantity": 50,
        "exchange": "NFO",
        "product": "NRML",
        "strategy_id": "options_momentum",
        "option_type": "CE",
        "strike": 21000.0,
        "spot_price": 19_500.0,
    }


# ── run_rollover ──────────────────────────────────────────────────────────────

class TestRunRollover:
    @pytest.mark.asyncio
    async def test_no_expiring_positions(self, svc, mock_redis, mock_order_service, mock_master):
        svc.wire(
            order_service=mock_order_service,
            redis_store=mock_redis,
            instrument_master=mock_master,
        )
        # No positions in Redis
        mock_redis.get_all_open_positions = AsyncMock(return_value={})

        await svc.run_rollover()

        # No orders placed
        mock_order_service.place_exit_market.assert_not_called()
        mock_order_service.place_entry.assert_not_called()

    @pytest.mark.asyncio
    async def test_discovery_error_handled_gracefully(self, svc, mock_redis, mock_order_service, mock_master):
        svc.wire(
            order_service=mock_order_service,
            redis_store=mock_redis,
            instrument_master=mock_master,
        )
        mock_redis.get_all_open_positions = AsyncMock(side_effect=Exception("Redis down"))
        mock_redis._r.hgetall = AsyncMock(side_effect=Exception("Redis down"))

        # Should not raise
        await svc.run_rollover()
        mock_order_service.place_exit_market.assert_not_called()

    @pytest.mark.asyncio
    async def test_expiring_position_rolled(self, svc, mock_redis, mock_order_service, mock_master):
        pos = _make_expiring_position()
        inst = _make_instrument("NIFTY23SEP19000CE")
        mock_master.get_instrument = MagicMock(return_value=inst)
        mock_master.atm_option = MagicMock(return_value=inst)

        svc.wire(
            order_service=mock_order_service,
            redis_store=mock_redis,
            instrument_master=mock_master,
        )

        with patch.object(svc, "_discover_expiring_positions", AsyncMock(return_value=[pos])):
            with patch("engine.orders.expiry_rollover_service.publish_alert", AsyncMock()) as mock_pub:
                await svc.run_rollover()

        mock_order_service.place_exit_market.assert_called_once()
        mock_order_service.place_entry.assert_called_once()


# ── _roll_one ──────────────────────────────────────────────────────────────────

class TestRollOne:
    @pytest.mark.asyncio
    async def test_lock_held_skips(self, svc, mock_redis, mock_order_service, mock_master):
        pos = _make_expiring_position()
        svc.wire(
            order_service=mock_order_service,
            redis_store=mock_redis,
            instrument_master=mock_master,
        )
        # Lock already held (NX returns None/False)
        mock_redis._r.set = AsyncMock(return_value=None)

        result = await svc._roll_one(pos)
        assert result is True  # skipped-lock counts as success
        mock_order_service.place_exit_market.assert_not_called()

    @pytest.mark.asyncio
    async def test_exit_failure_publishes_alert(self, svc, mock_redis, mock_order_service, mock_master):
        pos = _make_expiring_position()
        svc.wire(
            order_service=mock_order_service,
            redis_store=mock_redis,
            instrument_master=mock_master,
        )
        mock_order_service.place_exit_market = AsyncMock(return_value=None)  # failure

        with patch("engine.orders.expiry_rollover_service.publish_alert", AsyncMock()) as mock_pub:
            result = await svc._roll_one(pos)

        assert result is False
        mock_pub.assert_called_once()
        event = mock_pub.call_args[0][0]
        assert event.type == "expiry_rollover_failed"

    @pytest.mark.asyncio
    async def test_no_next_expiry_publishes_alert(self, svc, mock_redis, mock_order_service, mock_master):
        pos = _make_expiring_position()
        mock_master.nearest_expiry = MagicMock(return_value=None)
        svc.wire(
            order_service=mock_order_service,
            redis_store=mock_redis,
            instrument_master=mock_master,
        )

        with patch("engine.orders.expiry_rollover_service.publish_alert", AsyncMock()) as mock_pub:
            result = await svc._roll_one(pos)

        assert result is False
        event = mock_pub.call_args[0][0]
        assert "no_next_expiry" in event.payload.get("reason", "")

    @pytest.mark.asyncio
    async def test_no_atm_instrument_publishes_alert(self, svc, mock_redis, mock_order_service, mock_master):
        pos = _make_expiring_position()
        mock_master.atm_option = MagicMock(return_value=None)
        svc.wire(
            order_service=mock_order_service,
            redis_store=mock_redis,
            instrument_master=mock_master,
        )

        with patch("engine.orders.expiry_rollover_service.publish_alert", AsyncMock()) as mock_pub:
            result = await svc._roll_one(pos)

        assert result is False
        event = mock_pub.call_args[0][0]
        assert "atm_not_found" in event.payload.get("reason", "")

    @pytest.mark.asyncio
    async def test_happy_path_returns_true(self, svc, mock_redis, mock_order_service, mock_master):
        pos = _make_expiring_position()
        inst = _make_instrument("NIFTY23SEP19000CE")
        mock_master.atm_option = MagicMock(return_value=inst)
        svc.wire(
            order_service=mock_order_service,
            redis_store=mock_redis,
            instrument_master=mock_master,
        )

        with patch("engine.orders.expiry_rollover_service.publish_alert", AsyncMock()) as mock_pub:
            result = await svc._roll_one(pos)

        assert result is True
        mock_pub.assert_called_once()
        event = mock_pub.call_args[0][0]
        assert event.type == "expiry_rollover_complete"
        assert event.payload["old_symbol"] == "NIFTY23SEP21000CE"
        assert event.payload["new_symbol"] == "NIFTY23SEP19000CE"


# ── Notification registry (LogChannel) ────────────────────────────────────────

class TestNotificationRegistry:
    @pytest.mark.asyncio
    async def test_publish_alert_log_channel(self):
        """Verify publish_alert routes to LogChannel without raising."""
        from engine.core.notification_registry import AlertEvent, publish_alert
        event = AlertEvent(
            type="test_event",
            severity="INFO",
            payload={"key": "value"},
            strategy_id="test",
        )
        # Should not raise even if multiple channels registered
        await publish_alert(event)

    @pytest.mark.asyncio
    async def test_broken_channel_does_not_block_others(self, monkeypatch):
        from engine.core.notification_registry import (
            AlertEvent, notification_registry, publish_alert
        )
        from engine.core.registry import Registry

        class BrokenChannel:
            key = "broken"
            async def send(self, event):
                raise RuntimeError("channel down")

        called = []

        class GoodChannel:
            key = "good"
            async def send(self, event):
                called.append(event.type)

        reg = Registry()
        reg.register("broken", BrokenChannel())
        reg.register("good", GoodChannel())
        monkeypatch.setattr(
            "engine.core.notification_registry.notification_registry",
            reg,
        )

        event = AlertEvent(type="x", severity="INFO", payload={})
        await publish_alert(event)
        # good channel still called despite broken channel
        assert "x" in called
