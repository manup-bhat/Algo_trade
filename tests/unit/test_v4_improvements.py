"""Tests for v4 strategy improvements: ATR + VWAP indicators and the opt-in
Chandelier ATR trailing stop.

- CandleBuilder.atr / .vwap (new indicators)
- SymbolStateMachine on_tick Chandelier trailing (flag-gated, default OFF)
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock

import pytest
import pytz

from engine.market.candle_builder import CandleBuilder
from engine.strategy.state_machine import (
    OpenPosition,
    StrategyState,
    SymbolStateMachine,
)

IST = pytz.timezone("Asia/Kolkata")


def ts(hour: int, minute: int) -> datetime.datetime:
    return datetime.datetime.now(IST).replace(hour=hour, minute=minute, second=0, microsecond=0)


def _run_candles(builder: CandleBuilder, per_minute_prices: list[list[float]]) -> None:
    """Drive ticks so each inner list becomes one completed 1-min candle.

    The candle for minute i is emitted on the first tick of minute i+1, so the
    LAST minute is left forming (not emitted) — feed one extra minute to flush.
    """
    cum = 0
    for i, prices in enumerate(per_minute_prices):
        minute_ts = ts(10, i)
        for p in prices:
            cum += 1000
            builder.on_tick(float(p), cum, minute_ts)


# ── ATR ──────────────────────────────────────────────────────────────────────

def test_atr_none_before_period():
    b = CandleBuilder("TEST", sma_period=5, atr_period=3)
    assert b.atr is None
    # Two completed candles < atr_period(3)
    _run_candles(b, [[100, 101, 99, 100], [100, 102, 100, 101], [101, 103, 101, 102]])
    # Only 2 candles emitted so far (3rd minute still forming) → still None
    assert b.atr is None


def test_atr_available_and_positive_after_period():
    b = CandleBuilder("TEST", sma_period=5, atr_period=3)
    _run_candles(
        b,
        [
            [100, 101, 99, 100],
            [100, 102, 100, 101],
            [101, 103, 101, 102],
            [102, 104, 102, 103],
            [103, 105, 103, 104],  # flushes the 4th candle
        ],
    )
    assert b.atr is not None
    assert b.atr > 0


def test_reset_clears_atr_and_vwap():
    b = CandleBuilder("TEST", sma_period=5, atr_period=3)
    _run_candles(
        b,
        [[100, 101, 99, 100], [100, 102, 100, 101], [101, 103, 101, 102], [102, 104, 102, 103]],
    )
    assert b.atr is not None or b.vwap is not None
    b.reset()
    assert b.atr is None
    assert b.vwap is None


# ── VWAP ───────────────────────────────────────────────────────────────────────

def test_vwap_none_before_any_candle():
    b = CandleBuilder("TEST", sma_period=5, atr_period=3)
    assert b.vwap is None


def test_vwap_within_price_range():
    b = CandleBuilder("TEST", sma_period=5, atr_period=3)
    _run_candles(
        b,
        [[100, 101, 99, 100], [100, 102, 100, 101], [101, 103, 101, 102], [102, 104, 102, 103]],
    )
    assert b.vwap is not None
    # VWAP must sit within the observed price envelope
    assert 99.0 <= b.vwap <= 104.0


# ── Chandelier trailing (opt-in) ───────────────────────────────────────────────

def _managing_sm(redis_store, atr_value: float | None):
    sm = SymbolStateMachine("TEST", 111, redis_store, MagicMock())
    sm._is_paper_entry = True

    class _StubBuilder:
        atr = atr_value

    sm._candle_builder = _StubBuilder()
    sm.state = StrategyState.MANAGING
    sm.position = OpenPosition(
        trade_id=1,
        entry_price=100.0,
        quantity=10,
        initial_sl=99.0,
        current_sl=100.0,   # already at breakeven
        risk_per_share=1.0,
        risk_amount=10.0,
        target_1r2=102.0,
        target_1r3=103.0,
        target_1r4=200.0,   # high so no 1:4 exit during the test
        entry_order_id="X",
        cost_trailed=True,
        profit_locked=True,
        highest_price=110.0,
    )
    return sm


@pytest.mark.asyncio
async def test_chandelier_trailing_ratchets_sl_when_enabled(redis_store, monkeypatch):
    from engine.strategies.ivbs.ivbs_config import cfg

    monkeypatch.setattr(cfg, "DYNAMIC_TRAILING_ENABLED", True)
    monkeypatch.setattr(cfg, "ATR_TRAIL_MULTIPLIER", 2.5)

    sm = _managing_sm(redis_store, atr_value=2.0)
    await sm.on_tick(110.0, ts(11, 0))

    # chandelier = highest(110) - 2.5 * ATR(2.0) = 105.0 ; 105 > 100 → ratchet up
    assert sm.position.current_sl == 105.0


@pytest.mark.asyncio
async def test_chandelier_disabled_by_default(redis_store):
    sm = _managing_sm(redis_store, atr_value=2.0)
    await sm.on_tick(110.0, ts(11, 0))
    # Flag default OFF → SL unchanged at breakeven
    assert sm.position.current_sl == 100.0


@pytest.mark.asyncio
async def test_chandelier_never_loosens(redis_store, monkeypatch):
    from engine.strategies.ivbs.ivbs_config import cfg

    monkeypatch.setattr(cfg, "DYNAMIC_TRAILING_ENABLED", True)
    monkeypatch.setattr(cfg, "ATR_TRAIL_MULTIPLIER", 2.5)

    sm = _managing_sm(redis_store, atr_value=2.0)
    sm.position.current_sl = 106.0  # already tighter than chandelier(105)
    await sm.on_tick(110.0, ts(11, 0))
    assert sm.position.current_sl == 106.0  # not loosened downward

