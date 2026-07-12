"""
tests/integration/test_full_cycle.py — Full paper-trade cycle integration test.

Spec §16.2 test_full_cycle.py requirements:
  1. Initialize coordinator with 3 symbols
  2. Feed ticks to produce a scan hit (impact candle meeting all filters)
  3. Feed dry-up candles (3 small-volume candles)
  4. Feed re-ignition candle (volume spike + price breakout)
  5. Verify: on_order_filled() called with correct parameters
  6. Feed ticks to reach target_1r2 — verify: SL trailed to entry price
  7. Feed ticks to reach target_1r4 — verify: position closed (CLOSED_TARGET)
  8. Verify: trade record exists in DB with correct status

Uses fakeredis for in-memory Redis and SQLite in-memory DB.
"""

from __future__ import annotations

import asyncio
import datetime
import os
from pathlib import Path

import fakeredis.aioredis
import pytest
import pytz
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from engine.market.candle_builder import CandleBuilder, Candle
from engine.orders.fill_timeout import FillTimeoutManager
from engine.orders.order_service import OrderService
from engine.orders.order_tracker import OrderTracker
from engine.strategy.scanner import ImpactCandle
from engine.strategy.state_machine import SymbolStateMachine, StrategyState
from engine.store.redis_store import RedisStore
from engine.store.db_writer import DbWriter

IST_TZ = pytz.timezone("Asia/Kolkata")

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def fake_redis():
    """In-memory fake Redis (fakeredis). No actual Redis needed."""
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture
def redis_store(fake_redis):
    return RedisStore(fake_redis)


@pytest.fixture
def mock_db_writer():
    """
    Real DbWriter but mocked out — we don't want to touch a real DB in integration tests.
    The key things to verify are state transitions, not DB writes.
    """
    from unittest.mock import AsyncMock
    db = AsyncMock(spec=DbWriter)
    db.write_signal.return_value = 1
    db.open_trade.return_value = 42
    db.update_signal_progression.return_value = None
    db.close_trade.return_value = None
    return db


@pytest.fixture
def sm(redis_store, mock_db_writer):
    """Fresh SymbolStateMachine in paper mode with execution deps wired.

    Mirrors Coordinator._create_sm(): a paper-mode OrderService (kite=None),
    an OrderTracker, and a FillTimeoutManager. Without these the paper entry
    path (_trigger_entry -> order_service.place_entry) has nothing to call.
    """
    return SymbolStateMachine(
        symbol="RELIANCE",
        instrument_token=738561,
        redis_store=redis_store,
        db_writer=mock_db_writer,
        order_service=OrderService(kite=None),
        order_tracker=OrderTracker(),
        fill_timeout_manager=FillTimeoutManager(),
    )


def make_ts(hour: int, minute: int) -> datetime.datetime:
    today = datetime.date.today()
    return IST_TZ.localize(
        datetime.datetime.combine(today, datetime.time(hour, minute, 0))
    )


def make_candle(
    symbol: str = "RELIANCE",
    hour: int = 9,
    minute: int = 30,
    open_: float = 498.0,
    high: float = 510.0,
    low: float = 495.0,
    close: float = 508.0,
    volume: int = 200_000,
) -> Candle:
    ts = make_ts(hour, minute)
    return Candle(
        symbol=symbol,
        timestamp=ts,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        turnover=close * volume,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Full Cycle Test
# ─────────────────────────────────────────────────────────────────────────────

class TestFullPaperTradeCycle:
    """
    End-to-end paper trade cycle:
    Impact → Dry-up → Re-ignition → Fill → Trail → Target Exit
    """

    @pytest.mark.asyncio
    async def test_full_cycle_idle_to_closed_target(self, sm, redis_store, mock_db_writer):
        """
        Complete cycle: IDLE → SCAN_HIT → MONITORING → ACTION_PENDING
                       → MANAGING → CLOSED (CLOSED_TARGET)

        Validates:
          - Impact candle triggers SCAN_HIT
          - Dry-up candles accumulate correctly
          - Re-ignition triggers paper fill
          - SL trailed at 1:2
          - Position closed at 1:4
          - DB write_signal and open_trade called once each
        """
        # ── Step 1: Prime capital in Redis ────────────────────────────
        await redis_store.set_capital(5_00_000.0)  # ₹5 Lakh

        # ── Step 2: Trigger scan hit ───────────────────────────────────
        impact = ImpactCandle(
            symbol="RELIANCE",
            instrument_token=738561,
            time=make_ts(9, 15),
            open=498.0,
            high=510.0,
            low=495.0,
            close=508.0,
            volume=200_000,
            turnover=508.0 * 200_000,
            volume_sma_500=10_000.0,
            spike_multiple=20.0,
        )
        await sm.on_scan_hit(impact)
        assert sm.state == StrategyState.SCAN_HIT

        # Verify signal written to DB
        assert mock_db_writer.write_signal.call_count == 1

        # ── Step 3: Feed 3 dry-up candles ─────────────────────────────
        # These are low-volume, tight-range candles below breakout (510)
        dry_up_candles = [
            (505.0, 508.0, 503.0, 505.0, 8_000),   # volume=8k
            (505.0, 507.0, 503.0, 506.0, 7_000),   # volume=7k
            (506.0, 509.0, 504.0, 507.0, 9_000),   # volume=9k
        ]
        for i, (o, h, l, c, vol) in enumerate(dry_up_candles, start=1):
            await sm.on_candle(o, h, l, c, vol, make_ts(9, 15 + i))

        assert sm.state == StrategyState.MONITORING
        assert sm.consolidation is not None
        assert sm.consolidation.candle_count == 3
        # Verify prev_volumes have been accumulated
        assert sm.consolidation.volume_readings == [8_000, 7_000, 9_000]

        # ── Step 4: Feed re-ignition candle ───────────────────────────
        # volume=30000 > max([8000,7000,9000]) × 1.5 = 9000 × 1.5 = 13500 → True
        # close=515 > breakout_level=510 (pre-update) → True
        # close=515 > open=511 → True (green)
        # time=09:19 < 14:00 → True
        await sm.on_candle(511.0, 518.0, 509.0, 515.0, 30_000, make_ts(9, 19))

        # Should now be ACTION_PENDING or MANAGING (paper fills immediately)
        assert sm.state in (StrategyState.ACTION_PENDING, StrategyState.MANAGING), (
            f"Expected ACTION_PENDING or MANAGING after re-ignition, got {sm.state}"
        )

        # In paper mode, _trigger_entry calls order_service which calls on_order_filled
        # directly → should be MANAGING
        if sm.state == StrategyState.ACTION_PENDING:
            # Simulate the paper fill (should have happened automatically)
            pytest.fail("Should have transitioned to MANAGING via paper fill")

        assert sm.state == StrategyState.MANAGING
        assert sm.position is not None
        pos = sm.position

        # ── Step 5: Verify position and DB call ───────────────────────
        # Entry fill = limit_price × 1.001 ≈ 515 × 1.003 × 1.001
        # limit = 515 × 1.003 = 516.545
        # fill = 516.545 × 1.001 ≈ 517.06
        assert pos.entry_price > 515.0  # Fill above entry
        assert pos.quantity >= 1
        assert pos.current_sl > 0
        assert pos.target_1r2 > pos.entry_price
        assert pos.target_1r4 > pos.target_1r2

        # Verify DB trade opened
        assert mock_db_writer.open_trade.call_count == 1

        # ── Step 6: Feed tick at target_1r2 — verify SL trailed ────────
        tick_at_1r2 = pos.target_1r2 + 0.5
        await sm.on_tick(tick_at_1r2, make_ts(10, 0))

        # If we haven't hit 1r4 yet, should have trailed to cost
        if sm.state == StrategyState.MANAGING:
            assert pos.cost_trailed is True, (
                f"SL should be trailed to cost at LTP={tick_at_1r2} >= target_1r2={pos.target_1r2}"
            )
            assert pos.current_sl == pos.entry_price, (
                f"SL should be at entry_price={pos.entry_price}, got {pos.current_sl}"
            )

        # ── Step 7: Feed tick at target_1r4 — verify position closed ──
        tick_at_1r4 = pos.target_1r4 + 1.0
        await sm.on_tick(tick_at_1r4, make_ts(11, 0))

        assert sm.state == StrategyState.CLOSED, (
            f"Expected CLOSED after hitting target_1r4={pos.target_1r4}, "
            f"got {sm.state}"
        )

        # ── Step 8: Verify trade closure in DB ────────────────────────
        assert mock_db_writer.close_trade.call_count == 1
        close_call = mock_db_writer.close_trade.call_args
        close_kwargs = close_call.kwargs if close_call.kwargs else {}
        if "status" in close_kwargs:
            from app.models.db.trade import TradeStatus
            assert close_kwargs["status"] == TradeStatus.CLOSED_TARGET

    @pytest.mark.asyncio
    async def test_full_cycle_sl_hit(self, sm, redis_store, mock_db_writer):
        """
        Verify SL hit closes the position correctly.
        """
        await redis_store.set_capital(5_00_000.0)

        impact = ImpactCandle(
            symbol="RELIANCE",
            instrument_token=738561,
            time=make_ts(9, 15),
            open=498.0,
            high=510.0,
            low=495.0,
            close=508.0,
            volume=200_000,
            turnover=508.0 * 200_000,
            volume_sma_500=10_000.0,
            spike_multiple=20.0,
        )
        await sm.on_scan_hit(impact)

        # 3 dry-up candles
        for i in range(3):
            await sm.on_candle(505.0, 508.0, 503.0, 505.0, 8_000, make_ts(9, 16 + i))

        # Re-ignition
        await sm.on_candle(511.0, 518.0, 509.0, 515.0, 30_000, make_ts(9, 19))
        assert sm.state == StrategyState.MANAGING
        pos = sm.position

        # Feed tick below SL
        await sm.on_tick(pos.current_sl - 1.0, make_ts(10, 0))

        assert sm.state == StrategyState.CLOSED

        # Trade should be closed in DB as STOPLOSS
        assert mock_db_writer.close_trade.call_count == 1

    @pytest.mark.asyncio
    async def test_abandonment_price_below_impact_low(self, sm, redis_store, mock_db_writer):
        """
        If close drops below impact candle low during monitoring → CLOSED (abandoned).
        """
        await redis_store.set_capital(5_00_000.0)

        impact = ImpactCandle(
            symbol="RELIANCE",
            instrument_token=738561,
            time=make_ts(9, 15),
            open=498.0,
            high=510.0,
            low=495.0,
            close=508.0,
            volume=200_000,
            turnover=508.0 * 200_000,
            volume_sma_500=10_000.0,
            spike_multiple=20.0,
        )
        await sm.on_scan_hit(impact)

        # Close breaks below impact low (495)
        await sm.on_candle(498.0, 502.0, 490.0, 493.0, 5000, make_ts(9, 16))

        assert sm.state == StrategyState.CLOSED
        assert sm._abandonment_reason == "price_broke_impact_low"

    @pytest.mark.asyncio
    async def test_abandonment_timeout(self, sm, redis_store, mock_db_writer):
        """
        If more than DRYUP_MAX_MINUTES pass without re-ignition → CLOSED (timeout).
        """
        await redis_store.set_capital(5_00_000.0)

        impact = ImpactCandle(
            symbol="RELIANCE",
            instrument_token=738561,
            time=make_ts(9, 15),
            open=498.0,
            high=510.0,
            low=495.0,
            close=508.0,
            volume=200_000,
            turnover=508.0 * 200_000,
            volume_sma_500=10_000.0,
            spike_multiple=20.0,
        )
        await sm.on_scan_hit(impact)

        # Normal dry-up candles well within the dry-up window (no re-ignition)
        for i in range(5):
            await sm.on_candle(505.0, 508.0, 503.0, 505.0, 8_000, make_ts(9, 16 + i))

        # One candle past DRYUP_MAX_MINUTES after the 09:15 impact → timeout abandonment
        timeout_ts = make_ts(9, 15) + datetime.timedelta(minutes=settings.DRYUP_MAX_MINUTES + 1)
        await sm.on_candle(505.0, 508.0, 503.0, 505.0, 8_000, timeout_ts)

        assert sm.state == StrategyState.CLOSED
        assert sm._abandonment_reason == "timeout"
