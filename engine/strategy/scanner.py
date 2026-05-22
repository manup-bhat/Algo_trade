"""
engine/strategy/scanner.py — Phase 1: Impact Candle Detection.

Pure function — no side effects, no I/O, no async.
All six filters are applied in fail-fast order (cheapest checks first).
Returns ImpactCandle dataclass on hit, None on miss.

Filter order (spec Part 7.10):
  1. volume_sma is None → skip (warmup incomplete)
  2. volume_sma <= 0    → skip (data issue)
  3. spike < 20x SMA   → skip
  4. turnover < 8Cr    → skip
  5. price range       → skip
  6. close < open×0.995 → skip (sell dump)
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from engine.market.candle_builder import Candle, CandleBuilder

from app.core.config import settings

log = structlog.get_logger(__name__)

# Module-level cache for VIX and Nifty gate \u2014 updated by coordinator on each candle.
# Using a simple float avoids making evaluate() async (it's called from the hot path).
_cached_vix: float | None = None
_nifty_gate_open: bool = True   # True = allow new entries (default: open)


def update_market_gate(vix: float | None, gate_open: bool) -> None:
    """Called by coordinator whenever a Nifty/VIX candle closes."""
    global _cached_vix, _nifty_gate_open
    _cached_vix = vix
    _nifty_gate_open = gate_open


@dataclass(frozen=True, slots=True)
class ImpactCandle:
    """
    Data snapshot of a confirmed Phase 1 scan hit.
    All values are immutable after creation — treated as a value object.
    """
    symbol: str
    instrument_token: int
    time: datetime.datetime       # Candle timestamp (minute boundary, IST)
    open: float
    high: float
    low: float
    close: float
    volume: int
    turnover: float               # close × volume (₹)
    volume_sma_500: float         # The SMA at the moment of detection
    spike_multiple: float         # candle.volume / volume_sma_500

    def __str__(self) -> str:
        return (
            f"ImpactCandle({self.symbol} @ {self.time:%H:%M} "
            f"spike={self.spike_multiple:.1f}x vol={self.volume:,} "
            f"turnover=INR{self.turnover/1e7:.2f}Cr)"
        )


def evaluate(
    candle: "Candle",
    builder: "CandleBuilder",
    instrument_token: int = 0,
) -> ImpactCandle | None:
    """
    Evaluate a completed 1-minute candle against all scan filters.

    Args:
        candle:            The completed candle from CandleBuilder.
        builder:           The CandleBuilder for this symbol (for SMA access).
        instrument_token:  Kite instrument token for this symbol.

    Returns:
        ImpactCandle if all filters pass, None otherwise.

    This is a pure function — safe to call from any context.
    The coordinator is responsible for calling this only during market hours.
    """
    # ── Filter 0: Market direction gate (Nifty EMA) ───────────────────
    # Block all new scan hits if Nifty is below its 5-min EMA.
    # This prevents entries into a broad bearish session.
    # Gate defaults to OPEN if no EMA has been computed yet (cold start safety).
    if settings.NIFTY_GATE_ENABLED and not _nifty_gate_open:
        return None  # Market gate closed — skip entire symbol this candle

    # ── Filter 1: SMA warmup ──────────────────────────────────────────
    volume_sma = builder.volume_sma
    if volume_sma is None:
        return None  # Not enough history yet

    # ── Filter 2: SMA validity ─────────────────────────────────────────
    if volume_sma <= 0:
        log.warning("scanner_zero_sma", symbol=candle.symbol)
        return None

    # ── Filter 3: Volume spike multiple ───────────────────────────────
    spike_multiple = candle.volume / volume_sma
    if spike_multiple < settings.VOLUME_SPIKE_MULTIPLE:
        return None  # Most candles fail here — hot path exit

    # ── Filter 4: Minimum turnover (VIX-aware) ────────────────────────
    # During high-volatility sessions (VIX > threshold), raise the turnover
    # bar to filter out noise spikes that won't survive the dry-up phase.
    # Falls back to MIN_TURNOVER_CRORE if VIX data is unavailable.
    vix = _cached_vix
    if vix is not None and vix > settings.HIGH_VIX_THRESHOLD:
        effective_turnover_crore = settings.HIGH_VIX_TURNOVER_CRORE
    else:
        effective_turnover_crore = settings.MIN_TURNOVER_CRORE
    effective_turnover_rupees = effective_turnover_crore * 1e7

    if candle.turnover < effective_turnover_rupees:
        log.debug(
            "scanner_turnover_miss",
            symbol=candle.symbol,
            turnover_cr=candle.turnover / 1e7,
            required_cr=effective_turnover_crore,
            vix=vix,
            spike=f"{spike_multiple:.1f}x",
        )
        return None

    # ── Filter 5: Price range ─────────────────────────────────────────
    if candle.close < settings.MIN_PRICE or candle.close > settings.MAX_PRICE:
        log.debug(
            "scanner_price_range_miss",
            symbol=candle.symbol,
            close=candle.close,
            min_price=settings.MIN_PRICE,
            max_price=settings.MAX_PRICE,
        )
        return None

    # ── Filter 6: Not a sell dump (green or near-flat candle only) ────
    # close >= open × 0.995: allows flat (close==open) and green candles
    # Rejects strongly red candles (close < open × 0.995)
    threshold = candle.open * 0.995
    if candle.close < threshold:
        log.debug(
            "scanner_sell_dump_miss",
            symbol=candle.symbol,
            open=candle.open,
            close=candle.close,
            threshold=round(threshold, 2),
        )
        return None

    # ── ALL FILTERS PASSED ────────────────────────────────────────────
    impact = ImpactCandle(
        symbol=candle.symbol,
        instrument_token=instrument_token,
        time=candle.timestamp,
        open=candle.open,
        high=candle.high,
        low=candle.low,
        close=candle.close,
        volume=candle.volume,
        turnover=candle.turnover,
        volume_sma_500=volume_sma,
        spike_multiple=spike_multiple,
    )

    log.info(
        "scanner_hit",
        symbol=candle.symbol,
        candle_time=candle.timestamp.strftime("%H:%M"),
        close=candle.close,
        volume=candle.volume,
        spike_multiple=f"{spike_multiple:.1f}x",
        turnover_cr=round(candle.turnover / 1e7, 2),
        sma=round(volume_sma, 0),
    )
    return impact
