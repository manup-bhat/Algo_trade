"""
engine/runner.py — Engine entry point. asyncio.run(main()) here.

Phase 1: Connects to Kite WebSocket, initializes CandleBuilders,
         loads SMA history, starts tick processing. No orders, no strategy.

Run with: python -m engine.runner
"""

from __future__ import annotations

import asyncio
import datetime
import signal
import sys
from pathlib import Path

import pytz
import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Add trading_bot to sys.path if running as module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.core.logging import configure_logging
from app.store.redis_client import get_redis
from engine.kite.instruments import InstrumentCache, load_instruments_async
from engine.market.calendar import is_market_open, now_ist
from engine.market.universe import load_universe
from engine.store.redis_store import RedisStore
from engine.strategy.coordinator import Coordinator

log = structlog.get_logger(__name__)

IST_TZ = pytz.timezone("Asia/Kolkata")

# ── Global engine state ────────────────────────────────────────────────────
_coordinator: Coordinator | None = None
_ticker: object | None = None
_scheduler: AsyncIOScheduler | None = None
_running = True


# ── APScheduler Jobs ──────────────────────────────────────────────────────

async def job_pre_market_setup() -> None:
    """09:00 AM IST — Load instruments, SMA history, subscribe WebSocket."""
    assert _coordinator is not None
    redis_client = get_redis()
    redis_store = RedisStore(redis_client)

    log.info("pre_market_setup_start")

    try:
        # 1. Load instruments (needs real kite client — Phase 4 wires this fully)
        #    For Phase 1, we use cached instrument data if available
        log.info("pre_market_setup_instruments_note",
                 message="Real instruments load requires Kite auth — wire in Phase 4")

        # 2. Reset daily state
        await redis_store.set_circuit_breaker(False)
        await redis_store.set_daily_pnl(0.0)
        await redis_store.set_blocked_margin(0.0)

        # 3. Load SMA history
        await _coordinator.load_sma_histories()

        # 4. Set pre-market status
        await redis_store.set_engine_status({
            "status": "PRE_MARKET_READY",
            "timestamp": now_ist().isoformat(),
            **_coordinator.get_stats(),
        })
        log.info("pre_market_setup_complete")

    except Exception as exc:
        log.error("pre_market_setup_failed", error=str(exc), exc_info=True)


async def job_market_open() -> None:
    """09:15 AM IST — Reset builders for new session, activate scanning."""
    assert _coordinator is not None
    redis_client = get_redis()
    redis_store = RedisStore(redis_client)

    await _coordinator.on_market_open()

    await redis_store.set_engine_status({
        "status": "SCANNING",
        "timestamp": now_ist().isoformat(),
        **_coordinator.get_stats(),
    })
    log.info("market_open", **_coordinator.get_stats())


async def job_session_end() -> None:
    """15:25 PM IST — Persist SMA history, write daily summary."""
    assert _coordinator is not None
    redis_client = get_redis()
    redis_store = RedisStore(redis_client)

    await _coordinator.persist_sma_histories()
    await redis_store.set_engine_status({
        "status": "MARKET_CLOSED",
        "timestamp": now_ist().isoformat(),
        **_coordinator.get_stats(),
    })
    log.info("session_end_sma_persisted", **_coordinator.get_stats())


async def job_squareoff() -> None:
    """15:20 PM IST — Square off all open positions (Phase 3+ wires real orders)."""
    log.info("squareoff_job_fired_phase1_noop")


# ── Graceful Shutdown ─────────────────────────────────────────────────────

def _handle_signal(sig: int, frame: object) -> None:
    global _running
    log.warning("shutdown_signal_received", signal=signal.Signals(sig).name)
    _running = False


async def shutdown(loop: asyncio.AbstractEventLoop) -> None:
    """Gracefully stop scheduler, ticker, and event loop."""
    global _ticker, _scheduler

    log.info("engine_shutting_down")

    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)

    if _ticker is not None:
        try:
            _ticker.stop()  # type: ignore[attr-defined]
        except Exception as exc:
            log.warning("ticker_stop_error", error=str(exc))

    # Persist SMA history on clean shutdown
    if _coordinator is not None:
        try:
            await _coordinator.persist_sma_histories()
        except Exception as exc:
            log.warning("sma_persist_on_shutdown_failed", error=str(exc))

    log.info("engine_shutdown_complete")


# ── Main ──────────────────────────────────────────────────────────────────

async def main() -> None:
    global _coordinator, _ticker, _scheduler

    configure_logging(settings.LOG_LEVEL)
    log.info(
        "engine_starting",
        version="phase1",
        paper_trade=settings.is_paper_trade,
        log_level=settings.LOG_LEVEL,
    )

    # ── Redis connection ───────────────────────────────────────────────
    redis_client = get_redis()
    redis_store = RedisStore(redis_client)

    if not await redis_store.ping():
        log.critical("redis_not_reachable", hint="Start Redis: docker compose up -d redis")
        return

    log.info("redis_connected", url=settings.REDIS_URL)

    # ── Coordinator ────────────────────────────────────────────────────
    _coordinator = Coordinator(redis_store)

    # Load universe (without live instruments in Phase 1 — using file only)
    raw_symbols = load_universe()
    log.info("universe_symbols_loaded", count=len(raw_symbols))

    # Initialize builders for all universe symbols
    # In Phase 1 we use a stub InstrumentInfo to populate builders
    # Full instrument loading is wired in Phase 4 with real Kite auth
    instrument_cache = InstrumentCache()
    # Bootstrap: create minimal InstrumentInfo entries for universe symbols
    # so builders can be initialized. Tokens are 0 until real instruments loaded.
    stub_universe: dict = {}
    from engine.kite.instruments import InstrumentInfo
    for i, sym in enumerate(raw_symbols[:500]):  # Cap at 500 per spec
        stub_universe[sym] = InstrumentInfo(
            instrument_token=i + 1,  # Placeholder; replaced at 09:00 AM with real tokens
            symbol=sym,
            tick_size=0.05,
            lot_size=1,
            series="EQ",
            last_price=0.0,
        )

    _coordinator.initialize_builders(stub_universe, sma_period=settings.VOLUME_SMA_PERIOD)

    # Load any persisted SMA history from Redis
    await _coordinator.load_sma_histories()

    # ── AsyncKiteTicker (Phase 1: connects but needs real token) ──────
    # The ticker is initialized here but would need a real access_token.
    # For Phase 1 validation without Kite credentials, the ticker is skipped.
    # Uncomment and wire properly in Phase 4 after auth is built.
    #
    # from engine.kite.ticker import AsyncKiteTicker, MODE_QUOTE
    # loop = asyncio.get_event_loop()
    # _ticker = AsyncKiteTicker(settings.KITE_API_KEY, access_token, loop, _coordinator)
    # _ticker.start()
    # tokens = [info.instrument_token for info in stub_universe.values()]
    # _ticker.subscribe(tokens)
    # _ticker.set_mode(MODE_QUOTE, tokens)

    log.info(
        "engine_ticker_note",
        message="KiteTicker disabled in Phase 1 — wire access_token in Phase 4",
    )

    # ── APScheduler ───────────────────────────────────────────────────
    _scheduler = AsyncIOScheduler(timezone=IST_TZ)

    _scheduler.add_job(
        job_pre_market_setup, "cron", hour=9, minute=0,
        id="pre_market_setup", replace_existing=True,
    )
    _scheduler.add_job(
        job_market_open, "cron", hour=9, minute=15,
        id="market_open", replace_existing=True,
    )
    _scheduler.add_job(
        job_squareoff, "cron", hour=15, minute=20,
        id="squareoff", replace_existing=True,
    )
    _scheduler.add_job(
        job_session_end, "cron", hour=15, minute=25,
        id="session_end", replace_existing=True,
    )

    _scheduler.start()
    log.info("scheduler_started", jobs=[j.id for j in _scheduler.get_jobs()])

    # ── Engine status ─────────────────────────────────────────────────
    await redis_store.set_engine_status({
        "status": "RUNNING_PHASE1",
        "timestamp": now_ist().isoformat(),
        **_coordinator.get_stats(),
    })

    log.info(
        "engine_running",
        builders=len(_coordinator.candle_builders),
        warmed_up=_coordinator.get_stats()["warmed_up"],
    )

    # ── Main loop ─────────────────────────────────────────────────────
    # In Phase 1: just keep alive + respond to control signals.
    # In Phase 4: engine control commands from Redis are polled here.
    loop = asyncio.get_event_loop()
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        while _running:
            await asyncio.sleep(5)
            # Poll engine control (Phase 4 adds START/STOP/EMERGENCY_STOP handling)
            control = await redis_store.get_engine_control()
            if control == "EMERGENCY_STOP":
                log.critical("emergency_stop_received")
                break
    finally:
        await shutdown(loop)


if __name__ == "__main__":
    asyncio.run(main())
