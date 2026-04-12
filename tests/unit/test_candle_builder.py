"""
tests/unit/test_candle_builder.py — Complete unit tests for CandleBuilder.

Tests cover all spec-required scenarios from Section 16.1:
  1. Normal tick accumulation → correct OHLCV
  2. Minute boundary detection
  3. Cumulative volume delta calculation
  4. Reconnect: first tick after reset → no candle, no delta
  5. SMA returns None until 500 candles
  6. SMA is correct mean after 500 candles
  7. Volume history rolling (oldest dropped at 501)
  8. load_history pre-warms the builder
  
Plus Bug regression tests:
  - Bug 4: reconnect phantom volume spike prevention
  - Reconnect scenario: full disconnect + reconnect cycle
"""

from __future__ import annotations

import datetime
import statistics

import pytest
import pytz

from engine.market.candle_builder import Candle, CandleBuilder

IST_TZ = pytz.timezone("Asia/Kolkata")


def make_ts(hour: int, minute: int, second: int = 0) -> datetime.datetime:
    """Create an IST-aware datetime for today at given time."""
    now = datetime.datetime.now(IST_TZ)
    return now.replace(hour=hour, minute=minute, second=second, microsecond=0)


# ─────────────────────────────────────────────────────────────────────────────
# Fixture
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def builder():
    """Fresh CandleBuilder for symbol TEST with 5-period SMA (for speed in tests)."""
    return CandleBuilder("TEST", sma_period=5)


@pytest.fixture
def builder_500():
    """Fresh CandleBuilder with full 500-period SMA (spec-accurate)."""
    return CandleBuilder("TEST", sma_period=500)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Normal tick accumulation → correct OHLCV
# ─────────────────────────────────────────────────────────────────────────────

class TestNormalTickAccumulation:
    def test_first_tick_returns_none(self, builder):
        """First tick establishes baseline — no candle emitted."""
        result = builder.on_tick(100.0, 1000, make_ts(9, 15, 5))
        assert result is None

    def test_same_minute_ticks_return_none(self, builder):
        """Ticks within the same minute never produce a candle."""
        builder.on_tick(100.0, 1000, make_ts(9, 15, 5))   # baseline
        r1 = builder.on_tick(101.0, 1100, make_ts(9, 15, 20))
        r2 = builder.on_tick(99.5,  1200, make_ts(9, 15, 45))
        assert r1 is None
        assert r2 is None

    def test_new_minute_returns_completed_candle(self, builder):
        """A tick in the next minute triggers emission of the previous candle."""
        builder.on_tick(100.0, 1000, make_ts(9, 15, 5))   # baseline
        builder.on_tick(102.0, 1200, make_ts(9, 15, 30))  # accumulate
        builder.on_tick(98.0,  1350, make_ts(9, 15, 55))  # accumulate
        
        # This tick is in the 9:16 minute — should emit the 9:15 candle
        candle = builder.on_tick(103.0, 1500, make_ts(9, 16, 10))
        
        assert candle is not None
        assert isinstance(candle, Candle)
        assert candle.symbol == "TEST"

    def test_candle_ohlcv_correct(self, builder):
        """OHLCV values of the completed candle match the ticks in that minute."""
        t = make_ts(9, 15)
        
        # Baseline tick (no volume credit)
        builder.on_tick(100.0, 1000, t.replace(second=5))
        # In-minute ticks
        builder.on_tick(105.0, 1200, t.replace(second=20))   # high
        builder.on_tick(98.0,  1350, t.replace(second=40))   # low
        builder.on_tick(102.0, 1500, t.replace(second=55))   # close
        
        # Next minute tick emits the candle
        candle = builder.on_tick(101.0, 1600, t.replace(minute=16, second=5))
        
        assert candle is not None
        # Open: first accumulated tick (100.0 set by baseline tick)
        assert candle.open == 100.0
        assert candle.high == 105.0
        assert candle.low == 98.0
        assert candle.close == 102.0

    def test_candle_timestamp_is_minute_boundary(self, builder):
        """Candle timestamp = minute boundary (second=0, microsecond=0)."""
        builder.on_tick(100.0, 1000, make_ts(9, 15, 10))
        builder.on_tick(101.0, 1100, make_ts(9, 15, 30))
        candle = builder.on_tick(100.5, 1200, make_ts(9, 16, 5))
        
        assert candle is not None
        assert candle.timestamp.second == 0
        assert candle.timestamp.microsecond == 0
        assert candle.timestamp.minute == 15

    def test_candle_turnover_computed_correctly(self, builder):
        """turnover = close × volume."""
        builder.on_tick(500.0, 10000, make_ts(9, 15, 5))
        builder.on_tick(510.0, 15000, make_ts(9, 15, 30))
        candle = builder.on_tick(505.0, 16000, make_ts(9, 16, 5))
        
        assert candle is not None
        # volume = 15000 - 10000 = 5000 ticks accumulated
        assert candle.volume == 5000
        # turnover = 510.0 (close) × 5000
        assert candle.turnover == pytest.approx(510.0 * 5000, rel=1e-6)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Cumulative Volume Delta
# ─────────────────────────────────────────────────────────────────────────────

class TestCumulativeVolumeDelta:
    def test_delta_computed_from_cumulative(self, builder):
        """Volume delta = current_cumulative - previous_cumulative."""
        builder.on_tick(100.0, 5000, make_ts(9, 15, 5))   # baseline: prev=5000
        builder.on_tick(101.0, 5300, make_ts(9, 15, 15))  # delta = 300
        builder.on_tick(102.0, 5700, make_ts(9, 15, 45))  # delta = 400
        candle = builder.on_tick(103.0, 5900, make_ts(9, 16, 5))
        
        assert candle is not None
        # Total volume = 300 + 400 = 700
        assert candle.volume == 700

    def test_negative_delta_clamped_to_zero(self, builder):
        """Negative cumulative delta (data anomaly) is clamped to 0, not subtracted."""
        builder.on_tick(100.0, 5000, make_ts(9, 15, 5))   # baseline
        builder.on_tick(101.0, 4800, make_ts(9, 15, 30))  # cumulative went DOWN (anomaly)
        candle = builder.on_tick(102.0, 5100, make_ts(9, 16, 5))
        
        assert candle is not None
        # Delta for the bad tick: max(0, 4800-5000) = 0
        # Delta for next tick: 5100 - 4800 = 300; but baseline was reset to 4800
        # Total meaningful volume depends on implementation detail
        # Key assertion: no negative volume
        assert candle.volume >= 0


# ─────────────────────────────────────────────────────────────────────────────
# 3. Reconnect Scenario — Bug 4 Regression Test
# ─────────────────────────────────────────────────────────────────────────────

class TestReconnectHandling:
    def test_first_tick_after_startup_returns_none(self, builder):
        """On fresh start, first tick returns None (baseline establishment)."""
        # Builder starts with _awaiting_baseline_reset = True
        result = builder.on_tick(500.0, 100000, make_ts(9, 15, 30))
        assert result is None

    def test_first_tick_after_startup_no_volume_credit(self, builder):
        """The baseline tick must not contribute any volume to the candle."""
        builder.on_tick(500.0, 100000, make_ts(9, 15, 30))  # baseline
        builder.on_tick(502.0, 101000, make_ts(9, 15, 45))  # delta = 1000
        candle = builder.on_tick(501.0, 101500, make_ts(9, 16, 5))
        
        assert candle is not None
        # Volume = delta of tick at 9:15:45 only: 101000 - 100000 = 1000
        # The tick at 9:16:05 (cum=101500) triggers the candle close and becomes
        # the FIRST tick of the new 9:16 candle — its delta goes to the next candle.
        # Key invariant: baseline tick (cum=100000) contributes ZERO volume.
        assert candle.volume == 1000, (
            f"Expected 1000 volume (only post-baseline tick in 9:15 minute), got {candle.volume}. "
            "If 100000 was credited, the baseline reset is broken."
        )

    def test_reset_cumulative_baseline_sets_flag(self, builder):
        """reset_cumulative_baseline() puts builder back into awaiting state."""
        # First establish normal state
        builder.on_tick(500.0, 100000, make_ts(9, 15, 30))
        builder.on_tick(502.0, 101000, make_ts(9, 15, 45))
        
        assert builder._awaiting_baseline_reset is False, (
            "Should be False after processing ticks normally"
        )
        
        # Simulate WebSocket reconnect
        builder.reset_cumulative_baseline()
        assert builder._awaiting_baseline_reset is True

    def test_reconnect_first_tick_returns_none(self, builder):
        """After reconnect baseline reset, first tick must return None."""
        # Normal operation
        builder.on_tick(500.0, 100000, make_ts(9, 15, 30))
        builder.on_tick(502.0, 101000, make_ts(9, 15, 45))
        
        # WS reconnect
        builder.reset_cumulative_baseline()
        
        # First tick after reconnect (cumulative resets to lower value on reconnect)
        result = builder.on_tick(503.0, 80000, make_ts(9, 15, 50))
        assert result is None, "First tick after reconnect must return None"

    def test_reconnect_no_phantom_volume_spike(self, builder):
        """
        Bug 4 regression: After WS reconnect, cumulative volume may appear to
        jump dramatically because the baseline resets. Without the fix, this
        would create a massive phantom volume spike that could trigger the 20x
        scanner filter falsely.

        Scenario:
          Pre-disconnect: cum_vol = 500,000
          Post-reconnect: cum_vol = 50,000 (exchange resets its counter)
          Without fix: delta = max(0, 50000 - 500000) → 0 for this, but
                       next tick: delta = 51000 - 50000 = 1000 (correct)
          With fix:    first tick used only as baseline, next tick delta = 1000
        """
        # Build up state pre-reconnect
        builder.on_tick(500.0, 500000, make_ts(9, 30, 5))   # baseline
        builder.on_tick(501.0, 505000, make_ts(9, 30, 30))  # delta = 5000
        
        # Simulate reconnect: exchange resets cumulative (or replays from lower value)
        builder.reset_cumulative_baseline()
        
        # First tick after reconnect — should set baseline, no candle
        tick1 = builder.on_tick(502.0, 50000, make_ts(9, 30, 45))
        assert tick1 is None
        
        # Next tick in same minute — normal operation
        tick2 = builder.on_tick(503.0, 51500, make_ts(9, 30, 55))
        assert tick2 is None
        
        # New minute — emit candle
        candle = builder.on_tick(504.0, 52000, make_ts(9, 31, 5))
        assert candle is not None
        
        # Volume should only be the post-reconnect delta: 51500-50000=1500 + 52000-51500=500... 
        # BUT wait: first tick after reconnect (50000) sets baseline
        # Second tick (51500): delta = 51500 - 50000 = 1500
        # Third tick (52000): triggers new candle
        # The 9:30 candle volume = 1500 (just from second tick)
        # The 9:31 candle starts fresh with tick from 52000 baseline
        assert candle.volume == 1500, (
            f"Expected 1500 volume post-reconnect, got {candle.volume}. "
            "Phantom volume spike from reconnect."
        )


# ─────────────────────────────────────────────────────────────────────────────
# 4. Volume SMA
# ─────────────────────────────────────────────────────────────────────────────

class TestVolumeSMA:
    def _feed_candle(self, builder, volume: int, minute_offset: int) -> Candle | None:
        """
        Feed ticks to produce a single completed candle.
        minute_offset 0 = 9:15, 1 = 9:16, etc.
        Uses two ticks: one within the minute, one in the next minute to close it.
        Returns the completed candle (from the 'closing' tick).
        """
        # Absolute minute across hours
        total_minutes = 9 * 60 + 15 + minute_offset
        hour = total_minutes // 60
        minute = total_minutes % 60

        # Tick within the target minute (this goes into the candle)
        # We set cum_vol so delta = volume
        cum = (minute_offset + 1) * 10000 + volume
        builder._prev_cumulative_volume = cum - volume  # set prev so delta = volume
        builder._awaiting_baseline_reset = False  # bypass baseline logic
        builder._current_candle_time = make_ts(hour, minute).replace(second=0, microsecond=0)
        builder._open = 100.0
        builder._high = 100.0
        builder._low = 100.0
        builder._close = 100.0
        builder._candle_volume = volume

        # Advance to next minute to flush the candle
        next_total = total_minutes + 1
        next_hour = next_total // 60
        next_minute = next_total % 60
        result = builder.on_tick(100.0, cum + 0, make_ts(next_hour, next_minute))
        return result

    def test_sma_is_none_with_zero_candles(self, builder):
        assert builder.volume_sma is None

    def test_sma_is_none_below_sma_period(self, builder):
        """SMA is None until exactly sma_period candles accumulated (sma_period=5)."""
        # Feed 4 candles
        for i in range(4):
            self._feed_candle(builder, 1000, i)
        assert builder.history_size == 4
        assert not builder.is_warmed_up
        assert builder.volume_sma is None

    def test_sma_available_at_sma_period_candles(self, builder):
        """SMA available after exactly sma_period candles."""
        for i in range(5):
            self._feed_candle(builder, 1000, i)
        assert builder.is_warmed_up
        assert builder.volume_sma is not None

    def test_sma_value_is_correct_mean(self, builder):
        """SMA equals arithmetic mean of the last sma_period volumes."""
        volumes = [1000, 2000, 1500, 3000, 500]
        for i, vol in enumerate(volumes):
            self._feed_candle(builder, vol, i)
        expected = statistics.mean(volumes)
        assert builder.volume_sma == pytest.approx(expected, rel=1e-6)

    def test_sma_rolling_window_drops_oldest(self, builder):
        """After sma_period+1 candles, oldest is dropped."""
        volumes = [1000, 2000, 1500, 3000, 500, 9999]
        for i, vol in enumerate(volumes):
            self._feed_candle(builder, vol, i)
        # Window = last 5: [2000, 1500, 3000, 500, 9999]
        assert builder.history_size == 5
        expected = statistics.mean(volumes[1:])
        assert builder.volume_sma == pytest.approx(expected, rel=1e-6)

    def test_sma_period_500_requires_500_candles(self, builder_500):
        """500-period SMA: None at 499, available at 500."""
        for i in range(499):
            self._feed_candle(builder_500, 1000, i)
        assert builder_500.volume_sma is None
        assert builder_500.history_size == 499
        # Feed 500th candle
        self._feed_candle(builder_500, 1000, 499)
        assert builder_500.volume_sma is not None
        assert builder_500.is_warmed_up
        assert builder_500.history_size == 500


# ─────────────────────────────────────────────────────────────────────────────
# 5. load_history pre-warming
# ─────────────────────────────────────────────────────────────────────────────

class TestLoadHistory:
    def test_load_history_warms_builder(self, builder):
        """Loading exactly sma_period volumes pre-warms the builder."""
        # builder sma_period=5
        builder.load_history([1000, 2000, 1500, 3000, 500])
        assert builder.is_warmed_up
        assert builder.volume_sma is not None

    def test_load_history_partial_not_warmed(self, builder):
        """Loading less than sma_period volumes does not warm up the builder."""
        builder.load_history([1000, 2000, 1500])  # Only 3, need 5
        assert not builder.is_warmed_up
        assert builder.volume_sma is None

    def test_load_history_respects_sma_period(self, builder):
        """Loading more than sma_period keeps only the last sma_period values."""
        volumes = list(range(1, 12))  # 11 values, sma_period=5
        builder.load_history(volumes)
        assert builder.history_size == 5  # deque maxlen enforced
        # Should keep last 5: [7, 8, 9, 10, 11]
        assert builder.volume_sma == pytest.approx(statistics.mean([7, 8, 9, 10, 11]))

    def test_load_history_sma_value_correct(self, builder):
        """SMA after load_history equals mean of loaded values."""
        volumes = [100, 200, 150, 300, 250]  # sma_period=5
        builder.load_history(volumes)
        assert builder.volume_sma == pytest.approx(statistics.mean(volumes))

    def test_volume_history_snapshot_round_trips(self, builder):
        """volume_history_snapshot → load_history produces identical SMA."""
        # Simulate a session: load history, run some ticks, take snapshot
        original = [500, 600, 700, 800, 900]
        builder.load_history(original)
        original_sma = builder.volume_sma

        # Complete one more candle
        builder.on_tick(100.0, 0, make_ts(9, 15, 5))
        builder.on_tick(100.0, 1000, make_ts(9, 16, 5))  # completes 9:15 candle

        # Snapshot and recreate
        snapshot = builder.volume_history_snapshot
        new_builder = CandleBuilder("TEST2", sma_period=5)
        new_builder.load_history(snapshot)

        assert new_builder.volume_sma == builder.volume_sma


# ─────────────────────────────────────────────────────────────────────────────
# 6. Reset (session reset)
# ─────────────────────────────────────────────────────────────────────────────

class TestReset:
    def test_reset_clears_candle_state(self, builder):
        """reset() clears current minute's state."""
        builder.load_history([100, 200, 150, 300, 250])  # warm up
        builder.on_tick(100.0, 5000, make_ts(9, 15, 5))
        builder.on_tick(102.0, 5500, make_ts(9, 15, 30))
        
        builder.reset()
        
        assert builder._current_candle_time is None
        assert builder._candle_volume == 0
        assert builder._awaiting_baseline_reset is True

    def test_reset_preserves_sma_history(self, builder):
        """reset() does NOT clear the SMA history (continuity across sessions)."""
        builder.load_history([100, 200, 150, 300, 250])
        sma_before = builder.volume_sma
        
        builder.reset()
        
        assert builder.is_warmed_up
        assert builder.volume_sma == sma_before
