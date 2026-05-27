"""
tests/unit/test_second_spike_detector.py — Second Spike Detector unit tests.

Tests all 7 evaluation conditions:
  1. Prior spike record exists
  2. Gap >= SECOND_SPIKE_MIN_GAP_MINUTES (15 min)
  3. Volume ratio 50-100% of prior spike
  4. Absolute volume floor >= 10x SMA
  5. Price held: close >= prior_spike_close × 0.998 (green candle condition)
  6. High-ratio price confirm: at vol_ratio >= 80%, close > prior spike high
  7. Green candle: close > open

Missing conditions 5 and 6 coverage added.
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import pytest
import pytz

from engine.strategy.second_spike_detector import (
    PriorSpikeRecord,
    SecondSpikeDetector,
    SecondSpikeEntry,
)
from app.core.config import settings

IST_TZ = pytz.timezone("Asia/Kolkata")


def make_ts(hour: int, minute: int) -> datetime.datetime:
    now = datetime.datetime.now(IST_TZ)
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _eval(detector: SecondSpikeDetector, **kwargs) -> SecondSpikeEntry | None:
    """Helper: call evaluate_second_spike with defaults."""
    return detector.evaluate_second_spike(
        symbol=kwargs.get("symbol", "TEST"),
        candle_close=kwargs.get("candle_close", 500.0),
        candle_open=kwargs.get("candle_open", 499.0),
        candle_low=kwargs.get("candle_low", 498.0),
        candle_volume=kwargs.get("candle_volume", 100_000),
        candle_time=kwargs.get("candle_time", make_ts(10, 30)),
        volume_sma=kwargs.get("volume_sma", 10_000.0),
        tick_size=kwargs.get("tick_size", 0.05),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Helper to record a prior spike directly via PriorSpikeRecord
# ─────────────────────────────────────────────────────────────────────────────

def _record_prior(
    detector: SecondSpikeDetector,
    symbol: str = "TEST",
    spike_time: datetime.datetime | None = None,
    spike_close: float = 500.0,
    spike_high: float = 505.0,
    spike_low: float = 498.0,
    spike_volume: int = 200_000,
    inter_spike_lows: list[float] | None = None,
) -> None:
    """Record a prior spike directly and update inter-spike low tracking."""
    if spike_time is None:
        spike_time = make_ts(9, 30)
    record = PriorSpikeRecord(
        symbol=symbol,
        spike_time=spike_time,
        spike_close=spike_close,
        spike_high=spike_high,
        spike_low=spike_low,
        spike_volume=spike_volume,
        inter_spike_low=spike_low,
    )
    detector._records[symbol] = record

    # Update inter-spike low for all intermediate candles
    if inter_spike_lows:
        for low in inter_spike_lows:
            detector.update_inter_spike_low(symbol, low)


# ─────────────────────────────────────────────────────────────────────────────
# Condition Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSecondSpikeConditions:
    """Test all 7 conditions individually."""

    def test_condition1_no_prior_record_returns_none(self):
        """No prior spike record → None."""
        detector = SecondSpikeDetector()
        result = _eval(detector, symbol="NOSUCH")
        assert result is None

    def test_condition2_gap_too_small_returns_none(self):
        """Gap < 15 minutes → None."""
        detector = SecondSpikeDetector()
        _record_prior(detector, spike_time=make_ts(9, 30))

        # Candle only 10 min after prior spike → too soon
        result = _eval(detector, candle_time=make_ts(9, 40))
        assert result is None

    def test_condition2_gap_sufficient_returns_entry(self):
        """Gap >= 15 minutes → valid entry."""
        detector = SecondSpikeDetector()
        _record_prior(detector, spike_time=make_ts(9, 30), inter_spike_lows=[498.0])

        # Candle 16 min after prior spike
        result = _eval(detector, candle_time=make_ts(9, 46))
        assert result is not None
        assert result.gap_minutes >= 15

    def test_condition3_vol_ratio_too_low_returns_none(self):
        """Vol ratio < 50% → None."""
        detector = SecondSpikeDetector()
        _record_prior(detector, spike_volume=200_000, inter_spike_lows=[498.0])

        # Second spike is only 40% of first spike volume → too small
        result = _eval(detector, candle_volume=80_000, candle_time=make_ts(10, 30))
        assert result is None

    def test_condition3_vol_ratio_too_high_returns_none(self):
        """Vol ratio > 100% → None (unrelated event)."""
        detector = SecondSpikeDetector()
        _record_prior(detector, spike_volume=100_000, inter_spike_lows=[498.0])

        # Second spike is 120% of first → rejected as unrelated
        result = _eval(detector, candle_volume=120_000, candle_time=make_ts(10, 30))
        assert result is None

    def test_condition3_vol_ratio_50_to_100_valid(self):
        """Vol ratio 50-100% → valid entry."""
        detector = SecondSpikeDetector()
        _record_prior(detector, spike_volume=200_000, inter_spike_lows=[498.0])

        # 70% ratio → in the 50-100% sweet spot
        result = _eval(detector, candle_volume=140_000, candle_time=make_ts(10, 30))
        assert result is not None
        assert 0.5 <= result.vol_ratio <= 1.0

    def test_condition4_abs_volume_floor(self):
        """Absolute volume must be >= 10x SMA floor."""
        detector = SecondSpikeDetector()
        _record_prior(detector, spike_volume=200_000, inter_spike_lows=[498.0])

        # Small volume relative to SMA (5x, below 10x floor)
        result = _eval(
            detector,
            candle_volume=50_000,   # 5x vs 10x SMA
            volume_sma=10_000.0,
            candle_time=make_ts(10, 30),
        )
        assert result is None

    def test_condition5_price_not_held_returns_none(self):
        """Close < prior_spike_close × 0.998 → None (absorption failed)."""
        detector = SecondSpikeDetector()
        _record_prior(detector, spike_close=500.0, spike_volume=200_000, inter_spike_lows=[498.0])

        # Close dropped to 499 (below 499.0 = 500 × 0.998 floor)
        # Price collapsed between waves → reject
        result = _eval(
            detector,
            candle_close=498.0,   # Below price floor
            candle_open=497.5,
            candle_volume=120_000,
            candle_time=make_ts(10, 30),
        )
        assert result is None

    def test_condition5_price_held_returns_entry(self):
        """Close >= prior_spike_close × 0.998 → valid."""
        detector = SecondSpikeDetector()
        _record_prior(detector, spike_close=500.0, spike_volume=200_000, inter_spike_lows=[498.0])

        # Close at 500.5 (above 499.0 floor) → price held
        result = _eval(
            detector,
            candle_close=500.5,
            candle_open=499.5,
            candle_volume=120_000,
            candle_time=make_ts(10, 30),
        )
        assert result is not None

    def test_condition5_green_candle_required(self):
        """close <= open → red/flat candle → None (not institutional buy)."""
        detector = SecondSpikeDetector()
        _record_prior(detector, spike_close=500.0, spike_volume=200_000, inter_spike_lows=[498.0])

        # Green candle: close > open → passes
        green_result = _eval(
            detector,
            candle_close=501.0,
            candle_open=499.0,
            candle_volume=120_000,
            candle_time=make_ts(10, 30),
        )
        assert green_result is not None

        # Red candle: close < open → rejected
        red_result = _eval(
            detector,
            candle_close=499.0,
            candle_open=501.0,   # Open above close = red candle
            candle_volume=120_000,
            candle_time=make_ts(10, 30),
        )
        assert red_result is None


    def test_condition6_high_ratio_needs_price_confirm_or_extended_gap(self):
        """
        At vol_ratio >= 80%, close must be >= prior spike high * 1.005 (0.5% buffer).
        UNLESS the inter-spike gap is >= SECOND_SPIKE_EXTENDED_GAP_MINUTES (30 min),
        in which case the extended gap compensates and the signal is allowed.

        Research: At 80%+ volume, Wyckoff secondary test is borderline.
        Price confirms with a 0.5% buffer, OR time compensates with a 30-min extended gap.
        """
        detector = SecondSpikeDetector()
        _record_prior(detector, spike_close=500.0, spike_high=505.0, spike_volume=200_000, inter_spike_lows=[498.0])

        # SHORT gap (20 min) + no price confirm → REJECT
        # 80% volume, close=504 (below 505*1.005=507.525), gap=20 min (< 30 min)
        result_short_gap = _eval(
            detector,
            candle_close=504.0,    # Below required 505 * 1.005 = 507.525
            candle_open=502.0,
            candle_volume=160_000,  # 80% of 200k
            candle_time=make_ts(9, 50),  # 20 min gap from 9:30 spike
        )
        assert result_short_gap is None, "Short gap + no price confirm should reject"

    def test_condition6_extended_gap_overrides_no_price_confirm(self):
        """At vol_ratio >= 80%, if gap >= 30 min, allow even without price confirm above 0.5% buffer."""
        detector = SecondSpikeDetector()
        _record_prior(detector, spike_close=500.0, spike_high=505.0, spike_volume=200_000, inter_spike_lows=[498.0])

        # 60 min gap compensates for lack of price confirmation above 507.525
        result = _eval(
            detector,
            candle_close=504.0,    # Below required 505 * 1.005 = 507.525 — but gap compensates
            candle_open=502.0,
            candle_volume=160_000,  # 80% of 200k
            candle_time=make_ts(10, 30),  # 60 min gap from 9:30 spike
        )
        assert result is not None, "60-min extended gap should override no-price-confirm at 80%"

    def test_condition6_high_ratio_with_price_confirm(self):
        """At vol_ratio >= 80%, close >= prior spike high * 1.005 → valid even short gap."""
        detector = SecondSpikeDetector()
        _record_prior(detector, spike_close=500.0, spike_high=505.0, spike_volume=200_000, inter_spike_lows=[498.0])

        # Vol ratio 80% with close = 509 (above 505*1.005=507.525)
        result = _eval(
            detector,
            candle_close=509.0,    # Above prior spike high * 1.005
            candle_open=506.0,
            candle_volume=160_000,  # 80% of 200k
            candle_time=make_ts(10, 30),
        )
        assert result is not None

    def test_condition6_below_80_no_price_confirm_needed(self):
        """Below 80% ratio — no price above high required."""
        detector = SecondSpikeDetector()
        _record_prior(detector, spike_close=500.0, spike_high=505.0, spike_volume=200_000, inter_spike_lows=[498.0])

        # 60% ratio, close below prior high → still valid (no confirm needed)
        result = _eval(
            detector,
            candle_close=503.0,    # Below prior high but below 80% ratio
            candle_open=501.0,
            candle_volume=120_000,  # 60% of 200k
            candle_time=make_ts(10, 30),
        )
        assert result is not None


# ─────────────────────────────────────────────────────────────────────────────
# SL Anchor: inter_spike_low
# ─────────────────────────────────────────────────────────────────────────────

class TestSecondSpikeSL:
    def test_stop_loss_uses_inter_spike_low(self):
        """SL = inter_spike_low - 1 tick."""
        detector = SecondSpikeDetector()
        _record_prior(detector, inter_spike_lows=[499.5, 498.0, 497.0])  # Lowest was 497.0

        result = _eval(detector)
        assert result is not None
        assert result.stop_loss == 496.95  # 497.0 - 0.05 tick

    def test_stop_loss_with_larger_tick(self):
        """Tick size 0.10 → SL = inter_spike_low - 0.10."""
        detector = SecondSpikeDetector()
        # inter_spike_low tracks the MINIMUM of passed values.
        # spike_low defaults to 498.0 which is < 500, so min = 498.
        # Use spike_low=502 so the minimum of [502, 500, 501, 502] = 500.
        _record_prior(detector, spike_low=502.0, inter_spike_lows=[500.0, 501.0, 502.0])

        result = _eval(detector, tick_size=0.10)
        assert result.stop_loss == 499.9  # 500.0 - 0.10


# ─────────────────────────────────────────────────────────────────────────────
# Lifecycle: record / clear
# ─────────────────────────────────────────────────────────────────────────────

class TestSecondSpikeLifecycle:
    def test_has_record_returns_true_after_record(self):
        detector = SecondSpikeDetector()
        _record_prior(detector, symbol="RELIANCE")
        assert detector.has_record("RELIANCE")

    def test_has_record_returns_false_for_unknown_symbol(self):
        detector = SecondSpikeDetector()
        assert not detector.has_record("NOSUCH")

    def test_clear_removes_record(self):
        detector = SecondSpikeDetector()
        _record_prior(detector, symbol="RELIANCE")
        detector.clear("RELIANCE")
        assert not detector.has_record("RELIANCE")

    def test_end_of_day_reset_clears_all(self):
        detector = SecondSpikeDetector()
        _record_prior(detector, symbol="RELIANCE")
        _record_prior(detector, symbol="ITC")
        detector.end_of_day_reset()
        assert not detector.has_record("RELIANCE")
        assert not detector.has_record("ITC")

    def test_record_first_spike_overwrites_prior(self):
        """
        Third spike scenario: newer first spike overwrites the prior record.
        The vol_ratio in subsequent evaluations uses the MOST RECENT prior spike volume.
        """
        detector = SecondSpikeDetector()

        # First spike at 09:30 with volume=200k
        _record_prior(detector, symbol="TEST", spike_time=make_ts(9, 30), spike_volume=200_000, inter_spike_lows=[498.0])

        # Second (newest) spike at 11:00 with volume=300k — overwrites 200k record
        _record_prior(detector, symbol="TEST", spike_time=make_ts(11, 0), spike_volume=300_000, inter_spike_lows=[498.0])

        # Evaluate with 200k candle → ratio = 200k/300k = 67% (valid)
        result = _eval(detector, candle_time=make_ts(12, 0), candle_volume=200_000)
        assert result is not None
        # Should use the 300k (most recent) spike volume, not 200k
        assert result.prior_spike.spike_volume == 300_000
        assert result.vol_ratio == pytest.approx(0.667, rel=1e-2)


# ─────────────────────────────────────────────────────────────────────────────
# Happy path: all conditions pass
# ─────────────────────────────────────────────────────────────────────────────

class TestSecondSpikeHappyPath:
    def test_all_conditions_pass_returns_entry(self):
        """Complete happy path with all 7 conditions satisfied."""
        detector = SecondSpikeDetector()
        _record_prior(
            detector,
            symbol="RELIANCE",
            spike_time=make_ts(9, 30),
            spike_close=500.0,
            spike_high=505.0,
            spike_low=498.0,
            spike_volume=200_000,
            inter_spike_lows=[499.0, 498.5, 497.5],
        )

        result = _eval(
            detector,
            symbol="RELIANCE",
            candle_close=501.0,   # Green candle, above price floor
            candle_open=500.0,
            candle_low=499.5,
            candle_volume=140_000,  # 70% ratio
            candle_time=make_ts(10, 30),
            volume_sma=10_000.0,
            tick_size=0.05,
        )

        assert result is not None
        assert result.symbol == "RELIANCE"
        assert result.vol_ratio == pytest.approx(0.70, rel=1e-2)
        assert result.gap_minutes >= 15
        assert result.stop_loss == 497.45  # 497.5 - 0.05
        assert result.is_second_spike is True

    def test_boundary_50_pct_ratio_valid(self):
        """50% ratio is valid (best zone per spec)."""
        detector = SecondSpikeDetector()
        _record_prior(detector, spike_volume=200_000, inter_spike_lows=[498.0])

        result = _eval(detector, candle_volume=100_000, candle_time=make_ts(10, 30))
        assert result is not None

    def test_boundary_100_pct_ratio_valid(self):
        """
        100% ratio is valid (at the edge of marginal zone).
        At 100% vol_ratio, condition 6 requires close > prior spike's high,
        so we must provide candle_close above the default high of 505.0.
        """
        detector = SecondSpikeDetector()
        _record_prior(detector, spike_volume=200_000, spike_high=505.0, inter_spike_lows=[498.0])

        result = _eval(detector, candle_volume=200_000, candle_time=make_ts(10, 30), candle_close=506.0, candle_open=504.0)
        assert result is not None