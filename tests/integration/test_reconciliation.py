"""
tests/integration/test_reconciliation.py — Integration tests for spec §12.1 and §12.2.

Tests:
  §12.1 Orphan Detection:
    - SM in MANAGING state + Kite has open position → no orphan (normal)
    - Kite has open position + NO Redis state → orphan detected, market sell fired
    - Redis has MANAGING state + NO Kite open position → ghost detected, Redis cleared

  §12.2 Order Book Reconciliation:
    - SM is MANAGING, SL was triggered silently → on_sl_triggered called
    - SM is MANAGING, SL was REJECTED → emergency close fired
    - SM is ACTION_PENDING, fill missed → on_order_filled called
    - SM is ACTION_PENDING, entry rejected → on_order_rejected called
"""

from __future__ import annotations

import datetime
import os
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis
import pytest
import pytz

os.environ.setdefault("KITE_API_KEY", "test")
os.environ.setdefault("KITE_API_SECRET", "test")
os.environ.setdefault("PAPER_TRADE", "true")

IST_TZ = pytz.timezone("Asia/Kolkata")
NOW_IST = datetime.datetime.now(IST_TZ)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
async def redis_store():
    from engine.store.redis_store import RedisStore
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    store = RedisStore(r)
    yield store
    await r.aclose()


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.write_order_event = AsyncMock()
    db.write_signal = AsyncMock(return_value=1)
    db.update_signal_progression = AsyncMock()
    return db


@pytest.fixture
def mock_order_service():
    svc = AsyncMock()
    svc.place_exit_market = AsyncMock(return_value="EXIT_ORDER_001")
    svc.cancel_order = AsyncMock(return_value=True)
    return svc


@pytest.fixture
async def coordinator(redis_store, mock_db, mock_order_service):
    from engine.orders.fill_timeout import FillTimeoutManager
    from engine.orders.order_tracker import OrderTracker
    from engine.strategy.coordinator import Coordinator

    tracker = OrderTracker()
    ftm = FillTimeoutManager()

    coord = Coordinator(redis_store, mock_db)
    coord.inject_dependencies(
        order_service=mock_order_service,
        order_tracker=tracker,
        fill_timeout_manager=ftm,
        kite=None,
    )
    return coord


@pytest.fixture
def mock_kite():
    kite = AsyncMock()
    kite.positions.return_value = {"day": [], "net": []}
    kite.orders.return_value = []
    kite.trades.return_value = []
    return kite


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_sm(symbol: str, redis_store, mock_db, mock_order_service):
    """Create a SymbolStateMachine with minimal wiring for tests."""
    from engine.orders.fill_timeout import FillTimeoutManager
    from engine.orders.order_tracker import OrderTracker
    from engine.strategy.state_machine import SymbolStateMachine

    sm = SymbolStateMachine(
        symbol=symbol,
        instrument_token=99,
        redis_store=redis_store,
        db_writer=mock_db,
        order_service=mock_order_service,
        order_tracker=OrderTracker(),
        fill_timeout_manager=FillTimeoutManager(),
    )
    return sm


def _make_open_position(sm, entry_price=500.0, qty=100):
    """Hydrate SM with a fake MANAGING position."""
    from engine.strategy.state_machine import OpenPosition, StrategyState

    sm.state = StrategyState.MANAGING
    pos = OpenPosition(
        trade_id=1,
        entry_price=entry_price,
        quantity=qty,
        initial_sl=460.0,
        current_sl=460.0,
        risk_per_share=40.0,
        risk_amount=4000.0,
        target_1r2=580.0,
        target_1r3=620.0,
        target_1r4=660.0,
        entry_order_id="ENTRY_001",
        sl_order_id="SL_001",
    )
    sm.position = pos
    return sm


# ── §12.1 Orphan Detection Tests ──────────────────────────────────────────────

class TestOrphanDetection:
    async def test_no_orphan_when_sm_matches_kite(
        self, coordinator, redis_store, mock_db, mock_order_service, mock_kite
    ):
        """
        Kite has open position for RELIANCE AND coordinator has MANAGING SM.
        No orphan detected → no emergency close.
        """
        sm = _make_sm("RELIANCE", redis_store, mock_db, mock_order_service)
        _make_open_position(sm)
        coordinator.active_state_machines["RELIANCE"] = sm
        await redis_store.set_strategy_state("RELIANCE", {"state": "MANAGING"})

        mock_kite.positions.return_value = {
            "day": [],
            "net": [{"tradingsymbol": "RELIANCE", "quantity": 100, "exchange": "NSE"}],
        }

        await coordinator.orphan_check(mock_kite)

        # No market exit placed
        mock_order_service.place_exit_market.assert_not_called()

    async def test_orphan_position_triggers_market_sell(
        self, coordinator, redis_store, mock_db, mock_order_service, mock_kite
    ):
        """
        Kite has open position for INFY but coordinator has NO SM.
        Orphan detected → emergency market sell fired.
        """
        mock_kite.positions.return_value = {
            "day": [],
            "net": [{"tradingsymbol": "INFY", "quantity": 50, "exchange": "NSE"}],
        }
        mock_kite.trades.return_value = []

        await coordinator.orphan_check(mock_kite)

        mock_order_service.place_exit_market.assert_called_once_with(
            "INFY", 50, reason="orphan_close"
        )

    async def test_ghost_managing_state_cleared(
        self, coordinator, redis_store, mock_db, mock_order_service, mock_kite
    ):
        """
        Redis has MANAGING state for WIPRO but Kite shows 0 quantity.
        Ghost detected → Redis state cleared.
        """
        # Only Redis has state; Kite has no open position
        await redis_store.set_strategy_state("WIPRO", {"state": "MANAGING"})
        mock_kite.positions.return_value = {"day": [], "net": []}  # No position
        mock_kite.trades.return_value = []

        await coordinator.orphan_check(mock_kite)

        # Redis state should be cleared
        state = await redis_store.get_strategy_state("WIPRO")
        assert state is None


# ── §12.2 Reconciliation Tests ────────────────────────────────────────────────

class TestOrderReconciliation:
    async def test_exit_fill_missed_triggers_close(
        self, coordinator, redis_store, mock_db, mock_order_service, mock_kite
    ):
        """
        SM is MANAGING with exit already initiated.
        Exit order status COMPLETE in Kite orders should close via _close_position.
        """
        sm = _make_sm("TATASTEEL", redis_store, mock_db, mock_order_service)
        _make_open_position(sm)
        sm.position._exit_initiated = True
        sm.position.exit_order_id = "EXIT_001"
        sm.position.exit_reason = "CLOSED_TARGET"
        sm._close_position = AsyncMock()
        coordinator.active_state_machines["TATASTEEL"] = sm

        mock_kite.orders.return_value = [
            {
                "order_id": "EXIT_001",
                "status": "COMPLETE",
                "average_price": 621.5,
                "tradingsymbol": "TATASTEEL",
            }
        ]

        await coordinator.reconcile_orders(mock_kite)

        sm._close_position.assert_called_once_with(621.5, "EXIT_001", "CLOSED_TARGET")

    async def test_exit_rejected_retries_market_exit(
        self, coordinator, redis_store, mock_db, mock_order_service, mock_kite
    ):
        """
        SM is MANAGING with exit initiated, but exit order REJECTED.
        Reconciliation should retry MARKET exit.
        """
        sm = _make_sm("TATAMOTORS", redis_store, mock_db, mock_order_service)
        _make_open_position(sm, qty=40)
        sm.position._exit_initiated = True
        sm.position.exit_order_id = "EXIT_BAD"
        sm.position.exit_reason = "CLOSED_TIME"
        coordinator.active_state_machines["TATAMOTORS"] = sm

        mock_kite.orders.return_value = [
            {
                "order_id": "EXIT_BAD",
                "status": "REJECTED",
                "tradingsymbol": "TATAMOTORS",
                "status_message": "RMS blocked",
            }
        ]

        await coordinator.reconcile_orders(mock_kite)

        mock_order_service.place_exit_market.assert_called_once_with(
            "TATAMOTORS",
            40,
            reason="CLOSED_TIME",
        )

    async def test_sl_triggered_missed_postback(
        self, coordinator, redis_store, mock_db, mock_order_service, mock_kite
    ):
        """
        SM is MANAGING. SL order status is COMPLETE in Kite orders but SM hasn't seen postback.
        reconcile_orders should call on_sl_triggered.
        """
        sm = _make_sm("TCS", redis_store, mock_db, mock_order_service)
        _make_open_position(sm)
        sm._close_position = AsyncMock()  # spy instead of running full close
        coordinator.active_state_machines["TCS"] = sm

        mock_kite.orders.return_value = [
            {
                "order_id": "SL_001",
                "status": "COMPLETE",
                "average_price": 462.0,
                "tradingsymbol": "TCS",
                "exchange_update_timestamp": NOW_IST.isoformat(),
            }
        ]

        await coordinator.reconcile_orders(mock_kite)

        # Position should have been closed via on_sl_triggered
        sm._close_position.assert_called_once()
        call_kwargs = sm._close_position.call_args
        # exit_price should be the avg_price from the order
        assert call_kwargs[1].get("exit_price") == 462.0 or call_kwargs[0][0] == 462.0

    async def test_sl_rejected_triggers_emergency_close(
        self, coordinator, redis_store, mock_db, mock_order_service, mock_kite
    ):
        """
        SM is MANAGING. SL order REJECTED in Kite → emergency market close.
        """
        sm = _make_sm("HDFC", redis_store, mock_db, mock_order_service)
        _make_open_position(sm, qty=75)
        coordinator.active_state_machines["HDFC"] = sm

        mock_kite.orders.return_value = [
            {
                "order_id": "SL_001",
                "status": "REJECTED",
                "tradingsymbol": "HDFC",
                "average_price": 0.0,
            }
        ]

        await coordinator.reconcile_orders(mock_kite)

        # Emergency market sell must fire
        mock_order_service.place_exit_market.assert_called_once_with(
            "HDFC", 75, reason="sl_rejected"
        )

    async def test_fill_missed_triggers_on_order_filled(
        self, coordinator, redis_store, mock_db, mock_order_service, mock_kite
    ):
        """
        SM is ACTION_PENDING. Entry fill missed by WS.
        reconcile_orders should call sm.on_order_filled.
        """
        from engine.strategy.state_machine import StrategyState

        sm = _make_sm("SBIN", redis_store, mock_db, mock_order_service)
        sm.state = StrategyState.ACTION_PENDING
        sm._pending_order_id = "ENTRY_SBIN_001"
        sm.on_order_filled = AsyncMock()
        coordinator.active_state_machines["SBIN"] = sm

        mock_kite.orders.return_value = [
            {
                "order_id": "ENTRY_SBIN_001",
                "status": "COMPLETE",
                "average_price": 503.5,
                "filled_quantity": 250,
                "tradingsymbol": "SBIN",
                "exchange_update_timestamp": NOW_IST.isoformat(),
            }
        ]

        await coordinator.reconcile_orders(mock_kite)

        sm.on_order_filled.assert_called_once()
        call_args = sm.on_order_filled.call_args
        assert call_args[1].get("fill_price") == 503.5 or call_args[0][1] == 503.5
        assert call_args[1].get("fill_qty") == 250 or call_args[0][2] == 250

    async def test_entry_rejected_triggers_on_order_rejected(
        self, coordinator, redis_store, mock_db, mock_order_service, mock_kite
    ):
        """
        SM is ACTION_PENDING. Entry order REJECTED in Kite.
        reconcile_orders should call sm.on_order_rejected.
        """
        from engine.strategy.state_machine import StrategyState

        sm = _make_sm("AXISBANK", redis_store, mock_db, mock_order_service)
        sm.state = StrategyState.ACTION_PENDING
        sm._pending_order_id = "ENTRY_AXIS_001"
        sm.on_order_rejected = AsyncMock()
        coordinator.active_state_machines["AXISBANK"] = sm

        mock_kite.orders.return_value = [
            {
                "order_id": "ENTRY_AXIS_001",
                "status": "REJECTED",
                "status_message": "Insufficient funds",
                "tradingsymbol": "AXISBANK",
                "average_price": 0.0,
            }
        ]

        await coordinator.reconcile_orders(mock_kite)

        sm.on_order_rejected.assert_called_once_with("ENTRY_AXIS_001", "Insufficient funds")

    async def test_reconcile_noops_when_no_active_sms(
        self, coordinator, mock_kite
    ):
        """
        Empty coordinator → reconcile should exit without calling kite.orders().
        """
        await coordinator.reconcile_orders(mock_kite)
        mock_kite.orders.assert_not_called()

    async def test_reconcile_handles_kite_api_failure_gracefully(
        self, coordinator, redis_store, mock_db, mock_order_service, mock_kite
    ):
        """
        Kite API fails during reconciliation → should log and not crash engine.
        """
        from engine.strategy.state_machine import StrategyState

        sm = _make_sm("ICICIBANK", redis_store, mock_db, mock_order_service)
        sm.state = StrategyState.MANAGING
        _make_open_position(sm)
        coordinator.active_state_machines["ICICIBANK"] = sm

        mock_kite.orders.side_effect = Exception("API error")

        # Should not raise — just log and return
        await coordinator.reconcile_orders(mock_kite)
