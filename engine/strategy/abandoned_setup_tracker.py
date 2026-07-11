"""
engine/strategy/abandoned_setup_tracker.py — Re-entry after abandonment.

When a setup is abandoned (timeout, a-shape, exit pressure), the stock often
gives a SECOND chance entry later in the same day when the initial supply has
been fully absorbed. This tracker monitors these symbols for a valid re-entry.

Strategy basis (Wyckoff Method):
  - "Secondary Test" (ST): after an impulse, institutions re-test the level
    with lower volume to confirm absorption before the second leg up.
  - "Last Point of Support" (LPS): a quiet, low-volume pullback to the
    breakout level, followed by renewed buying interest = high probability entry.
  - "Failed-to-fail": a setup that was abandoned due to excessive volume
    (false distribution signal) often re-establishes itself once that wave
    of selling is absorbed.

Re-entry conditions (all must be met):
  1. Price is above the original impact candle's LOW (structure not broken)
  2. At least RE_ENTRY_MIN_GAP_MINUTES have passed since abandonment
  3. Volume >= RE_ENTRY_VOLUME_MULTIPLE × SMA (much lower bar than 20x scanner)
  4. Close is above the original impact candle's CLOSE (above the key level)
  5. Candle is green (c > o)
  6. Before MAX_ENTRY_TIME cutoff
  7. Re-entry count < RE_ENTRY_MAX_PER_SYMBOL (prevent churning)

NOT allowed for:
  - price_broke_impact_low (price structure broken — don't re-enter)
  - Symbols that have already re-entered RE_ENTRY_MAX_PER_SYMBOL times today
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field

import pytz
import structlog

from app.core.config import settings

log = structlog.get_logger(__name__)
IST_TZ = pytz.timezone("Asia/Kolkata")

# Abandonment reasons that allow re-entry attempts
REENTRY_ALLOWED_REASONS = frozenset({
    "timeout",
    "a_shape_reversal",
    "institutional_exit_pressure",
    # NOT included: "price_broke_impact_low", "no_capital_available",
    # "insufficient_capital_for_quantity", "risk_per_share_too_small:...",
    # "pre_trade_failed:..." — these indicate structural or risk failures
})


@dataclass
class AbandonedRecord:
    """Record of an abandoned setup, used to evaluate re-entry eligibility."""
    symbol: str
    abandon_time: datetime.datetime        # Wall clock time of abandonment (IST)
    impact_candle_close: float             # The original spike candle's close
    impact_candle_low: float               # The original spike candle's low (price floor)
    impact_candle_high: float              # The original spike candle's high
    impact_candle_volume: int              # Original spike volume (for relative checks)
    abandonment_reason: str               # Why it was abandoned
    inter_session_low: float              # Lowest price seen AFTER abandonment (tracks shakeout)
    reentry_count: int = 0                # How many times we've attempted re-entry
    reentry_times: list[datetime.datetime] = field(default_factory=list)


class AbandonedSetupTracker:
    """
    Tracks abandoned setups and evaluates re-entry conditions on each new candle.

    Usage:
        # On SM abandon:
        tracker.record(symbol, abandon_time, impact_candle, reason)

        # In coordinator._on_candle_complete() IDLE path (after existing SM cleanup):
        re_entry = tracker.evaluate(symbol, candle, volume_sma)
        if re_entry:
            # Trigger re-entry via same path as second_spike entry

        # Update tracking low on every IDLE candle:
        tracker.update_low(symbol, candle.low)

        # At session end / on explicit clear:
        tracker.clear(symbol)
        tracker.clear_all()  # called at market close
    """

    def __init__(self) -> None:
        self._records: dict[str, AbandonedRecord] = {}

    def has_record(self, symbol: str) -> bool:
        """True if this symbol has an active abandoned setup record."""
        return symbol in self._records

    def record(
        self,
        symbol: str,
        abandon_time: datetime.datetime,
        impact_close: float,
        impact_low: float,
        impact_high: float,
        impact_volume: int,
        reason: str,
    ) -> None:
        """
        Record an abandoned setup for potential re-entry evaluation.

        Only records if the abandonment reason is in REENTRY_ALLOWED_REASONS.
        If a record already exists for this symbol, it is overwritten by the
        newest abandonment (keeps the most recent state as the reference).
        """
        if not settings.RE_ENTRY_ENABLED:
            return

        # Skip non-recoverable abandonment reasons
        if reason not in REENTRY_ALLOWED_REASONS:
            log.debug(
                "re_entry_skipped_non_recoverable_reason",
                symbol=symbol,
                reason=reason,
            )
            return

        # Check daily re-entry limit
        existing = self._records.get(symbol)
        if existing and existing.reentry_count >= settings.RE_ENTRY_MAX_PER_SYMBOL:
            log.debug(
                "re_entry_skipped_daily_limit",
                symbol=symbol,
                reentry_count=existing.reentry_count,
                max=settings.RE_ENTRY_MAX_PER_SYMBOL,
            )
            return

        reentry_count = existing.reentry_count if existing else 0
        reentry_times = existing.reentry_times if existing else []

        self._records[symbol] = AbandonedRecord(
            symbol=symbol,
            abandon_time=abandon_time,
            impact_candle_close=impact_close,
            impact_candle_low=impact_low,
            impact_candle_high=impact_high,
            impact_candle_volume=impact_volume,
            abandonment_reason=reason,
            inter_session_low=impact_low,  # Start tracking from impact low
            reentry_count=reentry_count,
            reentry_times=reentry_times,
        )
        log.info(
            "abandoned_setup_tracked",
            symbol=symbol,
            reason=reason,
            impact_close=impact_close,
            impact_low=impact_low,
            reentry_count=reentry_count,
        )

    def update_low(self, symbol: str, candle_low: float) -> None:
        """
        Track the lowest price seen since abandonment. Called for every IDLE
        candle after abandonment. Used to detect shakeout patterns (price
        dips below impact low then recovers — classic Wyckoff spring).
        """
        rec = self._records.get(symbol)
        if rec is not None:
            rec.inter_session_low = min(rec.inter_session_low, candle_low)

    def evaluate(
        self,
        symbol: str,
        candle_open: float,
        candle_high: float,  # noqa: ARG002 — available for future use
        candle_low: float,
        candle_close: float,
        candle_volume: int,
        candle_time: datetime.datetime,
        volume_sma: float | None,
    ) -> bool:
        """
        Evaluate whether this IDLE candle qualifies as a re-entry after abandonment.

        Returns True if ALL re-entry conditions are met. The caller is responsible
        for creating the SM and triggering the entry.
        """
        rec = self._records.get(symbol)
        if rec is None:
            return False

        if not settings.RE_ENTRY_ENABLED:
            return False

        if volume_sma is None or volume_sma <= 0:
            return False

        # Condition 1: Minimum gap since abandonment
        elapsed = (candle_time - rec.abandon_time).total_seconds() / 60
        if elapsed < settings.RE_ENTRY_MIN_GAP_MINUTES:
            return False

        # Condition 2: Price is still above the original impact candle's LOW
        # (If price broke below the impact low, the structure is broken — no re-entry)
        if candle_low < rec.impact_candle_low:
            log.info(
                "re_entry_rejected_price_below_impact_low",
                symbol=symbol,
                candle_low=candle_low,
                impact_low=rec.impact_candle_low,
            )
            self.clear(symbol)  # Structure broken — remove tracking
            return False

        # Condition 3: Volume must meet the re-entry threshold (lower than 20x scan)
        re_entry_vol_threshold = volume_sma * settings.RE_ENTRY_VOLUME_MULTIPLE
        if candle_volume < re_entry_vol_threshold:
            return False

        # Condition 4: Close must be above the original impact candle's CLOSE
        # (must reclaim the institutional accumulation level)
        if candle_close <= rec.impact_candle_close:
            return False

        # Condition 5: Must be a green (bullish) candle — demand confirming
        if candle_close <= candle_open:
            return False

        # Condition 6: Before entry cutoff
        if candle_time.time() >= settings.max_entry_time:
            return False

        # Condition 7: Daily re-entry limit
        if rec.reentry_count >= settings.RE_ENTRY_MAX_PER_SYMBOL:
            return False

        # ALL CONDITIONS MET — log the re-entry signal
        log.info(
            "re_entry_conditions_met",
            symbol=symbol,
            candle_time=candle_time.strftime("%H:%M"),
            elapsed_min=round(elapsed, 1),
            candle_volume=candle_volume,
            re_entry_threshold=round(re_entry_vol_threshold, 0),
            vol_ratio=round(candle_volume / volume_sma, 1),
            candle_close=candle_close,
            impact_close=rec.impact_candle_close,
            original_reason=rec.abandonment_reason,
            reentry_count=rec.reentry_count + 1,
        )

        # Increment re-entry counter and record time
        rec.reentry_count += 1
        rec.reentry_times.append(candle_time)

        # Log snapshot for this re-entry trigger
        import asyncio
        from engine.store.db_writer import DbWriter
        asyncio.create_task(
            DbWriter().write_signal_snapshot(
                signal_id=None,
                symbol=symbol,
                event_type="RE_ENTRY_TRIGGER",
                context_data={
                    "open": candle_open, "high": candle_high, "low": candle_low, "close": candle_close, "volume": candle_volume,
                    "time": candle_time.isoformat(),
                    "vol_ratio": round(candle_volume / volume_sma, 1),
                    "original_reason": rec.abandonment_reason,
                }
            )
        )

        return True

    def get_impact_data(self, symbol: str) -> AbandonedRecord | None:
        """Get the original impact candle data for SL placement on re-entry."""
        return self._records.get(symbol)

    def clear(self, symbol: str) -> None:
        """Remove a symbol's abandoned record (called when structure breaks or re-entered)."""
        self._records.pop(symbol, None)

    def clear_all(self) -> None:
        """Clear all records — called at session end."""
        count = len(self._records)
        self._records.clear()
        if count > 0:
            log.info("abandoned_tracker_cleared", symbol_count=count)

    def active_count(self) -> int:
        """Number of symbols currently being tracked for re-entry."""
        return len(self._records)


# Module-level singleton
abandoned_setup_tracker = AbandonedSetupTracker()
