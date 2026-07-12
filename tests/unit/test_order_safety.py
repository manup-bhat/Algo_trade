"""
tests/unit/test_order_safety.py — Phase 5 real-trading safety.

Covers:
  - on_order_filled idempotency (no double position / SL / margin on racing fills)
  - OrderTracker duplicate-postback dedup (a repeated COMPLETE fills once)
  - Partial-fill handling: CANCELLED/REJECTED with filled_qty > 0 manages the fill
  - Reconciliation metrics on the coordinator
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock

import fakeredis.aioredis
import pytest
import pytz

from engine.orders.fill_timeout import FillTimeoutManager
from engine.orders.order_service import OrderService
from engine.orders.order_tracker import OrderTracker
from engine.store.redis_store import RedisStore
from engine.strategy.coordinator import Coordinator
from engine.strategy.state_machine import (
    ConsolidationData,
    StrategyState,
    SymbolStateMachine,
)

IST = pytz.timezone("Asia/Kolkata")


def _ts() -> datetime.datetime:
    return datetime.datetime.now(IST).replace(second=0, microsecond=0)


@pytest.fixture
def redis_store():
    return RedisStore(fakeredis.aioredis.FakeRedis(decode_responses=True))


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.open_trade.return_value = 42
    db.write_signal.return_value = 1
    return db


def _pending_sm(redis_store, mock_db) -> SymbolStateMachine:
    sm = SymbolStateMachine(
        symbol="TEST",
        instrument_token=123,
        redis_store=redis_store,
        db_writer=mock_db,
        order_service=OrderService(kite=None),
        order_tracker=OrderTracker(),
        fill_timeout_manager=FillTimeoutManager(),
    )
    sm.consolidation = ConsolidationData(
        start_time=_ts(), high=100.0, low=95.0, swing_low=95.0
    )
    sm._is_paper_entry = True
    sm._trade_mode = "PAPER"
    sm.state = StrategyState.ACTION_PENDING
    return sm


class TestFillIdempotency:
    @pytest.mark.asyncio
    async def test_duplicate_fill_processed_once(self, redis_store, mock_db):
        sm = _pending_sm(redis_store, mock_db)
        await sm.on_order_filled("ORD1", 100.0, 10, _ts())
        assert sm.state == StrategyState.MANAGING
        assert sm.position is not None
        assert mock_db.open_trade.await_count == 1

        # A racing/duplicate fill must be a no-op (state already MANAGING).
        await sm.on_order_filled("ORD1", 100.0, 10, _ts())
        assert mock_db.open_trade.await_count == 1

    @pytest.mark.asyncio
    async def test_fill_in_progress_flag_blocks_reentry(self, redis_store, mock_db):
        sm = _pending_sm(redis_store, mock_db)
        sm._fill_in_progress = True  # simulate an in-flight fill mid-await
        await sm.on_order_filled("ORD2", 100.0, 10, _ts())
        assert mock_db.open_trade.await_count == 0
        assert sm.position is None


class TestPostbackDedup:
    @pytest.mark.asyncio
    async def test_duplicate_complete_fills_once(self):
        ot = OrderTracker()
        ot.register_entry("E1", "REL")
        sm = AsyncMock()
        coord = SimpleNamespace(active_state_machines={"REL": sm}, _order_service=AsyncMock())
        db = AsyncMock()
        msg = {
            "order_id": "E1", "status": "COMPLETE", "tradingsymbol": "REL",
            "average_price": 100.0, "filled_quantity": 10,
        }
        await ot.on_postback(msg, coord, db)
        await ot.on_postback(dict(msg), coord, db)  # duplicate
        assert sm.on_order_filled.await_count == 1


class TestPartialFill:
    @pytest.mark.asyncio
    async def test_cancelled_with_partial_fill_manages_position(self):
        ot = OrderTracker()
        ot.register_entry("E2", "REL2")
        sm = AsyncMock()
        coord = SimpleNamespace(active_state_machines={"REL2": sm}, _order_service=AsyncMock())
        db = AsyncMock()
        msg = {
            "order_id": "E2", "status": "CANCELLED", "tradingsymbol": "REL2",
            "average_price": 99.5, "filled_quantity": 5,
        }
        await ot.on_postback(msg, coord, db)
        sm.on_order_filled.assert_awaited_once_with("E2", 99.5, 5, ANY)
        assert sm.on_order_rejected.await_count == 0

    @pytest.mark.asyncio
    async def test_rejected_with_no_fill_abandons(self):
        ot = OrderTracker()
        ot.register_entry("E3", "REL3")
        sm = AsyncMock()
        coord = SimpleNamespace(active_state_machines={"REL3": sm}, _order_service=AsyncMock())
        db = AsyncMock()
        msg = {
            "order_id": "E3", "status": "REJECTED", "tradingsymbol": "REL3",
            "status_message": "insufficient funds", "filled_quantity": 0,
        }
        await ot.on_postback(msg, coord, db)
        assert sm.on_order_rejected.await_count == 1
        assert sm.on_order_filled.await_count == 0


class TestReconcileMetrics:
    @pytest.mark.asyncio
    async def test_reconcile_increments_metric(self, redis_store, mock_db):
        coord = Coordinator(redis_store, mock_db)
        kite = AsyncMock()
        kite.orders.return_value = []
        await coord.reconcile_orders(kite)
        stats = coord.get_stats()
        assert stats["reconcile_count"] == 1
        assert stats["last_reconcile_at"] is not None
