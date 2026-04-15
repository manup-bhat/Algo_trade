"""
engine/runner.py — Phase 4: Production Engine Entry Point.

Lifecycle:
  08:50 AM         : Start process (manual)
  09:00 AM IST     : pre_market_setup — auth, capital, instruments, SMA, WS subscribe, orphan check
  09:15 AM IST     : market_open — reset builders, begin scanning
  <<market hours>> : reconcile_orders every 5 min (missed postbacks safety net)
  03:18 PM IST     : early_squareoff_check — if >1 MANAGING position, close all early
  03:20 PM IST     : squareoff — force close all open positions
  03:25 PM IST     : session_end — persist SMA, daily P&L, set status MARKET_CLOSED

Control loop polls Redis engine:control every 5 seconds for:
  START              → trigger market_open immediately (manual override)
  STOP               → new entries blocked, existing managed to 3:20 PM
  EMERGENCY_STOP     → immediate close of ALL positions, shutdown

Run with: PYTHONPATH=. uv run python -m engine.runner
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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.core.logging import configure_logging
from app.store.database import init_db
from app.store.redis_client import get_redis
from engine.kite.auth import load_token, validate_token
from engine.kite.client import AsyncKiteClient
from engine.kite.instruments import InstrumentCache, load_instruments_async
from engine.kite.ticker import AsyncKiteTicker, MODE_QUOTE
from engine.market.calendar import is_market_open, now_ist
from engine.market.universe import load_universe
from engine.orders.fill_timeout import fill_timeout_manager
from engine.orders.order_service import order_service
from engine.orders.order_tracker import order_tracker
from engine.risk.circuit_breaker import circuit_breaker
from engine.store.db_writer import DbWriter
from engine.store.redis_store import RedisStore
from engine.strategy.coordinator import Coordinator

log = structlog.get_logger(__name__)
IST_TZ = pytz.timezone("Asia/Kolkata")

# ── Globals (set in main, referenced by job functions) ───────────────────────

_coordinator: Coordinator | None = None
_kite_client: AsyncKiteClient | None = None
_ticker: AsyncKiteTicker | None = None
_scheduler: AsyncIOScheduler | None = None
_redis_store: RedisStore | None = None
_db_writer: DbWriter | None = None
_universe_tokens: list[int] = []
_running = True
_scanning_active = False


# ── Helpers ──────────────────────────────────────────────────────────────────

def _assert_ready() -> tuple[Coordinator, RedisStore, DbWriter]:
    assert _coordinator is not None, "coordinator not initialized"
    assert _redis_store is not None, "redis_store not initialized"
    assert _db_writer is not None, "db_writer not initialized"
    return _coordinator, _redis_store, _db_writer


# ── APScheduler Jobs ─────────────────────────────────────────────────────────

async def job_pre_market_setup() -> None:
    """
    09:00 AM IST — Full 8-step pre-market initialization (spec §10.1).

    Steps:
      1. Validate Kite token
      2. Fetch capital
      3. Reset daily state
      4. Load instruments (tick_size, tokens → Redis)
      5. Load SMA history
      6. Subscribe WebSocket
      7. Orphan check
      8. Set status PRE_MARKET_READY
    """
    global _kite_client, _ticker, _universe_tokens

    coordinator, redis_store, db_writer = _assert_ready()
    log.info("pre_market_setup_start")

    # ── 1. Validate token ────────────────────────────────────────────
    try:
        from kiteconnect import KiteConnect  # type: ignore[import-untyped]
    except ImportError:
        log.critical("kiteconnect_not_installed")
        await redis_store.set_engine_status({
            "status": "KITECONNECT_MISSING",
            "timestamp": now_ist().isoformat(),
        })
        return

    kite_obj = KiteConnect(api_key=settings.KITE_API_KEY)
    access_token = await load_token(
        token_path=settings.KITE_TOKEN_PATH,
        redis_store=redis_store,
    )

    if not access_token:
        log.critical("no_access_token_on_pre_market_setup")
        await redis_store.set_engine_status({
            "status": "AUTH_REQUIRED",
            "timestamp": now_ist().isoformat(),
        })
        return

    if not validate_token(kite_obj, access_token):
        await redis_store.set_engine_status({
            "status": "AUTH_EXPIRED",
            "timestamp": now_ist().isoformat(),
        })
        return

    _kite_client = AsyncKiteClient(kite_obj)
    order_service.set_kite(_kite_client)

    # Wire kite into coordinator
    coordinator.inject_dependencies(
        order_service=order_service,
        order_tracker=order_tracker,
        fill_timeout_manager=fill_timeout_manager,
        kite=_kite_client,
    )

    log.info("kite_authenticated")

    # ── 2. Fetch capital ─────────────────────────────────────────────
    try:
        capital = await _kite_client.get_net_equity()
        log.info("day_capital_fetched", capital=capital)
    except Exception as exc:
        log.error("capital_fetch_failed", error=str(exc))
        capital = await redis_store.get_capital()  # Use stale if available
        log.warning("using_stale_capital", capital=capital)
        
    override_cap = await redis_store.get_max_capital_override()
    if override_cap is not None:
        capital = min(capital, override_cap)
        log.info("capital_override_applied", override_cap=override_cap, final_capital=capital)
        
    await redis_store.set_capital(capital)

    # ── 3. Reset daily state ─────────────────────────────────────────
    await redis_store.set_circuit_breaker(False)
    await circuit_breaker.reset(redis_store)
    await redis_store.set_daily_pnl(0.0)
    await redis_store.set_blocked_margin(0.0)
    log.info("daily_state_reset")

    # ── 4. Load instruments ──────────────────────────────────────────
    raw_symbols = load_universe()
    try:
        # load_instruments_async returns raw list from kite.instruments("NSE")
        raw_instruments: list[dict] = await load_instruments_async(_kite_client)
        cache = InstrumentCache()
        cache.load(raw_instruments)
        universe = cache.filter_to_universe(
            raw_symbols,
            min_price=settings.MIN_PRICE,
            max_price=settings.MAX_PRICE,
        )
        coordinator.initialize_builders(universe, sma_period=settings.VOLUME_SMA_PERIOD)

        # Store tick_size and token in Redis for each symbol
        for symbol, info in universe.items():
            await redis_store.set_tick_size(symbol, info.tick_size)
            await redis_store.set_instrument_token(symbol, info.instrument_token)

        _universe_tokens = [info.instrument_token for info in universe.values()]
        log.info("instruments_loaded", symbol_count=len(universe))

    except Exception as exc:
        log.error("instruments_load_failed", error=str(exc), exc_info=True)
        return

    # ── 5. Load SMA history ──────────────────────────────────────────
    await coordinator.load_sma_histories()

    # -- 6. Subscribe WebSocket --
    loop = asyncio.get_event_loop()
    if _ticker is None:
        _ticker_new = AsyncKiteTicker(
            api_key=settings.KITE_API_KEY,
            access_token=access_token,
            loop=loop,
            coordinator=coordinator,
        )
        # Store tokens before start() so _on_connect subscribes once WS is open
        if _universe_tokens:
            _ticker_new._subscribed_tokens = _universe_tokens
        _ticker_new.start()
        globals()["_ticker"] = _ticker_new
        log.info("ws_connecting_tokens_queued", token_count=len(_universe_tokens))
    else:
        # Already running (reinit after re-login) - update tokens
        if _universe_tokens:
            globals()["_ticker"]._subscribed_tokens = _universe_tokens
            try:
                globals()["_ticker"].subscribe(_universe_tokens)
                globals()["_ticker"].set_mode(MODE_QUOTE, _universe_tokens)
                log.info("ws_resubscribed", token_count=len(_universe_tokens))
            except AttributeError:
                log.info("ws_subscribe_deferred_until_connect")

    # ── 7. Orphan check ──────────────────────────────────────────────
    await coordinator.orphan_check(_kite_client)

    # ── 8. Set status ────────────────────────────────────────────────
    await redis_store.set_engine_status({
        "status": "PRE_MARKET_READY",
        "timestamp": now_ist().isoformat(),
        "paper_trade": settings.is_paper_trade,
        **coordinator.get_stats(),
    })
    log.info("pre_market_setup_complete", **coordinator.get_stats())


async def job_market_open() -> None:
    """09:15 AM IST — Reset all candle builders, activate scanner."""
    global _scanning_active

    coordinator, redis_store, _ = _assert_ready()

    await coordinator.on_market_open()
    coordinator.set_new_entries_enabled(True)
    _scanning_active = True

    await redis_store.set_engine_status({
        "status": "SCANNING",
        "timestamp": now_ist().isoformat(),
        "paper_trade": settings.is_paper_trade,
        **coordinator.get_stats(),
    })
    log.info("market_open", **coordinator.get_stats())


async def job_early_squareoff_check() -> None:
    """
    03:18 PM IST — If more than 1 MANAGING position, close all now.
    Sequential API calls (cancel SL + market sell × N) need more time buffer.
    """
    coordinator, redis_store, _ = _assert_ready()

    stats = coordinator.get_stats()
    managing = stats.get("managing_positions", 0)

    if managing > 1:
        log.warning(
            "early_squareoff_triggered",
            managing_positions=managing,
            reason="multiple_positions_need_time_buffer",
        )
        await coordinator.on_squareoff()
        await redis_store.set_engine_status({
            "status": "SQUARING_OFF",
            "timestamp": now_ist().isoformat(),
            **coordinator.get_stats(),
        })


async def job_squareoff() -> None:
    """03:20 PM IST — Force close ALL remaining open positions."""
    coordinator, redis_store, _ = _assert_ready()

    log.info("squareoff_job_start")
    await coordinator.on_squareoff()

    await redis_store.set_engine_status({
        "status": "SQUARING_OFF",
        "timestamp": now_ist().isoformat(),
        **coordinator.get_stats(),
    })
    log.info("squareoff_job_complete", **coordinator.get_stats())


async def job_session_end() -> None:
    """
    03:25 PM IST — Persist SMA history, write daily P&L, unsubscribe WS.
    Spec §10.5.
    """
    coordinator, redis_store, db_writer = _assert_ready()

    log.info("session_end_start")

    # 1. Persist SMA history
    await coordinator.persist_sma_histories()

    # 2. Write daily summary
    if _kite_client is not None:
        try:
            daily_pnl = await redis_store.get_daily_pnl()
            capital = await redis_store.get_capital()
            stats = coordinator.get_stats()
            await db_writer.write_daily_pnl(
                trade_date=now_ist().date(),
                total_capital=capital,
                signals_fired=stats.get("total_signals", 0),
                setups_abandoned=0,
                trades_taken=0,
                winning_trades=0,
                losing_trades=0,
                breakeven_trades=0,
                gross_pnl=daily_pnl,
                total_charges=0.0,
                net_pnl=daily_pnl,
            )
        except Exception as exc:
            log.error("daily_pnl_write_failed", error=str(exc))

    # 3. Unsubscribe WebSocket
    if _ticker is not None and _universe_tokens:
        try:
            _ticker.unsubscribe(_universe_tokens)
        except Exception as exc:
            log.warning("ws_unsubscribe_failed", error=str(exc))

    # 4. Persist market snapshot for after-hours dashboard
    try:
        symbol_count = await redis_store.persist_eod_market_snapshot()
        log.info("eod_market_snapshot_persisted", symbol_count=symbol_count)
    except Exception as exc:
        log.warning("eod_market_snapshot_persist_failed", error=str(exc))

    # 5. Set final status
    await redis_store.set_engine_status({
        "status": "MARKET_CLOSED",
        "timestamp": now_ist().isoformat(),
        **coordinator.get_stats(),
    })

    log.info("session_end_complete", **coordinator.get_stats())


async def job_reconcile() -> None:
    """
    Every 5 minutes during market hours — spec §12.2.
    Catches any postbacks missed by WebSocket.
    """
    coordinator, _, _ = _assert_ready()

    if not is_market_open() or _kite_client is None:
        return

    await coordinator.reconcile_orders(_kite_client)


# ── Graceful Shutdown ─────────────────────────────────────────────────────────

def _handle_signal(sig: int, frame: object) -> None:
    global _running
    log.warning("shutdown_signal_received", signal=signal.Signals(sig).name)
    _running = False


async def shutdown(loop: asyncio.AbstractEventLoop) -> None:
    """Gracefully stop scheduler, ticker, persist SMA."""
    global _ticker, _scheduler

    log.info("engine_shutting_down")

    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)

    if _ticker is not None:
        try:
            _ticker.stop()
        except Exception as exc:
            log.warning("ticker_stop_error", error=str(exc))

    if _coordinator is not None:
        try:
            await _coordinator.persist_sma_histories()
        except Exception as exc:
            log.warning("sma_persist_on_shutdown_failed", error=str(exc))

    if _redis_store is not None:
        try:
            await _redis_store.set_engine_status({
                "status": "OFFLINE",
                "timestamp": now_ist().isoformat(),
            })
        except Exception:
            pass

    log.info("engine_shutdown_complete")


# ── Emergency Stop ────────────────────────────────────────────────────────────

async def _emergency_stop() -> None:
    """Immediate market close of all positions, then shutdown."""
    log.critical("emergency_stop_received_squaring_off_all")
    if _coordinator is not None:
        await _coordinator.on_squareoff()
    if _redis_store is not None:
        await _redis_store.set_engine_status({
            "status": "EMERGENCY_STOP",
            "timestamp": now_ist().isoformat(),
        })


# ── Configuration Polling ─────────────────────────────────────────────────────

async def _poll_config() -> None:
    """Poll Redis for configuration overrides every 5 seconds (allows runtime adjustments without restart)."""
    while True:
        try:
            if _redis_store is not None:
                override_pt = await _redis_store.get_paper_trade_override()
                if override_pt is not None and settings.PAPER_TRADE != override_pt:
                    settings.PAPER_TRADE = override_pt
                    log.info("runtime_config_updated", paper_trade=override_pt)

                # Check if a fresh login just happened → re-run pre-market setup
                if await _redis_store.consume_reinit_trigger():
                    log.info("reinit_trigger_detected_re_running_pre_market_setup")
                    try:
                        await job_pre_market_setup()
                    except Exception as exc:
                        log.error("reinit_triggered_pre_market_setup_failed", error=str(exc))
                    continue  # skip status update this cycle — pre_market_setup sets it

                # Push heartbeat telemetry — but NEVER clobber auth failure states
                if _coordinator is not None:
                    current = await _redis_store.get_engine_status() or {}
                    current_status = current.get("status", "")
                    # Auth failure states must persist until user re-logs in
                    if current_status not in ("AUTH_REQUIRED", "AUTH_EXPIRED", "KITECONNECT_MISSING"):
                        new_status = "ONLINE" if (_ticker is not None) else "PRE_MARKET_READY"
                        await _redis_store.set_engine_status({
                            "status": new_status,
                            "timestamp": now_ist().isoformat(),
                            "total_ticks": _coordinator._tick_count,
                            "paper_trade": settings.is_paper_trade,
                        })
        except Exception as exc:
            log.debug("config_poll_error", error=str(exc))
        await asyncio.sleep(5)


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    global _coordinator, _redis_store, _db_writer, _scheduler

    configure_logging(settings.LOG_LEVEL)
    log.info(
        "engine_starting",
        version="phase4",
        paper_trade=settings.is_paper_trade,
        log_level=settings.LOG_LEVEL,
    )

    # ── Database ──────────────────────────────────────────────────────────────
    try:
        await init_db()
        log.info("database_initialized")
    except Exception as exc:
        log.critical("database_init_failed", error=str(exc))
        return

    # ── Redis ──────────────────────────────────────────────────────────────────
    redis_client = get_redis()
    _redis_store = RedisStore(redis_client)

    if not await _redis_store.ping():
        log.critical(
            "redis_not_reachable",
            hint="Start Redis on localhost:6379 (local service preferred) or run docker compose up -d redis",
        )
        return
    log.info("redis_connected", url=settings.REDIS_URL)

    # ── DB Writer ─────────────────────────────────────────────────────────────
    _db_writer = DbWriter()

    # ── Coordinator (without kite deps — wired in job_pre_market_setup) ───────
    _coordinator = Coordinator(_redis_store, _db_writer)


    # ── APScheduler ──────────────────────────────────────────────────────────
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
        job_early_squareoff_check, "cron", hour=15, minute=18,
        id="early_squareoff_check", replace_existing=True,
    )
    _scheduler.add_job(
        job_squareoff, "cron", hour=15, minute=20,
        id="squareoff", replace_existing=True,
    )
    _scheduler.add_job(
        job_session_end, "cron", hour=15, minute=25,
        id="session_end", replace_existing=True,
    )
    _scheduler.add_job(
        job_reconcile, "interval", minutes=5,
        id="reconcile_orders", replace_existing=True,
    )

    _scheduler.start()
    log.info("scheduler_started", jobs=[j.id for j in _scheduler.get_jobs()])
    
    # ── Initial Engine State Parsing ──────────────────────────────────────────
    log.info("triggering_initial_pre_market_setup", time=now_ist().isoformat())
    await job_pre_market_setup()
    # Note: job_market_open() is specifically scheduled for 09:15 or triggered manually
    
    # ── Background Tasks ──────────────────────────────────────────────────────
    asyncio.create_task(_poll_config())

    # ── Engine Status ─────────────────────────────────────────────────────────
    await _redis_store.set_engine_status({
        "status": "RUNNING" if not settings.is_paper_trade else "RUNNING_PAPER",
        "timestamp": now_ist().isoformat(),
        "paper_trade": settings.is_paper_trade,
        **_coordinator.get_stats(),
    })

    # ── Dashboard: inject redis + db into API router ───────────────────────────
    try:
        from app.api.dashboard_router import set_dependencies as _dash_init
        _dash_init(_redis_store, _db_writer)
        log.info("dashboard_dependencies_injected")
    except Exception as _e:
        log.warning("dashboard_init_failed", error=str(_e))

    # ── Auth router: inject redis for callback token save + reinit trigger ─────
    try:
        from app.api.v1.routes.auth import set_redis as _auth_set_redis
        _auth_set_redis(_redis_store)
        log.info("auth_dependencies_injected")
    except Exception as _e:
        log.warning("auth_init_failed", error=str(_e))

    log.info(
        "engine_running",
        builders=len(_coordinator.candle_builders),
        warmed_up=_coordinator.get_stats()["warmed_up"],
    )

    # ── Signal Handlers ───────────────────────────────────────────────────────
    loop = asyncio.get_event_loop()
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    # ── Main Control Loop ─────────────────────────────────────────────────────
    try:
        while _running:
            await asyncio.sleep(5)

            # Poll Redis for operator control commands
            control = await _redis_store.get_engine_control()
            if control is None:
                continue

            control_str = control.decode() if isinstance(control, bytes) else str(control)

            if control_str == "EMERGENCY_STOP":
                await _emergency_stop()
                break
            elif control_str == "STOP":
                log.info("stop_command_received_graceful_mode")
                # No new entries; existing positions continue to be managed.
                _coordinator.set_new_entries_enabled(False)
                await _redis_store.set_engine_status({
                    "status": "STOPPING",
                    "timestamp": now_ist().isoformat(),
                })
            elif control_str == "START":
                log.info("start_command_received_firing_market_open")
                _coordinator.set_new_entries_enabled(True)
                await job_market_open()
                await _redis_store.set_engine_control("")

    finally:
        await shutdown(loop)


if __name__ == "__main__":
    asyncio.run(main())
