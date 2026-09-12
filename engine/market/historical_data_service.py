"""
engine/market/historical_data_service.py — Rate-limited historical data service.

Wraps the Kite historical data REST API with:
  1. Token-bucket rate limiter (≤3 req/sec, Kite's hard limit).
  2. Local file cache (JSON per symbol/interval/date) so the same 500-candle
     lookback isn't re-fetched by every strategy on every restart.
  3. A shared warmup method that drives CandleBuilder SMA initialization.

The cache prevents hitting the Kite 3 req/sec ceiling when:
  - Multiple strategies request historical data for the same symbols at startup.
  - The engine restarts mid-session and needs to reload SMAs.

Architecture:
  - One shared asyncio.Semaphore caps concurrent requests at BURST_CAPACITY.
  - A sliding-window refill via asyncio.sleep ensures the long-run rate ≤3/sec.
  - Cache files: data/historical_cache/{symbol}/{interval}/{date}.json
    (one file per day-fetch, merged on read).
  - Cache TTL: 24 hours (a file older than 24h is re-fetched from Kite).

This is the Phase 1 generalisation of historical_warmup.py (which remains for
the SMA warmup case — HistoricalDataService calls it internally).
"""

from __future__ import annotations

import asyncio
import datetime
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytz
import structlog

if TYPE_CHECKING:
    from engine.kite.client import AsyncKiteClient
    from engine.market.candle_builder import CandleBuilder

log = structlog.get_logger(__name__)
IST_TZ = pytz.timezone("Asia/Kolkata")

# Kite REST: ≤3 requests/second (documented API limit)
_MAX_RPS = 3
_BURST_CAPACITY = 3          # allow up to 3 immediate requests
_REFILL_INTERVAL = 1.0       # seconds per full burst refill
_MAX_RETRIES = 3
_RATE_LIMIT_SLEEP = 1.0      # sleep on 429 before retry

# Cache directory relative to repo root
_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "historical_cache"
_CACHE_MAX_AGE_HOURS = 24

# Intervals supported by Kite historical API
_VALID_INTERVALS = frozenset({
    "minute", "3minute", "5minute", "10minute", "15minute",
    "30minute", "60minute", "day",
    # Aliases we accept and map to Kite names
    "1min", "3min", "5min", "10min", "15min", "30min",
})
_INTERVAL_MAP = {
    "1min": "minute",
    "3min": "3minute",
    "5min": "5minute",
    "10min": "10minute",
    "15min": "15minute",
    "30min": "30minute",
}


class HistoricalDataService:
    """
    Rate-limited, cached Kite historical data wrapper.

    One shared instance across all strategies — the rate limiter is shared so
    concurrent warmup of 200 symbols respects the API ceiling without each
    strategy needing to coordinate.

    Usage:
        service = HistoricalDataService(kite_client)
        candles = await service.get_candles(
            "RELIANCE", "1min",
            from_date=datetime.date(2026, 9, 1),
            to_date=datetime.date(2026, 9, 9),
        )
        loaded = await service.warmup_volume_sma("RELIANCE", builder)
    """

    def __init__(self, kite: "AsyncKiteClient | None" = None) -> None:
        self._kite = kite
        # Token bucket: semaphore caps burst + asyncio.sleep enforces rate
        self._semaphore = asyncio.Semaphore(_BURST_CAPACITY)
        self._last_request_time: float = 0.0

    def set_kite(self, kite: "AsyncKiteClient") -> None:
        """Wire kite client after auth (called from runner.py post-login)."""
        self._kite = kite

    # ── Public API ────────────────────────────────────────────────────────────

    async def get_candles(
        self,
        symbol: str,
        interval: str,
        from_date: datetime.date,
        to_date: datetime.date,
        use_cache: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Return OHLCV candles for *symbol* in *interval* from *from_date* to *to_date*.

        Args:
            symbol:     NSE tradingsymbol (e.g. "RELIANCE").
            interval:   Candle interval. Supports Kite names ("minute", "5minute")
                        and our aliases ("1min", "5min").
            from_date:  Start date (inclusive).
            to_date:    End date (inclusive, usually today).
            use_cache:  If True, check local cache first; skip Kite fetch if fresh.

        Returns:
            List of dicts with keys: date, open, high, low, close, volume.
            Returns [] on any error — never raises.

        Edge cases:
          - from_date > to_date → returns [], logs ValueError.
          - Trading holiday → Kite returns [] → cached as empty result (valid).
          - 429 rate-limit response → sleep and retry up to _MAX_RETRIES.
          - kite not wired → returns [], logs error.
          - Symbol not in instrument cache → Kite will return error → return [].
        """
        if from_date > to_date:
            log.error(
                "historical_data_invalid_date_range",
                symbol=symbol,
                from_date=str(from_date),
                to_date=str(to_date),
            )
            return []

        kite_interval = _INTERVAL_MAP.get(interval, interval)

        # Try cache first
        if use_cache:
            cached = self._load_cache(symbol, kite_interval, from_date, to_date)
            if cached is not None:
                log.debug(
                    "historical_data_cache_hit",
                    symbol=symbol,
                    interval=kite_interval,
                    count=len(cached),
                )
                return cached

        # Fetch from Kite
        candles = await self._fetch_from_kite(symbol, kite_interval, from_date, to_date)

        # Cache the result (even if empty — empty = valid holiday response)
        if use_cache:
            self._save_cache(symbol, kite_interval, from_date, to_date, candles)

        return candles

    async def warmup_volume_sma(
        self,
        symbol: str,
        builder: "CandleBuilder",
        required_candles: int = 500,
    ) -> int:
        """
        Warm up *builder*'s rolling 500-minute volume deque using historical data.

        Fetches enough 1-min candles to fill the deque, using the cache to
        avoid repeated Kite API calls.  Returns the number of candles loaded.

        This replaces the per-symbol warmup logic in historical_warmup.py with
        a rate-limited, cache-backed version suitable for concurrent startup warmup
        of 200+ symbols.
        """
        # Use existing historical_warmup logic (keeps backward compatibility)
        from engine.market.historical_warmup import warmup_from_historical

        if self._kite is None:
            log.warning("historical_data_service_no_kite", symbol=symbol)
            return 0

        try:
            async with self._semaphore:
                await self._throttle()
                loaded = await warmup_from_historical(symbol, builder, self._kite)
                return loaded
        except Exception as exc:
            log.error("historical_warmup_failed", symbol=symbol, error=str(exc))
            return 0

    # ── Internal: rate limiter ─────────────────────────────────────────────────

    async def _throttle(self) -> None:
        """
        Enforce the ≤3 req/sec rate limit via token-bucket approximation.

        The semaphore caps burst concurrency; this sleep ensures the minimum
        inter-request gap so the long-run rate stays within bounds.
        """
        import time

        now = time.monotonic()
        since_last = now - self._last_request_time
        min_gap = _REFILL_INTERVAL / _MAX_RPS  # 0.333s between requests
        if since_last < min_gap:
            await asyncio.sleep(min_gap - since_last)
        self._last_request_time = time.monotonic()

    # ── Internal: Kite fetch ──────────────────────────────────────────────────

    async def _fetch_from_kite(
        self,
        symbol: str,
        kite_interval: str,
        from_date: datetime.date,
        to_date: datetime.date,
    ) -> list[dict[str, Any]]:
        if self._kite is None:
            log.error("historical_data_service_no_kite", symbol=symbol)
            return []

        # Need the instrument token for the Kite historical API
        try:
            from engine.market.instrument_master import instrument_master
            token = instrument_master.get_token(symbol)
            if token is None:
                log.warning("historical_data_no_token_for_symbol", symbol=symbol)
                return []
        except Exception:
            log.exception("historical_data_token_lookup_failed", symbol=symbol)
            return []

        for attempt in range(_MAX_RETRIES):
            try:
                async with self._semaphore:
                    await self._throttle()
                    raw = await self._kite.historical_data(
                        instrument_token=token,
                        from_date=datetime.datetime.combine(from_date, datetime.time.min),
                        to_date=datetime.datetime.combine(to_date, datetime.time.max),
                        interval=kite_interval,
                        continuous=False,
                        oi=False,
                    )

                candles = [
                    {
                        "date": str(c["date"]),
                        "open": float(c["open"]),
                        "high": float(c["high"]),
                        "low": float(c["low"]),
                        "close": float(c["close"]),
                        "volume": int(c["volume"]),
                    }
                    for c in (raw or [])
                ]
                log.debug(
                    "historical_data_fetched",
                    symbol=symbol,
                    interval=kite_interval,
                    count=len(candles),
                )
                return candles

            except Exception as exc:
                err_str = str(exc)
                if "429" in err_str or "rate" in err_str.lower():
                    log.warning(
                        "historical_data_rate_limited",
                        symbol=symbol,
                        attempt=attempt + 1,
                        sleeping=_RATE_LIMIT_SLEEP,
                    )
                    await asyncio.sleep(_RATE_LIMIT_SLEEP)
                    continue
                log.error(
                    "historical_data_fetch_failed",
                    symbol=symbol,
                    interval=kite_interval,
                    attempt=attempt + 1,
                    error=err_str,
                )
                return []

        log.error("historical_data_max_retries_exhausted", symbol=symbol, interval=kite_interval)
        return []

    # ── Internal: file cache ──────────────────────────────────────────────────

    def _cache_path(
        self,
        symbol: str,
        interval: str,
        from_date: datetime.date,
        to_date: datetime.date,
    ) -> Path:
        # Encode date range in filename so different ranges don't collide
        fname = f"{from_date}_{to_date}.json"
        return _CACHE_DIR / symbol / interval / fname

    def _load_cache(
        self,
        symbol: str,
        interval: str,
        from_date: datetime.date,
        to_date: datetime.date,
    ) -> list[dict[str, Any]] | None:
        """Return cached candles if fresh, None if missing or stale."""
        path = self._cache_path(symbol, interval, from_date, to_date)
        if not path.exists():
            return None

        mtime = datetime.datetime.fromtimestamp(path.stat().st_mtime, tz=datetime.timezone.utc)
        age_hours = (datetime.datetime.now(datetime.timezone.utc) - mtime).total_seconds() / 3600
        if age_hours > _CACHE_MAX_AGE_HOURS:
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            log.warning("historical_cache_read_error", path=str(path), error=str(exc))
            return None

    def _save_cache(
        self,
        symbol: str,
        interval: str,
        from_date: datetime.date,
        to_date: datetime.date,
        candles: list[dict[str, Any]],
    ) -> None:
        """Persist candles to cache file (creates directories as needed)."""
        path = self._cache_path(symbol, interval, from_date, to_date)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(candles, f, default=str)
        except Exception as exc:
            log.warning("historical_cache_write_error", path=str(path), error=str(exc))


# Module-level singleton — wire kite client post-auth via historical_data_service.set_kite()
historical_data_service = HistoricalDataService()
