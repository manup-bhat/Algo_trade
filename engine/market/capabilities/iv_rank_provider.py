"""
engine/market/capabilities/iv_rank_provider.py — IV Rank capability.

Computes IV Rank (IVR) and IV Percentile (IVP) for an underlying, comparing
current implied volatility against its 52-week historical range.

Registry key: "iv_rank"

IVR = (current_IV - 52w_low_IV) / (52w_high_IV - 52w_low_IV)  × 100
IVP = percentile rank of current_IV within all daily IVs over the past 252 sessions.

Both are expressed as 0–100 scores. High IVR/IVP = options are expensive
(favours selling premium). Low IVR/IVP = options are cheap (favours buying).

Input (via ctx.extra):
    current_iv:   float — current ATM IV (from GreeksProvider output)
    lookback_days: int  — historical window (default 252 = 1 trading year)

Output shape:
    {
        "current_iv":     float,
        "iv_rank":        float,   # 0–100
        "iv_percentile":  float,   # 0–100
        "iv_52w_high":    float,
        "iv_52w_low":     float,
        "lookback_days":  int,
        "samples":        int,     # actual daily IV samples available
    }
    None if current_iv is not provided or historical data is unavailable.

Note: Building the 52-week IV history requires historical option prices, which
are not yet fetched by HistoricalDataService. Phase 2 uses a Redis-cached IV
series written by the engine as it observes daily closes. If the cache is empty
(cold start), IVR/IVP are returned as None and the strategy must handle gracefully.
"""

from __future__ import annotations

from typing import Any

import structlog

from engine.core.capability_registry import CapabilityProvider, MarketContext

log = structlog.get_logger(__name__)

_DEFAULT_LOOKBACK = 252
_REDIS_KEY_PREFIX = "iv_history:"  # iv_history:{underlying} → JSON list of daily IVs


class IVRankProvider:
    """
    IV Rank + IV Percentile for an underlying.

    Phase 2 implementation: reads historical IV from Redis cache (populated
    daily by the engine at market close). Falls back gracefully if cache is
    empty (cold-start, first trading day, or Redis miss).

    Phase 3 upgrade path: replace Redis cache with HistoricalDataService parquet
    cache of historical option prices → compute IV directly from close prices.
    """

    key = "iv_rank"

    async def compute(self, ctx: MarketContext) -> dict[str, Any] | None:
        current_iv = ctx.extra.get("current_iv")
        if current_iv is None:
            log.debug("iv_rank_no_current_iv", symbol=ctx.symbol)
            return None

        current_iv = float(current_iv)
        underlying = ctx.extra.get("underlying") or ctx.underlying or ctx.symbol
        lookback = int(ctx.extra.get("lookback_days", _DEFAULT_LOOKBACK))

        # Attempt to read IV history from Redis
        iv_history: list[float] = []
        if ctx.redis_store is not None:
            try:
                import json
                raw = await ctx.redis_store._r.get(f"{_REDIS_KEY_PREFIX}{underlying}")
                if raw:
                    iv_history = json.loads(raw)[-lookback:]  # most recent N
            except Exception as exc:
                log.warning(
                    "iv_rank_redis_read_failed",
                    underlying=underlying,
                    error=str(exc),
                )

        if not iv_history:
            log.debug(
                "iv_rank_no_history",
                underlying=underlying,
                hint="IV history not yet cached. Strategy should handle None IVR gracefully.",
            )
            return {
                "current_iv": current_iv,
                "iv_rank": None,
                "iv_percentile": None,
                "iv_52w_high": None,
                "iv_52w_low":  None,
                "lookback_days": lookback,
                "samples": 0,
            }

        iv_52w_high = max(iv_history)
        iv_52w_low  = min(iv_history)

        # IV Rank
        iv_range = iv_52w_high - iv_52w_low
        iv_rank = (
            (current_iv - iv_52w_low) / iv_range * 100
            if iv_range > 1e-6 else 50.0  # undefined range → neutral
        )
        iv_rank = max(0.0, min(100.0, iv_rank))

        # IV Percentile
        below = sum(1 for v in iv_history if v <= current_iv)
        iv_percentile = below / len(iv_history) * 100

        return {
            "current_iv":    round(current_iv, 6),
            "iv_rank":       round(iv_rank, 2),
            "iv_percentile": round(iv_percentile, 2),
            "iv_52w_high":   round(iv_52w_high, 6),
            "iv_52w_low":    round(iv_52w_low, 6),
            "lookback_days": lookback,
            "samples":       len(iv_history),
        }

    @staticmethod
    async def record_daily_iv(underlying: str, iv: float, redis_store: Any) -> None:
        """
        Append today's closing IV to the Redis history list.

        Called from job_session_end() in runner.py after market close.
        Keeps at most 504 entries (2 trading years) to cap memory.

        Args:
            underlying:  NSE/NFO underlying symbol (e.g. "NIFTY").
            iv:          Today's ATM closing IV (annualised, 0–1).
            redis_store: Active RedisStore instance.
        """
        import json
        key = f"{_REDIS_KEY_PREFIX}{underlying}"
        try:
            raw = await redis_store._r.get(key)
            history: list[float] = json.loads(raw) if raw else []
            history.append(round(iv, 6))
            history = history[-504:]  # cap at 2 years
            await redis_store._r.set(key, json.dumps(history), ex=365 * 24 * 3600)
            log.info("iv_history_updated", underlying=underlying, samples=len(history))
        except Exception as exc:
            log.error("iv_history_update_failed", underlying=underlying, error=str(exc))
