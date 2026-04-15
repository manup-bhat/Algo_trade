"""
app/api/dashboard_router.py — FastAPI WebSocket + REST endpoints for the IVBS dashboard.

WebSocket architecture (3 background tasks):
  heartbeat  — every 5s: full status/positions/radar/scanner snapshot
  tick_batch — every 1s: all livetick:* keys for Universe per-cell updates
  pubsub     — Redis pub/sub: immediately pushes scan_hit/state_change/order_event/pnl_update

REST endpoints:
  GET  /api/v1/status          — engine status, capital, scanner counts
  GET  /api/v1/positions       — active positions
  GET  /api/v1/signals         — recent signals (legacy)
  GET  /api/v1/scanner         — today's scan hits from SQLite + live Redis state
  GET  /api/v1/orders          — today's order events
  GET  /api/v1/trades          — today's closed trades
  GET  /api/v1/market          — live market snapshot
  GET  /api/v1/circuit_breaker — circuit breaker status
    POST /api/v1/stop            — graceful stop (block new entries)
  POST /api/v1/emergency_stop  — halt engine
  POST /api/v1/start           — start scanning
  GET  /api/v1/settings        — get runtime settings
  POST /api/v1/settings        — update runtime settings
  WS   /api/v1/ws              — real-time push feed
"""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime
from typing import Any

import pytz
import structlog
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import create_async_engine

log = structlog.get_logger(__name__)
IST_TZ = pytz.timezone("Asia/Kolkata")

router = APIRouter()

# ── Dependency Registry ────────────────────────────────────────────────────────
_redis_store: Any = None
_db_writer: Any = None


def set_dependencies(redis_store: Any, db_writer: Any | None = None) -> None:
    global _redis_store, _db_writer
    _redis_store = redis_store
    _db_writer = db_writer


_db_engine = None


def _get_db_engine():
    global _db_engine
    if _db_engine is None:
        from app.core.config import settings
        _db_engine = create_async_engine(settings.DATABASE_URL)
    return _db_engine


def _rs() -> Any | None:
    global _redis_store
    if _redis_store is None:
        try:
            from app.store.redis_client import get_redis
            from engine.store.redis_store import RedisStore
            _redis_store = RedisStore(get_redis())
        except Exception as exc:
            log.warning("dashboard_redis_init_failed", error=str(exc))
    return _redis_store


def _is_market_open_now() -> bool:
    from app.core.config import settings

    now_ist = datetime.now(IST_TZ)
    return (
        now_ist.weekday() < 5
        and settings.market_open_time <= now_ist.time() <= settings.square_off_time
    )


# ── WebSocket pool ──────────────────────────────────────────────────────────────
_ws_clients: set[WebSocket] = set()


async def broadcast(payload: dict[str, Any]) -> None:
    msg = json.dumps(payload, default=str)
    dead: set[WebSocket] = set()
    for ws in list(_ws_clients):
        try:
            await ws.send_text(msg)
        except Exception:
            dead.add(ws)
    _ws_clients.difference_update(dead)


# ── /status ─────────────────────────────────────────────────────────────────────

@router.get("/status")
async def get_status():
    from app.core.config import settings
    now_ist = datetime.now(IST_TZ)
    market_open = _is_market_open_now()
    base = {
        "status": "ok",
        "paper_trade": settings.PAPER_TRADE,
        "market_open": market_open,
        "engine_running": False,
        "engine_control": "NOT_STARTED",
        "circuit_breaker_tripped": False,
        "account_equity": 0.0,
        "daily_pnl": 0.0,
        "daily_pnl_pct": 0.0,
        "blocked_margin": 0.0,
        "warmed_up": 0,
        "warming_up": 0,
        "total_ticks": 0,
        "timestamp": now_ist.isoformat(),
    }

    rs = _rs()
    if rs is None:
        return base

    try:
        capital     = await rs.get_capital() or 0.0
        daily_pnl   = await rs.get_daily_pnl() or 0.0
        cb_tripped  = await rs.is_circuit_breaker_tripped()
        blocked     = await rs.get_blocked_margin() or 0.0
        control     = await rs.get_engine_control() or "RUN"
        eng_status  = await rs.get_engine_status() or {}
        if isinstance(control, bytes):
            control = control.decode()

        warmed_raw  = await rs._r.get("engine:scanner:ready_count")
        warming_raw = await rs._r.get("engine:scanner:warming_count")
        warmed_up   = int(warmed_raw)  if warmed_raw  else 0
        warming_up  = int(warming_raw) if warming_raw else 0

        # Paper trade override from Redis (runtime toggle)
        pt_override = await rs.get_paper_trade_override()
        paper_trade = pt_override if pt_override is not None else settings.PAPER_TRADE

        return {
            **base,
            "paper_trade": paper_trade,
            "engine_running": True,
            "engine_control": control,
            "engine_status_msg": eng_status.get("status", "ONLINE"),
            "total_ticks": eng_status.get("total_ticks", 0),
            "circuit_breaker_tripped": cb_tripped,
            "account_equity": capital,
            "daily_pnl": daily_pnl,
            "daily_pnl_pct": round(daily_pnl / capital * 100, 3) if capital else 0.0,
            "blocked_margin": blocked,
            "warmed_up": warmed_up,
            "warming_up": warming_up,
        }
    except Exception as exc:
        log.error("dashboard_status_error", error=str(exc))
        return {**base, "error": str(exc)}


# ── /positions ──────────────────────────────────────────────────────────────────

@router.get("/positions")
async def get_positions():
    rs = _rs()
    if rs is None:
        return {"positions": [], "count": 0, "engine_running": False}
    try:
        states = await rs.get_all_strategy_states() or {}
        positions = []
        for symbol, state_data in states.items():
            if not isinstance(state_data, dict):
                continue

            state = state_data.get("state", "UNKNOWN")
            state_pos = state_data.get("position")
            fallback_pos = await rs.get_position(symbol) or {}
            pos: dict[str, Any] = {}
            if isinstance(fallback_pos, dict):
                pos.update(fallback_pos)
            if isinstance(state_pos, dict):
                for k, v in state_pos.items():
                    if v is not None:
                        pos[k] = v

            # Only show live/active rows (primarily MANAGING), but tolerate
            # transient mismatches by checking for an entry/qty payload.
            if state != "MANAGING" and not pos:
                continue

            entry_price = pos.get("entry_price")
            quantity = pos.get("quantity")
            current_sl = pos.get("current_sl")
            target_1r2 = pos.get("target_1r2")
            target_1r4 = pos.get("target_1r4")
            cost_trailed = pos.get("cost_trailed", False)
            profit_locked = pos.get("profit_locked", False)
            unrealized = pos.get("unrealized_pnl")

            # Fallback unrealized if the position key hasn't been updated yet.
            if unrealized is None and entry_price and quantity:
                ltp = await rs.get_last_ltp(symbol)
                if ltp is not None:
                    unrealized = round((ltp - float(entry_price)) * int(quantity), 2)
                else:
                    unrealized = 0.0

            positions.append({
                "symbol":         symbol,
                "state":          state,
                "entry_price":    entry_price,
                "quantity":       quantity,
                "current_sl":     current_sl,
                "unrealized_pnl": unrealized if unrealized is not None else 0.0,
                "target_1r2":     target_1r2,
                "target_1r4":     target_1r4,
                "cost_trailed":   cost_trailed,
                "profit_locked":  profit_locked,
            })
        return {"positions": positions, "count": len(positions), "engine_running": True}
    except Exception as exc:
        log.error("dashboard_positions_error", error=str(exc))
        return {"positions": [], "count": 0, "error": str(exc)}


# ── /signals (legacy) ───────────────────────────────────────────────────────────

@router.get("/signals")
async def get_signals():
    try:
        from sqlalchemy import text
        engine = _get_db_engine()
        async with engine.connect() as conn:
            result = await conn.execute(text(
                "SELECT symbol, signal_time AS candle_time, "
                "  volume_spike_multiple AS spike_multiple, "
                "  impact_candle_close AS entry_price, created_at "
                "FROM signals ORDER BY created_at DESC LIMIT 50"
            ))
            rows = [dict(r._mapping) for r in result]
        return {"signals": rows, "count": len(rows)}
    except Exception as exc:
        log.debug("dashboard_signals_not_available", error=str(exc))
        return {"signals": [], "count": 0}


# ── /scanner ─────────────────────────────────────────────────────────────────────

@router.get("/scanner")
async def get_scanner():
    from sqlalchemy import text
    rs = _rs()
    today = date.today().isoformat()
    rows = []

    try:
        engine = _get_db_engine()
        async with engine.connect() as conn:
            result = await conn.execute(text(
                "SELECT symbol, signal_time, "
                "  volume_spike_multiple AS spike_multiple, "
                "  impact_candle_close AS close, "
                "  impact_candle_volume AS volume, "
                "  impact_candle_turnover AS turnover_raw, "
                "  impact_candle_high AS impact_high, "
                "  impact_candle_low AS impact_low, "
                "  progressed_to_monitor, abandonment_reason, created_at "
                "FROM signals "
                "WHERE date(signal_time) = :today "
                "ORDER BY signal_time DESC LIMIT 100"
            ), {"today": today})
            rows = [dict(r._mapping) for r in result]
    except Exception as exc:
        log.debug("scanner_db_query_failed", error=str(exc))

    if rs:
        try:
            states = await rs.get_all_strategy_states() or {}
            for row in rows:
                sym = row["symbol"]
                state_data = states.get(sym, {})
                row["state"] = state_data.get("state", "CLOSED")
                tr = row.get("turnover_raw") or 0
                row["turnover_cr"] = round(tr / 1e7, 2) if tr else 0.0
        except Exception as exc:
            log.debug("scanner_state_enrich_failed", error=str(exc))

    for row in rows:
        if "state" not in row:
            if row.get("abandonment_reason"):
                row["state"] = "ABANDONED"
            elif row.get("progressed_to_monitor"):
                row["state"] = "MONITORING"
            else:
                row["state"] = "SCAN_HIT"
        if "turnover_cr" not in row:
            tr = row.get("turnover_raw") or 0
            row["turnover_cr"] = round(tr / 1e7, 2) if tr else 0.0

    return {"hits": rows, "count": len(rows)}


# ── /orders ──────────────────────────────────────────────────────────────────────

@router.get("/orders")
async def get_orders():
    try:
        from sqlalchemy import text
        today = date.today().isoformat()
        engine = _get_db_engine()
        async with engine.connect() as conn:
            result = await conn.execute(text(
                "SELECT order_id, symbol, event_type AS order_type, "
                "  status, average_price AS avg_price, quantity, "
                "  status_message AS reason, event_time AS timestamp "
                "FROM order_events "
                "WHERE date(event_time) = :today "
                "ORDER BY event_time DESC LIMIT 100"
            ), {"today": today})
            rows = [dict(r._mapping) for r in result]
        return {"orders": rows, "count": len(rows)}
    except Exception as exc:
        log.debug("dashboard_orders_not_available", error=str(exc))
        return {"orders": [], "count": 0}


# ── /trades ───────────────────────────────────────────────────────────────────────

@router.get("/trades")
async def get_trades():
    try:
        from sqlalchemy import text
        today = date.today().isoformat()
        engine = _get_db_engine()
        async with engine.connect() as conn:
            result = await conn.execute(text(
                "SELECT symbol, entry_time, entry_price, exit_time, exit_price, "
                "  quantity, gross_pnl, net_pnl, brokerage, stt, other_charges, "
                "  status, notes "
                "FROM trades "
                "WHERE date(entry_time) = :today "
                "ORDER BY exit_time DESC"
            ), {"today": today})
            rows = [dict(r._mapping) for r in result]
        total_net = sum(r.get("net_pnl") or 0 for r in rows)
        wins = sum(1 for r in rows if (r.get("net_pnl") or 0) > 0)
        return {
            "trades": rows, "count": len(rows),
            "total_net_pnl": round(total_net, 2),
            "wins": wins, "losses": len(rows) - wins,
            "win_rate": round(wins / len(rows) * 100, 1) if rows else 0.0,
        }
    except Exception as exc:
        log.debug("dashboard_trades_not_available", error=str(exc))
        return {"trades": [], "count": 0, "total_net_pnl": 0.0,
                "wins": 0, "losses": 0, "win_rate": 0.0}


# ── /circuit_breaker ─────────────────────────────────────────────────────────────

@router.get("/circuit_breaker")
async def get_circuit_breaker():
    from app.core.config import settings
    rs = _rs()
    if rs is None:
        return {"tripped": False, "daily_pnl": 0.0, "loss_limit": 0.0,
                "loss_limit_pct": settings.DAILY_LOSS_LIMIT_PCT,
                "capital": 0.0, "usage_pct": 0.0, "engine_running": False}
    try:
        tripped   = await rs.is_circuit_breaker_tripped()
        capital   = await rs.get_capital() or 0.0
        daily_pnl = await rs.get_daily_pnl() or 0.0
        loss_limit = -(capital * settings.DAILY_LOSS_LIMIT_PCT / 100) if capital else 0.0
        usage_pct = round(abs(daily_pnl / loss_limit * 100), 1) if loss_limit else 0.0
        return {"tripped": tripped, "daily_pnl": daily_pnl, "loss_limit": loss_limit,
                "loss_limit_pct": settings.DAILY_LOSS_LIMIT_PCT, "capital": capital,
                "usage_pct": usage_pct, "engine_running": True}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── /emergency_stop ───────────────────────────────────────────────────────────────

@router.post("/emergency_stop")
async def emergency_stop():
    rs = _rs()
    if rs is None:
        return {"status": "NOT_STARTED", "message": "Engine not running."}
    try:
        await rs.set_engine_control("EMERGENCY_STOP")
        log.critical("emergency_stop_triggered_via_dashboard")
        await broadcast({"event": "emergency_stop",
                         "timestamp": datetime.now(IST_TZ).isoformat()})
        return {
            "status": "EMERGENCY_STOP",
            "message": "Emergency stop sent. Immediate square-off requested.",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/stop")
async def stop_engine():
    """Graceful stop: blocks new entries; existing positions continue managed lifecycle."""
    rs = _rs()
    if rs is None:
        return {"status": "NOT_STARTED", "message": "Engine not running."}
    try:
        await rs.set_engine_control("STOP")
        await broadcast({"event": "stop", "timestamp": datetime.now(IST_TZ).isoformat()})
        return {"status": "STOP", "message": "Graceful stop sent. New entries blocked."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── /start ─────────────────────────────────────────────────────────────────────────

@router.post("/start")
async def start_engine():
    rs = _rs()
    if rs is None:
        return {"status": "NOT_STARTED", "message": "Backend offline."}
    try:
        await rs.set_engine_control("START")
        return {"status": "START", "message": "Engine scan started."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── /settings ───────────────────────────────────────────────────────────────────

class SettingsUpdate(BaseModel):
    paper_trade: bool
    max_capital: float | None = None


@router.get("/settings")
async def get_settings():
    from app.core.config import settings
    rs = _rs()
    if rs is None:
        return {"paper_trade": settings.PAPER_TRADE, "max_capital": None,
                "daily_loss_limit_pct": settings.DAILY_LOSS_LIMIT_PCT}
    try:
        pt_override = await rs.get_paper_trade_override()
        paper_trade = pt_override if pt_override is not None else settings.PAPER_TRADE
        max_capital = await rs.get_max_capital_override()
        return {
            "paper_trade": paper_trade,
            "max_capital": max_capital,
            "daily_loss_limit_pct": settings.DAILY_LOSS_LIMIT_PCT,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/settings")
async def update_settings(payload: SettingsUpdate):
    rs = _rs()
    if rs is None:
        raise HTTPException(status_code=503, detail="Engine not running")
    try:
        await rs.set_paper_trade_override(payload.paper_trade)
        await rs.set_max_capital_override(payload.max_capital)
        await broadcast({"event": "settings_updated",
                         "paper_trade": payload.paper_trade,
                         "max_capital": payload.max_capital,
                         "timestamp": datetime.now(IST_TZ).isoformat()})
        return {"status": "success", "paper_trade": payload.paper_trade,
                "max_capital": payload.max_capital}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── /market ───────────────────────────────────────────────────────────────────────

@router.get("/market")
async def get_market():
    rs = _rs()
    if rs is None:
        return {"ticks": [], "count": 0}
    try:
        if not _is_market_open_now():
            snapshot_ticks = await rs.load_eod_market_snapshot(limit=500)
            if snapshot_ticks:
                return {
                    "ticks": snapshot_ticks,
                    "count": len(snapshot_ticks),
                    "source": "eod_snapshot",
                }

        ticks = await rs.get_market_snapshot(limit=500)
        return {
            "ticks": ticks,
            "count": len(ticks),
            "source": "live_ticks",
        }
    except Exception as exc:
        return {"ticks": [], "count": 0, "error": str(exc)}


# ── Radar helper ────────────────────────────────────────────────────────────────

async def _get_radar_data():
    rs = _rs()
    if rs is None:
        return []
    try:
        states = await rs.get_all_strategy_states()
        radar = []
        for symbol, state_data in (states or {}).items():
            state = state_data.get("state")
            if state in ("SCAN_HIT", "MONITORING", "ACTION_PENDING"):
                impact = state_data.get("impact_candle") or {}
                consolidation = state_data.get("consolidation") or {}
                impact_time = state_data.get("impact_candle_time") or impact.get("time")
                impact_close = state_data.get("impact_close") or impact.get("close")
                spike_multiple = state_data.get("spike_multiple") or impact.get("spike_multiple")

                breakout_level = consolidation.get("breakout_trigger_price")
                if breakout_level is None:
                    breakout_level = consolidation.get("high")

                ltp = await rs.get_last_ltp(symbol)
                radar.append({
                    "symbol": symbol,
                    "state": state,
                    "impact_time": impact_time,
                    "impact_close": impact_close,
                    "spike_multiple": spike_multiple,
                    "turnover_cr": impact.get("turnover_cr") or state_data.get("turnover_cr"),
                    "breakout_level": breakout_level,
                    "candle_count": consolidation.get("candle_count", 0),
                    "current_price": ltp,
                })
        return radar
    except Exception as exc:
        log.error("dashboard_radar_error", error=str(exc))
        return []


# ── WebSocket /ws ─────────────────────────────────────────────────────────────────

@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """
    Real-time dashboard feed.

    Three background tasks are created and cancelled cleanly when client disconnects.
    Main coroutine blocks on receive_text(); WebSocketDisconnect triggers cleanup.
    """
    await ws.accept()
    _ws_clients.add(ws)
    log.info("dashboard_ws_connected", total=len(_ws_clients))

    async def _send(payload: dict) -> None:
        await ws.send_text(json.dumps(payload, default=str))

    async def _heartbeat_loop():
        # Send snapshot immediately on connect
        try:
            sd = await get_status()
            pd = await get_positions()
            rd = await _get_radar_data()
            sc = await get_scanner()
            mk = await get_market()
            await _send({
                "event": "snapshot",
                "status": sd,
                "positions": pd["positions"],
                "radar": rd,
                "scanner": sc["hits"],
                "market": mk["ticks"],
            })
        except asyncio.CancelledError:
            return
        except Exception as exc:
            log.debug("ws_snapshot_error", error=str(exc))

        while True:
            try:
                await asyncio.sleep(5)
                sd = await get_status()
                pd = await get_positions()
                rd = await _get_radar_data()
                sc = await get_scanner()
                await _send({
                    "event": "heartbeat",
                    "status": sd,
                    "positions": pd["positions"],
                    "radar": rd,
                    "scanner": sc["hits"],
                })
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.debug("ws_heartbeat_error", error=str(exc))

    async def _tick_batch_loop():
        rs = _rs()
        if rs is None:
            return
        while True:
            try:
                await asyncio.sleep(1)
                ticks = await rs.get_all_live_ticks()
                if ticks:
                    await _send({"event": "tick_batch", "data": ticks})
            except asyncio.CancelledError:
                break
            except Exception:
                pass  # Redis blip — skip tick batch

    async def _pubsub_loop():
        r = None
        pubsub = None
        try:
            from app.store.redis_client import get_redis
            r = get_redis()
            pubsub = r.pubsub()
            await pubsub.subscribe(
                "pub:signals", "pub:state_changes", "pub:orders", "pub:pnl"
            )
            evt_map = {
                "pub:signals":       "scan_hit",
                "pub:state_changes": "state_change",
                "pub:orders":        "order_event",
                "pub:pnl":           "pnl_update",
            }
            async for msg in pubsub.listen():
                ch = msg.get("channel", b"")
                if isinstance(ch, bytes):
                    ch = ch.decode()
                if msg.get("type") != "message":
                    continue
                try:
                    data = json.loads(msg["data"])
                except Exception:
                    continue
                try:
                    await _send({"event": evt_map.get(ch, "engine_event"), "data": data})
                except Exception:
                    break
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            log.debug("ws_pubsub_error", error=str(exc))
        finally:
            try:
                if pubsub:
                    await pubsub.unsubscribe()
                if r:
                    await r.aclose()
            except Exception:
                pass

    t1 = asyncio.create_task(_heartbeat_loop(),  name="ws_heartbeat")
    t2 = asyncio.create_task(_tick_batch_loop(), name="ws_ticks")
    t3 = asyncio.create_task(_pubsub_loop(),     name="ws_pubsub")

    try:
        # Block until client disconnects
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        log.debug("ws_receive_ended", error=str(exc))
    finally:
        t1.cancel()
        t2.cancel()
        t3.cancel()
        await asyncio.gather(t1, t2, t3, return_exceptions=True)
        _ws_clients.discard(ws)
        log.info("dashboard_ws_disconnected", remaining=len(_ws_clients))
