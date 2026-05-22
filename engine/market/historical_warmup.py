"""
engine/market/historical_warmup.py — Smart sliding-window SMA warmup from Kite historical API.

WHEN IT'S CALLED:
  09:00 AM from job_pre_market_setup(), AFTER:
    - instruments are loaded (builders initialized)
    - load_sma_histories() has loaded persisted data from disk/Redis

THE MATH — HOW MUCH DATA IS ACTUALLY NEEDED:
  Strategy uses a 500-period volume SMA (VOLUME_SMA_PERIOD=500).
  NSE market hours: 09:15 AM – 03:30 PM = exactly 375 one-minute candles per day.
  To fill the 500-period deque: ceil(500 / 375) = 2 trading days minimum.
  We use 3 days as a safety buffer (accounts for partial trading days etc.)

  So we only ever need to fetch at most 3 days of Kite historical data — NOT 5.
  Setting HISTORICAL_WARMUP_TRADING_DAYS=5 was wasteful; 3 is now the max.

SLIDING WINDOW — HOW IT WORKS:
  The CandleBuilder uses deque(maxlen=500). This IS the sliding window.
  Each trading day appends ~375 volumes, dropping the oldest ~375 automatically.

  The disk file (sma_histories.json.gz) stores:
    - The current 500-volume snapshot per symbol
    - The `as_of_date`: last trading date whose data is included

  On startup:
    Case A — file covers yesterday (as_of_date == yesterday):
      → All symbols already warmed, skip SMA fetch from Kite entirely
      → Only fetch recent candles for dashboard chart drawer (1-day call only)

    Case B — file is N days stale (e.g. weekend, holiday, missed day):
      → Load file (partially warmed)
      → Fetch ONLY the N gap days from Kite (not 5 full days)
      → Slide the deque: new days appended, oldest fall off automatically
      → After sliding: as_of_date is updated to yesterday

    Case C — no file (fresh install or first day):
      → Fetch 3 trading days from Kite (minimum for 500-period SMA)
      → Fully warms all builders

  Result: After the first day, startup warmup fetches 0–3 days (usually 0 or 1).

RATE LIMITING:
  HISTORICAL_WARMUP_CONCURRENCY=8, BATCH_DELAY_SEC=0.2 (configured in .env)
  → ceil(500/8) = 63 batches × 0.2s = ~13s minimum; real ~45-60s for full warmup.
  → On subsequent days (Case A): only candle fetch needed, ~30s total.
"""

from __future__ import annotations

import asyncio
import datetime
from typing import TYPE_CHECKING, Any

import pytz
import structlog

from app.core.config import settings
from engine.store import sma_file_store

if TYPE_CHECKING:
    from engine.kite.client import AsyncKiteClient
    from engine.store.redis_store import RedisStore
    from engine.strategy.coordinator import Coordinator

log = structlog.get_logger(__name__)
IST_TZ = pytz.timezone("Asia/Kolkata")

# Hard cap: never fetch more than SMA_TRADING_DAYS_NEEDED days from Kite.
# Even if the file is 10 days old, we only need the last 3 days for the SMA.
_MAX_WARMUP_DAYS = sma_file_store.SMA_TRADING_DAYS_NEEDED  # = 3


def _make_date_range(
    from_date: datetime.date,
    to_date: datetime.date,
) -> tuple[datetime.datetime, datetime.datetime]:
    """Convert date range to IST-aware datetimes for Kite API."""
    return (
        datetime.datetime.combine(from_date, datetime.time.min).replace(tzinfo=IST_TZ),
        datetime.datetime.combine(to_date, datetime.time(15, 30)).replace(tzinfo=IST_TZ),
    )


def _get_fetch_date_range() -> tuple[datetime.datetime, datetime.datetime, datetime.date]:
    """
    Calculate the date range for historical data fetch.

    Returns:
        (from_datetime, to_datetime, yesterday_date)

    to_date = yesterday's close (last complete trading session).
    from_date = to_date minus enough calendar days to cover _MAX_WARMUP_DAYS trading days.
    (Calendar days = trading days × 2 + 4 handles weekends and holiday clusters.)
    """
    today = datetime.datetime.now(IST_TZ).date()
    yesterday = today - datetime.timedelta(days=1)
    # Use 2× buffer to handle consecutive holidays / weekends
    calendar_days = _MAX_WARMUP_DAYS * 2 + 4
    from_date = yesterday - datetime.timedelta(days=calendar_days)
    from_dt, to_dt = _make_date_range(from_date, yesterday)
    return from_dt, to_dt, yesterday


def _get_gap_date_range(
    as_of_date: datetime.date,
) -> tuple[datetime.datetime, datetime.datetime]:
    """
    Calculate the date range to fetch for gap days only.

    Args:
        as_of_date: Last date already covered by the SMA file.

    Returns:
        (from_datetime, to_datetime) covering the day AFTER as_of_date up to yesterday.
    """
    gap_from = as_of_date + datetime.timedelta(days=1)
    today = datetime.datetime.now(IST_TZ).date()
    yesterday = today - datetime.timedelta(days=1)
    from_dt, to_dt = _make_date_range(gap_from, yesterday)
    return from_dt, to_dt


class _CandleLike:
    """
    Minimal duck-type compatible with redis_store.append_recent_candle().
    Wraps a raw Kite historical dict { date, open, high, low, close, volume }.
    """
    __slots__ = ("timestamp", "open", "high", "low", "close", "volume", "turnover")

    def __init__(self, raw: dict[str, Any]) -> None:
        ts = raw.get("date") or raw.get("timestamp")
        if isinstance(ts, datetime.datetime):
            self.timestamp = ts if ts.tzinfo else IST_TZ.localize(ts)
        elif isinstance(ts, str):
            try:
                self.timestamp = datetime.datetime.fromisoformat(ts)
                if self.timestamp.tzinfo is None:
                    self.timestamp = IST_TZ.localize(self.timestamp)
            except ValueError:
                self.timestamp = datetime.datetime.now(IST_TZ)
        else:
            self.timestamp = datetime.datetime.now(IST_TZ)

        self.open     = float(raw.get("open", 0))
        self.high     = float(raw.get("high", 0))
        self.low      = float(raw.get("low", 0))
        self.close    = float(raw.get("close", 0))
        self.volume   = int(raw.get("volume", 0))
        self.turnover = round(self.close * self.volume, 2)


async def _fetch_and_process_symbol(
    symbol: str,
    instrument_token: int,
    builder: "object",  # CandleBuilder
    kite: "AsyncKiteClient",
    redis_store: "RedisStore | None",
    from_dt: datetime.datetime,
    to_dt: datetime.datetime,
    recent_candles_limit: int,
    load_sma: bool,  # True = load volumes into builder; False = candles only
) -> tuple[str, int, str]:
    """
    Fetch historical 1-minute candles for one symbol.

    Args:
        load_sma:  If True, extract volumes and call builder.load_history().
                   If False (already warmed), skip SMA loading — only store candles.

    Returns:
        (symbol, candle_count, status)
        status: "warmed" | "partial" | "candles_only" | "error"
    """
    from engine.market.candle_builder import CandleBuilder
    assert isinstance(builder, CandleBuilder)

    try:
        candles: list[dict] = await kite.historical_data(
            instrument_token=instrument_token,
            from_date=from_dt,
            to_date=to_dt,
            interval="minute",
        )
    except Exception as exc:
        log.warning(
            "warmup_fetch_failed",
            symbol=symbol,
            token=instrument_token,
            error=str(exc),
        )
        return symbol, 0, "error"

    if not candles:
        log.debug("warmup_no_candles", symbol=symbol, token=instrument_token)
        return symbol, 0, "error"

    # ── Load volumes into SMA deque (sliding window via deque maxlen) ─────────
    if load_sma:
        volumes = [int(c.get("volume", 0)) for c in candles]
        # CandleBuilder.load_history() clears and reloads the deque (last sma_period values)
        # The deque's maxlen=500 enforces the sliding window automatically.
        builder.load_history(volumes)
        log.debug(
            "warmup_sma_loaded",
            symbol=symbol,
            fetched=len(candles),
            history_size=builder.history_size,
            warmed_up=builder.is_warmed_up,
        )

    # ── Store recent candles to Redis for chart drawer ────────────────────────
    if redis_store is not None:
        recent = candles[-recent_candles_limit:]
        volume_sma = builder.volume_sma
        for raw in recent:
            try:
                await redis_store.append_recent_candle(
                    symbol, _CandleLike(raw), volume_sma_500=volume_sma
                )
            except Exception as exc:
                log.debug("warmup_candle_store_error", symbol=symbol, error=str(exc))
                break  # Don't spam errors

    status = "candles_only" if not load_sma else ("warmed" if builder.is_warmed_up else "partial")
    return symbol, len(candles), status


async def _run_batch(
    symbols_batch: list[tuple[str, int, "object"]],
    kite: "AsyncKiteClient",
    redis_store: "RedisStore | None",
    from_dt: datetime.datetime,
    to_dt: datetime.datetime,
    recent_limit: int,
    load_sma: bool,
    batch_delay: float,
    concurrency: int,
) -> tuple[int, int, int]:
    """
    Process symbols in batches of `concurrency` parallel requests.
    Returns (warmed_ok, partial, errors).
    """
    warmed_ok = 0
    partial = 0
    errors = 0

    for i in range(0, len(symbols_batch), concurrency):
        chunk = symbols_batch[i: i + concurrency]
        tasks = [
            _fetch_and_process_symbol(
                sym, token, builder, kite, redis_store,
                from_dt, to_dt, recent_limit, load_sma,
            )
            for sym, token, builder in chunk
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for res in results:
            if isinstance(res, Exception):
                errors += 1
                log.warning("warmup_task_exception", error=str(res))
            else:
                _, n, status = res
                if status == "warmed":
                    warmed_ok += 1
                elif status in ("partial", "candles_only"):
                    partial += 1
                else:
                    errors += 1

        if batch_delay > 0 and i + concurrency < len(symbols_batch):
            await asyncio.sleep(batch_delay)

    return warmed_ok, partial, errors


async def warmup_from_historical(
    coordinator: "Coordinator",
    kite: "AsyncKiteClient",
    redis_store: "RedisStore | None" = None,
    symbols_subset: list[str] | None = None,
) -> None:
    """
    Smart sliding-window SMA warmup. Fetches the MINIMUM days needed from Kite.

    Decision logic:
      1. Read as_of_date from disk file (O(1) — reads only header bytes)
      2. Count gap trading days between as_of_date and yesterday
      3. If gap == 0: all warmed, only fetch candles for chart drawer (1-day fetch)
         If gap > 0 and gap <= MAX_WARMUP_DAYS: fetch gap days only
         If gap > MAX_WARMUP_DAYS or no file: fetch MAX_WARMUP_DAYS (3 days)
      4. For each symbol: load volumes into deque (gap/fresh only), always store candles

    The deque(maxlen=500) IS the sliding window — old data falls off automatically.

    symbols_subset: if provided, only warm these symbols (used when adding new
                    watchlist symbols mid-session via the edit modal).
    """
    if not settings.HISTORICAL_WARMUP_ENABLED:
        log.info("historical_warmup_disabled_skipping")
        return

    builders = coordinator.candle_builders
    token_map = coordinator.symbol_to_token

    # If a subset is specified (e.g. newly added watchlist symbols), filter builders.
    if symbols_subset is not None:
        subset_set = set(symbols_subset)
        builders = {s: b for s, b in builders.items() if s in subset_set}
        if not builders:
            log.info("warmup_subset_no_builders", requested=symbols_subset)
            return

    if not builders:
        log.warning("warmup_no_builders_initialized")
        return

    concurrency = settings.HISTORICAL_WARMUP_CONCURRENCY
    batch_delay = settings.HISTORICAL_WARMUP_BATCH_DELAY_SEC
    recent_limit = settings.HISTORICAL_WARMUP_RECENT_CANDLES

    today_ist = datetime.datetime.now(IST_TZ).date()
    yesterday = today_ist - datetime.timedelta(days=1)

    # ── Determine what data to fetch ──────────────────────────────────────────
    as_of_date = await asyncio.to_thread(sma_file_store.get_as_of_date)

    if as_of_date is not None:
        gap_days = sma_file_store.count_trading_days_gap(as_of_date, yesterday)
    else:
        gap_days = _MAX_WARMUP_DAYS  # No file → full warmup

    # For new symbols added mid-session: always force a full warmup
    # (they have no history in the SMA file regardless of as_of_date)
    if symbols_subset is not None:
        gap_days = _MAX_WARMUP_DAYS

    # Separate already-warmed and still-warming symbols
    already_warmed = [(s, token_map.get(s, 0), b)
                      for s, b in builders.items() if b.is_warmed_up]
    needs_warmup   = [(s, token_map.get(s, 0), b)
                      for s, b in builders.items() if not b.is_warmed_up]

    log.info(
        "historical_warmup_start",
        as_of_date=str(as_of_date) if as_of_date else "none",
        yesterday=yesterday.isoformat(),
        gap_trading_days=gap_days,
        already_warmed_sma=len(already_warmed),
        needs_sma_warmup=len(needs_warmup),
        total_symbols=len(builders),
        concurrency=concurrency,
        max_fetch_days=_MAX_WARMUP_DAYS,
        strategy="SLIDING_WINDOW",
    )

    # ── Case A: File is current (gap_days == 0) ───────────────────────────────
    # Already-warmed symbols: fetch only yesterday's candles for chart drawer.
    # Unwarmed symbols (shouldn't happen if file was saved correctly): full fetch.
    if gap_days == 0:
        log.info(
            "warmup_file_current",
            message="SMA histories up-to-date. Fetching only chart candles.",
            symbols_total=len(builders),
        )
        # Fetch yesterday only for dashboard chart population
        yesterday_from, yesterday_to = _make_date_range(yesterday, yesterday)

        if already_warmed:
            w, p, e = await _run_batch(
                already_warmed, kite, redis_store,
                yesterday_from, yesterday_to, recent_limit,
                load_sma=False,  # Candles only — SMA already warmed
                batch_delay=batch_delay, concurrency=concurrency,
            )
            log.info("warmup_candles_only_done",
                     candles_stored=len(already_warmed) - e, errors=e)

        if needs_warmup:
            # These slipped through — do a full fetch for them
            full_from, full_to, _ = _get_fetch_date_range()
            w, p, e = await _run_batch(
                needs_warmup, kite, redis_store,
                full_from, full_to, recent_limit,
                load_sma=True,
                batch_delay=batch_delay, concurrency=concurrency,
            )
            log.info("warmup_gap_fill_done",
                     warmed=w, partial=p, errors=e)
        _log_final_counts(builders, coordinator)
        return

    # ── Case B / C: Gap > 0 — fetch missing days ─────────────────────────────
    # Cap at MAX_WARMUP_DAYS regardless of actual gap (we only need 3 days for SMA)
    effective_gap = min(gap_days, _MAX_WARMUP_DAYS)
    if gap_days > _MAX_WARMUP_DAYS:
        log.info(
            "warmup_gap_capped",
            actual_gap_days=gap_days,
            using_days=effective_gap,
            reason=f"Only {_MAX_WARMUP_DAYS} days needed for {sma_file_store.SMA_PERIOD}-period SMA",
        )

    if as_of_date is not None and gap_days <= _MAX_WARMUP_DAYS:
        # Fetch only the gap period (not 3 full days)
        fetch_from, fetch_to = _get_gap_date_range(as_of_date)
    else:
        # No file or gap too large — fetch last MAX_WARMUP_DAYS trading days
        fetch_from, fetch_to, _ = _get_fetch_date_range()

    log.info(
        "warmup_fetching_range",
        from_date=fetch_from.date().isoformat(),
        to_date=fetch_to.date().isoformat(),
        effective_gap_days=effective_gap,
    )

    # Process ALL symbols: load_sma=True for unwarmed, False (candles-only) for warmed
    all_symbols: list[tuple[str, int, "object"]] = needs_warmup + already_warmed

    warmed_ok = partial = errors = 0
    for i in range(0, len(all_symbols), concurrency):
        chunk = all_symbols[i: i + concurrency]
        tasks = []
        for sym, token, builder in chunk:
            if token == 0:
                log.warning("warmup_no_token", symbol=sym)
                continue
            tasks.append(
                _fetch_and_process_symbol(
                    sym, token, builder, kite, redis_store,
                    fetch_from, fetch_to, recent_limit,
                    load_sma=(not builder.is_warmed_up),  # Only load SMA if not warmed
                )
            )
        if not tasks:
            continue

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for res in results:
            if isinstance(res, Exception):
                errors += 1
                log.warning("warmup_task_exception", error=str(res))
            else:
                _, n, status = res
                if status == "warmed":
                    warmed_ok += 1
                elif status in ("partial", "candles_only"):
                    partial += 1
                else:
                    errors += 1

        if batch_delay > 0 and i + concurrency < len(all_symbols):
            await asyncio.sleep(batch_delay)

    _log_final_counts(builders, coordinator)

    log.info(
        "historical_warmup_complete",
        gap_days_fetched=effective_gap,
        newly_warmed=warmed_ok,
        partial=partial,
        errors=errors,
    )


def _log_final_counts(builders: dict, coordinator: "Coordinator") -> None:
    """Update Redis scanner counts and log summary."""
    total_warmed = sum(1 for b in builders.values() if b.is_warmed_up)
    total_warming = len(builders) - total_warmed
    try:
        asyncio.ensure_future(
            coordinator._redis.set_scanner_counts(total_warmed, total_warming)
        )
    except Exception:
        pass
    log.info(
        "warmup_summary",
        total_warmed_sma=total_warmed,
        still_warming=total_warming,
        pct_ready=round(100 * total_warmed / max(len(builders), 1), 1),
    )
