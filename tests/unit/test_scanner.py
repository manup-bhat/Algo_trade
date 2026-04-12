"""
tests/unit/test_scanner.py — Boundary condition tests for scanner.evaluate().

All 6 filters tested at exact boundaries (spec §16.1):
  - volume = 20x SMA exactly → PASS
  - volume = 19.9x SMA → FAIL
  - turnover = 8Cr exactly → PASS
  - turnover just below 8Cr → FAIL
  - close = open × 0.995 exactly → PASS (flat candle)
  - close = open × 0.994 → FAIL (sell dump)
  - volume_sma = None → returns None
"""

from __future__ import annotations

import datetime
from collections import deque
from unittest.mock import MagicMock

import pytest
import pytz

from engine.market.candle_builder import Candle
from engine.strategy.scanner import evaluate, ImpactCandle

IST_TZ = pytz.timezone("Asia/Kolkata")


# ── Helpers ────────────────────────────────────────────────────────────────

def make_candle(
    symbol: str = "TEST",
    ts_hour: int = 10,
    ts_min: int = 30,
    open_: float = 500.0,
    high: float = 510.0,
    low: float = 498.0,
    close: float = 508.0,
    volume: int = 100_000,
    turnover: float | None = None,
) -> Candle:
    now = datetime.datetime.now(IST_TZ)
    ts = now.replace(hour=ts_hour, minute=ts_min, second=0, microsecond=0)
    if turnover is None:
        turnover = close * volume
    return Candle(
        symbol=symbol,
        timestamp=ts,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        turnover=turnover,
    )


def make_builder(sma_value: float | None, symbol: str = "TEST") -> MagicMock:
    """Create a mock CandleBuilder with a specific volume_sma return value."""
    builder = MagicMock()
    builder.volume_sma = sma_value
    builder.is_warmed_up = sma_value is not None
    return builder


# The SMA needed for a 20x spike: if volume=100_000, sma=5000 gives 20x
# turnover at close=508, volume=100_000 → 50_800_000 (5.08 Cr) — need to adjust
# For 8 Cr turnover: close × volume ≥ 8e7: at close=500, need volume ≥ 160_000
# Let's use: close=500, volume=200_000 → turnover=1e8 (10 Cr) ✓
# sma = 10_000 for 20x: 200_000 / 10_000 = 20x ✓

BASE_VOLUME = 200_000
BASE_SMA = 10_000    # 20x exactly
BASE_CLOSE = 500.0
BASE_OPEN = 498.0    # close/open = 500/498 > 0.995 ✓


def base_passing_candle(**overrides) -> Candle:
    """A candle that passes all 6 filters with default values."""
    defaults = dict(
        open_=BASE_OPEN,
        high=510.0,
        low=495.0,
        close=BASE_CLOSE,
        volume=BASE_VOLUME,
        turnover=BASE_CLOSE * BASE_VOLUME,  # = 1e8 = 10 Cr
    )
    defaults.update(overrides)
    return make_candle(**defaults)


class TestScannerWarmup:
    def test_none_sma_returns_none(self):
        """Filter 1: SMA=None → skip (warmup incomplete)."""
        candle = base_passing_candle()
        builder = make_builder(sma_value=None)
        result = evaluate(candle, builder)
        assert result is None

    def test_zero_sma_returns_none(self):
        """Filter 2: SMA=0 → skip (data issue)."""
        candle = base_passing_candle()
        builder = make_builder(sma_value=0.0)
        result = evaluate(candle, builder)
        assert result is None


class TestVolumeSpikeFilter:
    def test_exactly_20x_passes(self):
        """Volume = 20× SMA exactly → PASS (inclusive boundary)."""
        # volume=200_000, sma=10_000 → exactly 20x
        candle = base_passing_candle(volume=BASE_VOLUME)
        builder = make_builder(sma_value=float(BASE_VOLUME / 20))  # 10_000
        result = evaluate(candle, builder)
        assert result is not None
        assert isinstance(result, ImpactCandle)
        assert abs(result.spike_multiple - 20.0) < 0.001

    def test_just_below_20x_fails(self):
        """Volume = 19.9× SMA → FAIL."""
        sma = BASE_VOLUME / 19.9  # gives 19.9x
        candle = base_passing_candle(volume=BASE_VOLUME)
        builder = make_builder(sma_value=sma)
        result = evaluate(candle, builder)
        assert result is None

    def test_well_above_20x_passes(self):
        """Volume = 50× SMA → PASS."""
        sma = BASE_VOLUME / 50
        candle = base_passing_candle(volume=BASE_VOLUME)
        builder = make_builder(sma_value=sma)
        result = evaluate(candle, builder)
        assert result is not None
        assert result.spike_multiple > 20


class TestTurnoverFilter:
    def test_exactly_8cr_passes(self):
        """Turnover = ₹8,00,00,000 exactly → PASS."""
        turnover = 8_00_00_000  # 8 Crore exactly
        close = 500.0
        volume = int(turnover / close)  # 160_000 shares
        # SMA for 20x: volume / 20
        sma = volume / 20 - 1  # just above 20x
        candle = base_passing_candle(close=close, volume=volume, turnover=float(turnover))
        builder = make_builder(sma_value=float(volume / 20))  # exactly 20x
        result = evaluate(candle, builder)
        assert result is not None

    def test_just_below_8cr_fails(self):
        """Turnover = ₹7,99,99,999 → FAIL."""
        turnover = 7_99_99_999
        close = 500.0
        volume = 160_000
        candle = base_passing_candle(close=close, volume=volume, turnover=float(turnover))
        builder = make_builder(sma_value=float(volume / 20))
        result = evaluate(candle, builder)
        assert result is None

    def test_high_turnover_passes(self):
        """Turnover = ₹15 Crore → PASS."""
        candle = base_passing_candle(
            close=1000.0,
            volume=200_000,
            turnover=1000.0 * 200_000,  # 20 Cr
        )
        builder = make_builder(sma_value=200_000 / 20)  # 10_000
        result = evaluate(candle, builder)
        assert result is not None


class TestPriceRangeFilter:
    def test_price_below_min_fails(self):
        """Close = ₹49.99 (below MIN_PRICE=50) → FAIL."""
        close = 49.99
        volume = int(8_10_00_000 / close)  # ensure 8.1 Cr turnover
        candle = base_passing_candle(close=close, open_=49.0, volume=volume,
                                     turnover=close * volume)
        builder = make_builder(sma_value=volume / 20)
        result = evaluate(candle, builder)
        assert result is None

    def test_price_at_min_passes(self):
        """Close = ₹50.00 (exactly MIN_PRICE) → PASS."""
        close = 50.0
        volume = int(8_10_00_000 / close)
        candle = base_passing_candle(close=close, open_=49.8, volume=volume,
                                     turnover=close * volume)
        builder = make_builder(sma_value=volume / 20)
        result = evaluate(candle, builder)
        assert result is not None

    def test_price_above_max_fails(self):
        """Close = ₹5,001 (above MAX_PRICE=5000) → FAIL."""
        close = 5001.0
        volume = int(8_10_00_000 / close)
        candle = base_passing_candle(close=close, open_=5000.0, volume=volume,
                                     turnover=close * volume)
        builder = make_builder(sma_value=volume / 20)
        result = evaluate(candle, builder)
        assert result is None

    def test_price_at_max_passes(self):
        """Close = ₹5,000 (exactly MAX_PRICE) → PASS."""
        close = 5000.0
        volume = int(8_10_00_000 / close) + 10
        candle = base_passing_candle(close=close, open_=4990.0, volume=volume,
                                     turnover=close * volume)
        builder = make_builder(sma_value=volume / 20)
        result = evaluate(candle, builder)
        assert result is not None


class TestSellDumpFilter:
    def test_flat_candle_passes(self):
        """Close = open × 0.995 exactly → PASS (flat candle allowed)."""
        open_ = 500.0
        close = round(open_ * 0.995, 2)  # 497.50
        candle = base_passing_candle(open_=open_, close=close, volume=BASE_VOLUME,
                                     turnover=close * BASE_VOLUME)
        # Need turnover >= 8Cr: 497.5 × 200_000 = 9.95Cr ✓
        builder = make_builder(sma_value=BASE_SMA)
        result = evaluate(candle, builder)
        assert result is not None, (
            f"Flat candle (close={close}, open={open_}) should PASS but failed"
        )

    def test_too_red_candle_fails(self):
        """Close = open × 0.994 → FAIL (sell dump)."""
        open_ = 500.0
        close = round(open_ * 0.994, 2)  # 497.00
        candle = base_passing_candle(open_=open_, close=close, volume=BASE_VOLUME,
                                     turnover=close * BASE_VOLUME)
        builder = make_builder(sma_value=BASE_SMA)
        result = evaluate(candle, builder)
        assert result is None

    def test_green_candle_passes(self):
        """Close > open → PASS (green candle)."""
        open_ = 498.0
        close = 510.0
        candle = base_passing_candle(open_=open_, close=close, volume=BASE_VOLUME,
                                     turnover=close * BASE_VOLUME)
        builder = make_builder(sma_value=BASE_SMA)
        result = evaluate(candle, builder)
        assert result is not None


class TestImpactCandleFields:
    def test_impact_candle_fields_populated_correctly(self):
        """Verify all ImpactCandle fields match the input candle."""
        candle = base_passing_candle(volume=BASE_VOLUME)
        sma = float(BASE_SMA)
        builder = make_builder(sma_value=sma)
        result = evaluate(candle, builder, instrument_token=12345)

        assert result is not None
        assert result.symbol == "TEST"
        assert result.instrument_token == 12345
        assert result.volume == BASE_VOLUME
        assert result.volume_sma_500 == sma
        assert abs(result.spike_multiple - (BASE_VOLUME / sma)) < 0.001
        assert result.turnover == candle.turnover
        assert result.open == candle.open
        assert result.high == candle.high
        assert result.low == candle.low
        assert result.close == candle.close
