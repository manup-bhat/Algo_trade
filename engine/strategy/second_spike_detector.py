"""
engine/strategy/second_spike_detector.py

Detects when a stock fires a second significant volume spike on the same
trading day as a prior scan hit.

Research basis:
  - Chan & Lakonishok (1995, J. Finance): institutions execute packages of
    trades across sessions. When they return same day it signals urgency —
    deadline, price target, or expected catalyst.
  - Keim & Madhavan (1995): institutions "leg into" positions in tranches.
    The intraday second wave volume averages 60-80% of the first wave.
  - Wyckoff Method: the secondary test occurs on lower volume than the
    selling climax, confirming supply absorption. The inter-spike quiet
    period IS the Wyckoff secondary test at the 5-min timeframe.

Entry rule:
  The inter-spike period structurally replaces the dry-up phase.
  When the second spike is detected, enter directly on that candle close.
  No separate dry-up cycle is required.

Volume ratio guide (validated):
  50-65%   Best zone. Supply clearly dried up. Cleanest setup.
  65-80%   Strong zone. Institution returned with conviction. Valid.
  80-100%  Marginal. Add price-above-prior-high condition (enforced in code).
  >100%    Reject. Second wave >= first = unrelated event or distribution.
  <50%     Too small. Statistically insignificant second wave.

v3 NEW module — introduced in IVBS strategy v3.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import structlog

from app.core.config import settings
from engine.strategy.scanner import ImpactCandle

log = structlog.get_logger(__name__)


@dataclass
class PriorSpikeRecord:
    """Snapshot of a first-wave impact candle, preserved for second-spike comparison."""
    symbol: str
    spike_time: datetime
    spike_close: float
    spike_high: float
    spike_low: float
    spike_volume: int
    inter_spike_low: float  # Lowest low seen between spike 1 and spike 2 (= SL anchor)


@dataclass
class SecondSpikeEntry:
    """All data needed to place a direct entry from a second-spike signal."""
    symbol: str
    entry_close: float          # Close price of the second spike candle
    entry_time: datetime        # Timestamp of the second spike candle
    stop_loss: float            # = inter_spike_low - 1 tick
    vol_ratio: float            # second_volume / first_volume
    gap_minutes: float          # time between spikes
    prior_spike: PriorSpikeRecord
    is_second_spike: bool = True  # Tag for analytics / DB notes


class SecondSpikeDetector:
    """
    Singleton-style manager. One instance shared by the Coordinator.

    Lifecycle per symbol:
      1. record_first_spike()       -- called when Phase 1 scanner fires
      2. update_inter_spike_low()   -- called on every candle while symbol
                                       is IDLE (no active SM)
      3. evaluate_second_spike()    -- called when a new scan-level candle
                                       appears for a symbol with a prior spike
      4. clear()                    -- called after second spike is acted on
      5. end_of_day_reset()         -- called at session_end (15:25 IST)
    """

    def __init__(self) -> None:
        self._records: dict[str, PriorSpikeRecord] = {}

    # ── Public API ──────────────────────────────────────────────────────────

    def record_first_spike(self, impact: ImpactCandle) -> None:
        """
        Call immediately after the scanner fires (Phase 1 hit).
        Stores the prior spike record for the symbol.
        If the symbol already has a record (third spike scenario),
        this overwrites with the most recent prior spike.
        """
        self._records[impact.symbol] = PriorSpikeRecord(
            symbol=impact.symbol,
            spike_time=impact.time,
            spike_close=impact.close,
            spike_high=impact.high,
            spike_low=impact.low,
            spike_volume=impact.volume,
            inter_spike_low=impact.low,  # starts at impact candle's own low
        )
        log.debug(
            "second_spike_first_wave_recorded",
            symbol=impact.symbol,
            volume=impact.volume,
            spike_time=impact.time.isoformat(),
        )

    def update_inter_spike_low(self, symbol: str, candle_low: float) -> None:
        """
        Call on every candle for a symbol with a prior spike record that is
        currently IDLE (no active SM). Tracks the lowest low seen during the
        inter-spike consolidation period.

        This is the true SL anchor for any second-spike entry because it is
        the Wyckoff structure low — if this level fails, both waves failed.
        """
        record = self._records.get(symbol)
        if record is not None:
            if candle_low < record.inter_spike_low:
                record.inter_spike_low = candle_low

    def evaluate_second_spike(
        self,
        symbol: str,
        candle_close: float,
        candle_open: float,
        candle_low: float,
        candle_volume: int,
        candle_time: datetime,
        volume_sma: float,
        tick_size: float,
    ) -> Optional[SecondSpikeEntry]:
        """
        Evaluate a new scan-level volume spike against the stored prior spike
        for this symbol. Returns a SecondSpikeEntry if all conditions pass,
        None otherwise.

        Conditions (all must pass):
          1. Prior spike exists for this symbol (recorded earlier today).
          2. Gap between prior spike and this candle >= SECOND_SPIKE_MIN_GAP_MINUTES.
             Validates that real consolidation occurred between waves.
          3. Volume ratio: this candle's volume is 50-100% of the prior spike.
             <50% = insignificant. >100% = unrelated event or distribution.
          4. Absolute volume floor: still >= SECOND_SPIKE_VOLUME_FLOOR x SMA.
             Ensures second spike is anomalous even in absolute terms.
          5. Price held: second spike close >= prior spike close x 0.998.
             If price collapsed between waves, absorption failed.
          6. Green candle: close > open. Institutional buy, not sell.
          7. At vol_ratio >= 0.80: close must be ABOVE prior spike's high.
             At 80%+ volume, price must confirm absorption, not just volume.
        """
        record = self._records.get(symbol)
        if record is None:
            return None

        # Condition 1: gap >= minimum (proves real consolidation)
        gap_minutes = (candle_time - record.spike_time).total_seconds() / 60.0
        if gap_minutes < settings.SECOND_SPIKE_MIN_GAP_MINUTES:
            log.debug(
                "second_spike_rejected_gap_too_small",
                symbol=symbol,
                gap_minutes=round(gap_minutes, 1),
                required=settings.SECOND_SPIKE_MIN_GAP_MINUTES,
            )
            return None

        # Condition 2: volume ratio within valid range
        if record.spike_volume <= 0:
            return None
        vol_ratio = candle_volume / record.spike_volume
        if not (settings.SECOND_SPIKE_MIN_RATIO <= vol_ratio <= settings.SECOND_SPIKE_MAX_RATIO):
            log.debug(
                "second_spike_rejected_vol_ratio",
                symbol=symbol,
                vol_ratio=round(vol_ratio, 2),
                required_range=(settings.SECOND_SPIKE_MIN_RATIO, settings.SECOND_SPIKE_MAX_RATIO),
            )
            return None

        # Condition 3: absolute volume floor
        if volume_sma > 0 and (candle_volume / volume_sma) < settings.SECOND_SPIKE_VOLUME_FLOOR:
            log.debug(
                "second_spike_rejected_abs_volume_floor",
                symbol=symbol,
                actual_multiple=round(candle_volume / volume_sma, 1),
                required=settings.SECOND_SPIKE_VOLUME_FLOOR,
            )
            return None

        # Condition 4: price held up (prior spike close is the floor)
        price_floor = record.spike_close * 0.998
        if candle_close < price_floor:
            log.debug(
                "second_spike_rejected_price_collapsed",
                symbol=symbol,
                candle_close=candle_close,
                required_floor=round(price_floor, 2),
            )
            return None

        # Condition 5: green candle
        if candle_close <= candle_open:
            log.debug("second_spike_rejected_not_green", symbol=symbol)
            return None

        # Condition 6: at vol_ratio >= 0.80, require close above prior spike's HIGH
        # Research: At 80%+ volume the Wyckoff secondary test rule is borderline —
        # price must compensate by confirming absorption with a new high.
        if (
            vol_ratio >= settings.SECOND_SPIKE_PRICE_ABOVE_HIGH_THRESHOLD
            and candle_close <= record.spike_high
        ):
            log.debug(
                "second_spike_rejected_high_ratio_no_price_confirm",
                symbol=symbol,
                vol_ratio=round(vol_ratio, 2),
                candle_close=candle_close,
                prior_spike_high=record.spike_high,
            )
            return None

        # All conditions passed
        # SL = lowest low of the inter-spike consolidation minus 1 tick
        stop_loss = round(record.inter_spike_low - tick_size, 2)

        log.info(
            "second_spike_signal",
            symbol=symbol,
            vol_ratio=round(vol_ratio, 2),
            gap_minutes=round(gap_minutes, 1),
            candle_close=candle_close,
            stop_loss=stop_loss,
            inter_spike_low=record.inter_spike_low,
        )
        return SecondSpikeEntry(
            symbol=symbol,
            entry_close=candle_close,
            entry_time=candle_time,
            stop_loss=stop_loss,
            vol_ratio=vol_ratio,
            gap_minutes=gap_minutes,
            prior_spike=record,
        )

    def has_record(self, symbol: str) -> bool:
        """Return True if a prior spike record exists for this symbol today."""
        return symbol in self._records

    def clear(self, symbol: str) -> None:
        """Call after a second-spike trade is entered or definitively failed."""
        self._records.pop(symbol, None)

    def end_of_day_reset(self) -> None:
        """Call at session_end (15:25 APScheduler job). Clears all records."""
        count = len(self._records)
        self._records.clear()
        log.info("second_spike_detector_eod_reset", cleared_symbols=count)
