"""
engine/market/capabilities/volume_sma_provider.py — Volume SMA capability.

Wraps the per-symbol CandleBuilder's volume history to produce a volume SMA
(Simple Moving Average) on demand. The CandleBuilder is passed via MarketContext
so this provider is completely stateless.

Registry key: "volume_sma"

Output shape:
    {
        "sma": float,        # Current volume SMA value
        "current": float,    # Current bar's volume (last closed candle)
        "ratio": float,      # current / sma  (>2.0 = spike)
        "period": int,       # SMA period used
        "bars_available": int,
    }
    None if CandleBuilder is not available or has insufficient history.
"""

from __future__ import annotations

from typing import Any

import structlog

from engine.core.capability_registry import CapabilityProvider, MarketContext

log = structlog.get_logger(__name__)

_DEFAULT_PERIOD = 20


class VolumeSmaProvider:
    """
    Reads volume SMA from the CandleBuilder already maintained by CandleAggregator.

    No new computation — the SMA is already kept live in CandleBuilder.volume_sma.
    This provider simply wraps it in the capability contract so strategies can
    declare `capabilities: [volume_sma]` instead of holding a direct CandleBuilder ref.
    """

    key = "volume_sma"

    async def compute(self, ctx: MarketContext) -> dict[str, Any] | None:
        """
        Returns current volume SMA info for ctx.symbol.

        Edge cases:
            - ctx.candle_builder is None → return None (not warmed up yet).
            - Builder has < period bars → sma=0, ratio=0.
            - Last bar volume is 0 → ratio=0 (no division error).
        """
        cb = ctx.candle_builder
        if cb is None:
            log.debug("volume_sma_no_builder", symbol=ctx.symbol)
            return None

        try:
            sma = cb.volume_sma or 0.0
            period = getattr(cb, "sma_period", _DEFAULT_PERIOD)
            bars = len(getattr(cb, "_volume_history", []))

            # Most recent completed candle volume
            current_vol = 0.0
            completed = getattr(cb, "_completed_candles", [])
            if completed:
                current_vol = float(completed[-1].volume if hasattr(completed[-1], "volume") else 0)
            else:
                # Fallback: check the running bar
                running = getattr(cb, "_running_candle", None)
                if running is not None:
                    current_vol = float(getattr(running, "volume", 0))

            ratio = (current_vol / sma) if sma > 0 else 0.0

            return {
                "sma": sma,
                "current": current_vol,
                "ratio": round(ratio, 4),
                "period": period,
                "bars_available": bars,
            }
        except Exception as exc:
            log.error(
                "volume_sma_compute_failed",
                symbol=ctx.symbol,
                error=str(exc),
            )
            return None
