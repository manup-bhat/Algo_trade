"""
engine/market/candle_builder.py — Tick → 1-minute OHLCV candle builder.

PRODUCTION-CRITICAL: This module has four known bug-points, all fixed here.
Do NOT modify the reconnect logic or the minute-bucketing without re-running tests.

Design:
  - One CandleBuilder instance per subscribed symbol.
  - Receives raw ticks: (ltp, cumulative_day_volume, exchange_timestamp).
  - Uses exchange_timestamp (from Kite, IST) for minute bucketing — NOT wall clock.
  - Maintains a rolling deque of last 500 one-minute volumes for SMA calculation.
  - Reconnect-safe: reset_cumulative_baseline() must be called on every WS reconnect.

Bug fixes implemented:
  Bug 4 — Reconnect phantom volume spike:
    After WS reconnect, cumulative_volume resets to a value < what it was pre-disconnect.
    Without a baseline reset, the delta = (new_cumulative - old_cumulative) would be a
    huge negative number → max(0, ...) clamps it to 0, BUT if the exchange also replays
    the pre-open volume, the cumulative can jump. Solution: _awaiting_baseline_reset=True
    causes the first tick after reconnect to be used ONLY to set the baseline, skipping
    candle update entirely. This guarantees no phantom volume credit.
"""

from __future__ import annotations

import datetime
import statistics
from collections import deque
from dataclasses import dataclass, field

import pytz
import structlog

log = structlog.get_logger(__name__)

IST_TZ = pytz.timezone("Asia/Kolkata")


@dataclass(slots=True)
class Candle:
    """A completed 1-minute OHLCV candle."""

    symbol: str
    timestamp: datetime.datetime  # Minute boundary in IST (second=0, microsecond=0)
    open: float
    high: float
    low: float
    close: float
    volume: int
    turnover: float  # close × volume (₹)

    def __repr__(self) -> str:
        return (
            f"Candle({self.symbol} {self.timestamp:%H:%M} "
            f"O={self.open:.2f} H={self.high:.2f} L={self.low:.2f} C={self.close:.2f} "
            f"V={self.volume:,} T=INR{self.turnover/1e7:.2f}Cr)"
        )


class CandleBuilder:
    """
    Per-symbol tick accumulator that emits completed 1-minute OHLCV candles.

    Thread safety: This class is NOT thread-safe. All calls must arrive on the
    asyncio event loop. KiteTicker dispatches via run_coroutine_threadsafe, so
    by the time on_tick() is called it is already on the event loop.

    Usage:
        builder = CandleBuilder("RELIANCE")
        candle = builder.on_tick(ltp=2500.0, cum_vol=150000, exchange_ts=<datetime>)
        if candle:
            # Candle for the completed minute is ready
            await scanner.evaluate(candle, builder)
    """

    def __init__(self, symbol: str, sma_period: int = 500) -> None:
        self.symbol = symbol
        self._sma_period = sma_period

        # ── Candle state ──────────────────────────────────────────────
        self._current_candle_time: datetime.datetime | None = None
        self._open: float = 0.0
        self._high: float = 0.0
        self._low: float = float("inf")
        self._close: float = 0.0
        self._prev_cumulative_volume: int = 0
        self._candle_volume: int = 0

        # ── SMA history ───────────────────────────────────────────────
        # deque with maxlen enforces the rolling window automatically
        self._volume_history: deque[int] = deque(maxlen=sma_period)

        # ── Reconnect guard (Bug 4 fix) ───────────────────────────────
        # Set True on WS reconnect. Next tick is used only to set the
        # cumulative baseline — no candle update, no volume delta.
        self._awaiting_baseline_reset: bool = True  # Also True on first tick of day

        self._tick_count: int = 0  # Diagnostics only

    # ── Public: Primary tick handler ──────────────────────────────────────

    def on_tick(
        self,
        ltp: float,
        cum_vol: int,
        exchange_ts: datetime.datetime,
    ) -> Candle | None:
        """
        Process a single tick. Returns a completed Candle if the minute boundary
        has passed, otherwise returns None.

        Args:
            ltp:         Last traded price in ₹ (NSE equities: already in rupees)
            cum_vol:     Cumulative day volume from Kite tick (monotonically increasing)
            exchange_ts: Exchange timestamp from tick data (IST, timezone-aware)

        Returns:
            Candle if a new minute started (i.e. the previous minute is now complete).
            None if we're still accumulating ticks within the current minute.
        """
        self._tick_count += 1

        # ── Ensure IST timezone ───────────────────────────────────────
        if exchange_ts.tzinfo is None:
            exchange_ts = IST_TZ.localize(exchange_ts)

        # ── Minute bucket: floor to minute boundary ───────────────────
        candle_minute = exchange_ts.replace(second=0, microsecond=0)

        # ── Bug 4 fix: Reconnect baseline reset ───────────────────────
        # On the first tick after startup or reconnect, we cannot compute a
        # meaningful delta because we don't know the previous cumulative.
        # Use this tick to establish the baseline and return immediately.
        if self._awaiting_baseline_reset:
            self._prev_cumulative_volume = cum_vol
            self._current_candle_time = candle_minute
            self._open = ltp
            self._high = ltp
            self._low = ltp
            self._close = ltp
            self._candle_volume = 0  # No volume credit on first tick
            self._awaiting_baseline_reset = False
            log.debug(
                "candle_builder_baseline_set",
                symbol=self.symbol,
                cum_vol=cum_vol,
                candle_minute=candle_minute.isoformat(),
            )
            return None

        # ── New minute started? ───────────────────────────────────────
        if self._current_candle_time is not None and candle_minute > self._current_candle_time:
            # Finalize and emit the completed candle
            completed = self._build_candle()

            # Append this minute's volume to SMA history
            self._volume_history.append(self._candle_volume)

            # Start the new minute
            self._reset_for_new_minute(ltp, cum_vol, candle_minute)

            log.debug(
                "candle_complete",
                symbol=self.symbol,
                candle=str(completed),
                sma_size=len(self._volume_history),
                warmed_up=self.is_warmed_up,
            )
            return completed

        # ── Same minute: accumulate tick ──────────────────────────────
        tick_volume = max(0, cum_vol - self._prev_cumulative_volume)
        self._update_current_candle(ltp, tick_volume, cum_vol)
        return None

    # ── Public: Control methods ───────────────────────────────────────────

    def reset_cumulative_baseline(self) -> None:
        """
        Called by coordinator on every WebSocket reconnect (Bug 4 fix).
        The next tick will be used only to reset the cumulative baseline —
        no volume delta will be credited to any candle.
        """
        self._awaiting_baseline_reset = True
        log.debug("candle_builder_awaiting_baseline_reset", symbol=self.symbol)

    def reset(self) -> None:
        """
        Full reset for a new trading session (called at 09:15 AM market open).
        Clears candle state but PRESERVES volume history for SMA continuity.
        """
        self._current_candle_time = None
        self._open = 0.0
        self._high = 0.0
        self._low = float("inf")
        self._close = 0.0
        self._prev_cumulative_volume = 0
        self._candle_volume = 0
        self._tick_count = 0
        self._awaiting_baseline_reset = True  # Re-establish baseline on next tick
        log.debug("candle_builder_reset", symbol=self.symbol)

    def load_history(self, volumes: list[int]) -> None:
        """
        Load persisted SMA history from Redis (loaded at 09:00 AM pre-market setup).
        Only the last _sma_period values are kept (deque enforces maxlen).

        Args:
            volumes: List of previous 1-minute volumes (oldest first)
        """
        self._volume_history.clear()
        # Take only the last sma_period values to respect the deque maxlen
        for v in volumes[-self._sma_period:]:
            self._volume_history.append(v)
        log.info(
            "candle_builder_history_loaded",
            symbol=self.symbol,
            loaded=len(self._volume_history),
            warmed_up=self.is_warmed_up,
        )

    # ── Properties ────────────────────────────────────────────────────────

    @property
    def volume_sma(self) -> float | None:
        """
        500-period SMA of 1-minute volume.
        Returns None until exactly 500 candles have been accumulated.
        This guards against false signals during the SMA warmup period.
        """
        if len(self._volume_history) < self._sma_period:
            return None
        return statistics.mean(self._volume_history)

    @property
    def is_warmed_up(self) -> bool:
        """True when the SMA has sufficient history to produce valid signals."""
        return len(self._volume_history) >= self._sma_period

    @property
    def history_size(self) -> int:
        """Number of completed candles in SMA history."""
        return len(self._volume_history)

    @property
    def current_volume(self) -> int:
        """Volume accumulated in the currently forming one-minute candle."""
        return self._candle_volume

    @property
    def volume_history_snapshot(self) -> list[int]:
        """
        Snapshot of the current volume history for Redis persistence.
        Called at session end (15:25 PM) by the APScheduler job.
        """
        return list(self._volume_history)

    # ── Private helpers ───────────────────────────────────────────────────

    def _build_candle(self) -> Candle:
        """Construct and return the Candle for the current (just-ended) minute."""
        assert self._current_candle_time is not None, "Cannot build candle before first tick"
        return Candle(
            symbol=self.symbol,
            timestamp=self._current_candle_time,
            open=self._open,
            high=self._high,
            low=self._low,
            close=self._close,
            volume=self._candle_volume,
            turnover=round(self._close * self._candle_volume, 2),
        )

    def _reset_for_new_minute(
        self, ltp: float, cum_vol: int, candle_minute: datetime.datetime
    ) -> None:
        """
        Set up state for the new (just-started) minute.
        The first tick of a new minute becomes the open of that minute.
        Its volume contribution: current cumulative - previous cumulative.
        """
        tick_volume = max(0, cum_vol - self._prev_cumulative_volume)
        self._current_candle_time = candle_minute
        self._open = ltp
        self._high = ltp
        self._low = ltp
        self._close = ltp
        self._candle_volume = tick_volume
        self._prev_cumulative_volume = cum_vol

    def _update_current_candle(self, ltp: float, tick_volume: int, cum_vol: int) -> None:
        """Update OHLCV for a tick within the current minute."""
        if ltp > self._high:
            self._high = ltp
        if ltp < self._low:
            self._low = ltp
        self._close = ltp
        self._candle_volume += tick_volume
        self._prev_cumulative_volume = cum_vol

    def __repr__(self) -> str:
        return (
            f"CandleBuilder({self.symbol} "
            f"history={self.history_size}/{self._sma_period} "
            f"warmed={self.is_warmed_up})"
        )
