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
from datetime import datetime, timedelta, timezone
from pathlib import Path
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


def _today_ist() -> str:
    return datetime.now(IST_TZ).date().isoformat()


def _is_recent_status(status_payload: dict[str, Any], max_age_seconds: int = 30) -> bool:
    raw_ts = status_payload.get("timestamp")
    if not raw_ts:
        return False
    try:
        parsed = datetime.fromisoformat(str(raw_ts))
        if parsed.tzinfo is None:
            parsed = IST_TZ.localize(parsed)
        return (
            datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)
        ) <= timedelta(seconds=max_age_seconds)
    except Exception:
        return False


def _state_phase(state: str | None) -> str:
    normalized = (state or "SCAN_HIT").upper()
    if normalized in {"ENTERED", "ACTION_PENDING", "PENDING"}:
        return "ENTRY"
    if normalized in {"MANAGING"}:
        return "MANAGING"
    if normalized in {"MONITORING"}:
        return "MONITORING"
    if normalized in {"ABANDONED"}:
        return "ABANDONED"
    if normalized in {"CLOSED", "CLOSED_TARGET", "CLOSED_STOPLOSS", "CLOSED_TRAILSTOP", "CLOSED_TIME"}:
        return "CLOSED"
    return "SCAN_HIT"


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
        "total_builders": 0,
        "total_ticks": 0,
        "total_candles": 0,
        "active_state_machines": 0,
        "runner_heartbeat": None,
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
        heartbeat   = await rs.get_runner_heartbeat()
        if isinstance(control, bytes):
            control = control.decode()

        warmed_raw  = await rs._r.get("engine:scanner:ready_count")
        warming_raw = await rs._r.get("engine:scanner:warming_count")
        warmed_up   = int(warmed_raw)  if warmed_raw  else 0
        warming_up  = int(warming_raw) if warming_raw else 0

        # Paper trade override from Redis (runtime toggle)
        pt_override = await rs.get_paper_trade_override()
        max_capital_override = await rs.get_max_capital_override()
        paper_trade = pt_override if pt_override is not None else settings.PAPER_TRADE
        status_name = str(eng_status.get("status", "OFFLINE")).upper()
        engine_running = bool(heartbeat) or (
            status_name not in {"", "OFFLINE", "EMERGENCY_STOP"}
            and _is_recent_status(eng_status)
        )

        return {
            **base,
            "paper_trade": paper_trade,
            "engine_running": engine_running,
            "engine_control": control,
            "engine_status_msg": eng_status.get("status", "ONLINE" if engine_running else "OFFLINE"),
            "total_ticks": eng_status.get("total_ticks", 0),
            "total_candles": eng_status.get("total_candles", 0),
            "total_builders": eng_status.get("total_builders", 0),
            "active_state_machines": eng_status.get("active_state_machines", 0),
            "circuit_breaker_tripped": cb_tripped,
            "account_equity": capital,
            "daily_pnl": daily_pnl,
            "daily_pnl_pct": round(daily_pnl / capital * 100, 3) if capital else 0.0,
            "blocked_margin": blocked,
            "warmed_up": warmed_up,
            "warming_up": warming_up,
            "max_capital": max_capital_override,
            "runner_heartbeat": heartbeat,
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
            initial_sl = pos.get("initial_sl") or pos.get("initial_stop_loss")
            risk_per_share = pos.get("risk_per_share")
            risk_amount = pos.get("risk_amount")
            target_1r2 = pos.get("target_1r2")
            target_1r3 = pos.get("target_1r3")
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
                "initial_sl":     initial_sl,
                "current_sl":     current_sl,
                "risk_per_share": risk_per_share,
                "risk_amount":    risk_amount,
                "unrealized_pnl": unrealized if unrealized is not None else 0.0,
                "target_1r2":     target_1r2,
                "target_1r3":     target_1r3,
                "target_1r4":     target_1r4,
                "cost_trailed":   cost_trailed,
                "profit_locked":  profit_locked,
                "entry_time":     pos.get("entry_time"),
                "sl_order_id":    pos.get("sl_order_id"),
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
    today = _today_ist()
    rows = []

    try:
        engine = _get_db_engine()
        async with engine.connect() as conn:
            result = await conn.execute(text(
                "SELECT symbol, signal_time, "
                "  impact_candle_open AS open, "
                "  volume_spike_multiple AS spike_multiple, "
                "  impact_candle_close AS close, "
                "  impact_candle_volume AS volume, "
                "  impact_candle_turnover AS turnover_raw, "
                "  impact_candle_high AS impact_high, "
                "  impact_candle_low AS impact_low, "
                "  progressed_to_monitor, progressed_to_action, resulted_in_trade, "
                "  abandonment_reason, created_at "
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
        if row.get("open") and row.get("close"):
            row["change_pct"] = round(
                (float(row["close"]) - float(row["open"])) / float(row["open"]) * 100,
                2,
            )

    return {"hits": rows, "count": len(rows)}


# ── /orders ──────────────────────────────────────────────────────────────────────

@router.get("/orders")
async def get_orders():
    try:
        from sqlalchemy import text
        today = _today_ist()
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
        today = _today_ist()
        engine = _get_db_engine()
        async with engine.connect() as conn:
            result = await conn.execute(text(
                "SELECT symbol, entry_time, entry_price, exit_time, exit_price, "
                "  quantity, initial_stop_loss, current_stop_loss, risk_per_share, "
                "  risk_amount, target_1r2, target_1r4, gross_pnl, net_pnl, "
                "  brokerage, stt, other_charges, cost_trailed, profit_locked, "
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
    paper_trade: bool | None = None
    max_capital: float | None = None
    config: dict[str, Any] | None = None
    reload_engine: bool = True


_SECRET_SETTING_KEYS = {"KITE_API_KEY", "KITE_API_SECRET"}

_SETTING_GROUPS: dict[str, list[str]] = {
    "Kite Credentials": [
        "KITE_API_KEY", "KITE_API_SECRET", "KITE_REDIRECT_URL", "KITE_TOKEN_PATH",
    ],
    "Infrastructure": ["REDIS_URL", "DATABASE_URL", "UNIVERSE_FILE"],
    "Scanner Filters": [
        "VOLUME_SPIKE_MULTIPLE", "VOLUME_SMA_PERIOD", "HISTORICAL_WARMUP_ENABLED",
        "HISTORICAL_WARMUP_TRADING_DAYS", "HISTORICAL_WARMUP_CONCURRENCY",
        "HISTORICAL_WARMUP_BATCH_DELAY_SEC", "HISTORICAL_WARMUP_RECENT_CANDLES",
        "MIN_TURNOVER_CRORE", "MIN_PRICE", "MAX_PRICE", "REIGNITION_VOLUME_MULTIPLE",
        "REIGNITION_LOOKBACK_CANDLES", "MIN_DRYUP_CANDLES",
        "ASHAPE_RED_CANDLE_PCT", "ASHAPE_VOLUME_MULTIPLE", "ASHAPE_MIN_CANDLE_COUNT",
    ],
    "Risk Controls": [
        "RISK_PER_TRADE_PCT", "MAX_CONCURRENT_POSITIONS", "DAILY_LOSS_LIMIT_PCT",
        "MIN_RISK_PER_SHARE_INR", "PEAK_MARGIN_SAFETY_BUFFER_PCT",
    ],
    "Regulatory Values": [
        "STT_INTRADAY_SELL_PCT", "NSE_TXFEE_PER_LAKH_INR",
        "SEBI_TXFEE_PER_CRORE_INR", "GST_ON_BROKERAGE_PCT", "STAMP_DUTY_BUY_PCT",
    ],
    "Broker API": [
        "BROKERAGE_PER_ORDER_INR", "ORDER_MAX_RETRIES", "ORDER_RETRY_BASE_DELAY_SEC",
        "WS_MAX_RECONNECT_ATTEMPTS", "WS_RECONNECT_DELAY_SEC",
        "MAX_WS_INSTRUMENTS", "EXIT_SL_CANCEL_DELAY_MS",
    ],
    "Strategy Calibration": [
        "DRYUP_MAX_MINUTES", "MAX_ENTRY_TIME", "ENTRY_BUFFER_PCT",
        "ENTRY_WIDEN_AFTER_SECONDS", "ENTRY_ABANDON_PCT", "ORDER_FILL_TIMEOUT_SECONDS",
    ],
    "Market Structure": [
        "MARKET_OPEN_TIME", "SQUARE_OFF_TIME", "MASS_SQUAREOFF_START_TIME",
        "SESSION_END_TIME",
    ],
    "Server Operations": [
        "API_HOST", "API_PORT", "DEBUG", "LOG_LEVEL",
        "AUTO_START_ENGINE_WITH_BACKEND", "AUTO_STOP_ENGINE_WITH_BACKEND",
        "ENGINE_RUNNER_CMD", "DASHBOARD_TICK_FLUSH_INTERVAL_MS",
        "DASHBOARD_WS_TICK_INTERVAL_MS", "DASHBOARD_WS_HEARTBEAT_INTERVAL_MS",
    ],
}

_SETTING_WARNINGS = {
    "STT_INTRADAY_SELL_PCT": "review after Union Budget",
    "NSE_TXFEE_PER_LAKH_INR": "review annually",
    "SEBI_TXFEE_PER_CRORE_INR": "review annually",
    "GST_ON_BROKERAGE_PCT": "review after Union Budget",
    "STAMP_DUTY_BUY_PCT": "review after Union Budget",
    "BROKERAGE_PER_ORDER_INR": "review if brokerage plan changes",
}

_SETTING_DESCRIPTIONS = {
    "UNIVERSE_FILE": "Universe source file loaded before Kite instrument filtering.",
    "VOLUME_SPIKE_MULTIPLE": "Minimum volume multiple versus 500-period SMA for scan hits.",
    "HISTORICAL_WARMUP_ENABLED": "Use Kite historical minute candles to pre-warm SMA builders before scanning.",
    "HISTORICAL_WARMUP_TRADING_DAYS": "Trading sessions requested from Kite for warmup history.",
    "HISTORICAL_WARMUP_CONCURRENCY": "Parallel Kite historical requests during warmup.",
    "HISTORICAL_WARMUP_BATCH_DELAY_SEC": "Pause between warmup request batches to avoid broker throttling.",
    "HISTORICAL_WARMUP_RECENT_CANDLES": "Historical candles stored per symbol for dashboard charts.",
    "MIN_TURNOVER_CRORE": "Minimum one-minute turnover in crore required for scan hits.",
    "RISK_PER_TRADE_PCT": "Capital risked per accepted trade.",
    "MAX_CONCURRENT_POSITIONS": "Maximum simultaneous live positions.",
    "DAILY_LOSS_LIMIT_PCT": "Circuit breaker loss threshold as percent of capital.",
    "DRYUP_MAX_MINUTES": "Maximum time a setup can remain in dry-up validation.",
    "ORDER_FILL_TIMEOUT_SECONDS": "Entry order timeout before reverting to monitoring.",
    "AUTO_START_ENGINE_WITH_BACKEND": "Start engine.runner automatically with FastAPI.",
    "DASHBOARD_TICK_FLUSH_INTERVAL_MS": "Minimum interval for persisting live ticks to Redis.",
    "DASHBOARD_WS_TICK_INTERVAL_MS": "WebSocket interval for live market tick batches.",
    "DASHBOARD_WS_HEARTBEAT_INTERVAL_MS": "WebSocket interval for status, positions, and scanner snapshots.",
}


def _setting_kind(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int) and not isinstance(value, bool):
        return "int"
    if isinstance(value, float):
        return "float"
    return "str"


def _coerce_setting_value(current: Any, raw: Any) -> Any:
    if isinstance(current, bool):
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(current, int) and not isinstance(current, bool):
        return int(raw)
    if isinstance(current, float):
        return float(raw)
    return str(raw)


def _env_format(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _write_env_updates(updates: dict[str, Any]) -> None:
    env_path = Path(".env")
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    remaining = dict(updates)
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            out.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in remaining:
            out.append(f"{key}={_env_format(remaining.pop(key))}")
        else:
            out.append(line)
    for key, value in remaining.items():
        out.append(f"{key}={_env_format(value)}")
    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")


def _settings_payload(settings: Any) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    all_fields = type(settings).model_fields
    for group_name, keys in _SETTING_GROUPS.items():
        fields = []
        for key in keys:
            if key not in all_fields:
                continue
            value = getattr(settings, key)
            secret = key in _SECRET_SETTING_KEYS
            fields.append({
                "key": key,
                "value": "********" if secret else value,
                "kind": _setting_kind(value),
                "editable": not secret,
                "description": _SETTING_DESCRIPTIONS.get(key, ""),
                "warning": _SETTING_WARNINGS.get(key),
            })
        groups.append({"name": group_name, "fields": fields})
    return groups


@router.get("/settings")
async def get_settings():
    from app.core.config import settings
    rs = _rs()
    max_capital = None
    try:
        if rs is not None:
            pt_override = await rs.get_paper_trade_override()
            max_capital = await rs.get_max_capital_override()
        else:
            pt_override = None
    except Exception:
        pt_override = None

    paper_trade = pt_override if pt_override is not None else settings.PAPER_TRADE
    return {
        "paper_trade": paper_trade,
        "max_capital": max_capital,
        "daily_loss_limit_pct": settings.DAILY_LOSS_LIMIT_PCT,
        "groups": _settings_payload(settings),
    }


@router.post("/settings")
async def update_settings(payload: SettingsUpdate):
    from app.core.config import Settings, settings

    rs = _rs()
    try:
        updates: dict[str, Any] = {}
        if payload.config:
            all_fields = type(settings).model_fields
            for key, raw_value in payload.config.items():
                if key not in all_fields:
                    raise HTTPException(status_code=400, detail=f"Unknown setting: {key}")
                if key in _SECRET_SETTING_KEYS:
                    raise HTTPException(status_code=400, detail=f"{key} is read-only")
                updates[key] = _coerce_setting_value(getattr(settings, key), raw_value)

            candidate = {
                key: getattr(settings, key)
                for key in type(settings).model_fields
            }
            candidate.update(updates)
            Settings.model_validate(candidate)
            _write_env_updates(updates)
            for key, value in updates.items():
                setattr(settings, key, value)

        if rs is not None:
            if payload.paper_trade is not None:
                await rs.set_paper_trade_override(payload.paper_trade)
                settings.PAPER_TRADE = payload.paper_trade
            if "max_capital" in payload.model_fields_set:
                await rs.set_max_capital_override(payload.max_capital)
            if payload.reload_engine:
                await rs.set_reinit_trigger()

        await broadcast({
            "event": "settings_updated",
            "paper_trade": payload.paper_trade,
            "max_capital": payload.max_capital,
            "updated_keys": sorted(updates.keys()),
            "timestamp": datetime.now(IST_TZ).isoformat(),
        })
        return {
            "status": "success",
            "paper_trade": payload.paper_trade,
            "max_capital": payload.max_capital,
            "updated_keys": sorted(updates.keys()),
            "reload_engine": payload.reload_engine,
        }
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise exc
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


# ── /universe ───────────────────────────────────────────────────────────────────

# Cache universe symbols in memory: reading 500 lines from disk on every API
# call (every ~3 seconds) is wasteful and floods the log with universe_loaded_raw.
_universe_cache: list[str] = []
_universe_cache_ts: float = 0.0
_UNIVERSE_CACHE_TTL = 30.0  # seconds


def _get_cached_universe() -> list[str]:
    """Return universe symbols from memory cache (refreshed every 30 seconds)."""
    import time as _time
    global _universe_cache, _universe_cache_ts
    if not _universe_cache or (_time.monotonic() - _universe_cache_ts) > _UNIVERSE_CACHE_TTL:
        from engine.market.universe import load_universe
        _universe_cache = load_universe()
        _universe_cache_ts = _time.monotonic()
    return _universe_cache


@router.get("/universe")
async def get_universe():
    """Universe file + live tick enrichment. Never fabricates prices."""
    from app.core.config import settings

    symbols = _get_cached_universe()
    rs = _rs()
    ticks_by_symbol: dict[str, Any] = {}
    states: dict[str, Any] = {}
    token_values: list[Any] = []
    tick_size_values: list[Any] = []

    if rs is not None:
        try:
            ticks_by_symbol = await rs.get_all_live_ticks()
            states = await rs.get_all_strategy_states() or {}
            if symbols:
                token_values = await rs._r.mget([f"token:{s}" for s in symbols])
                tick_size_values = await rs._r.mget([f"tick_size:{s}" for s in symbols])
        except Exception as exc:
            log.debug("universe_enrichment_failed", error=str(exc))

    rows = []
    for idx, symbol in enumerate(symbols):
        tick = ticks_by_symbol.get(symbol) or {}
        state_data = states.get(symbol) or {}
        token_raw = token_values[idx] if idx < len(token_values) else None
        tick_size_raw = tick_size_values[idx] if idx < len(tick_size_values) else None
        rows.append({
            "symbol": symbol,
            "ltp": tick.get("ltp"),
            "open": tick.get("open"),
            "prev_close": tick.get("prev_close"),
            "pct_chg": tick.get("pct_chg"),
            "volume": tick.get("volume"),
            "minute_volume": tick.get("minute_volume"),
            "volume_sma_500": tick.get("volume_sma_500"),
            "relative_volume": tick.get("relative_volume"),
            "has_tick": bool(tick),
            "state": state_data.get("state", "IDLE"),
            "instrument_token": int(token_raw) if token_raw else None,
            "tick_size": float(tick_size_raw) if tick_size_raw else None,
        })

    return {
        "symbols": rows,
        "count": len(rows),
        "tick_count": len(ticks_by_symbol),
        "source_file": settings.UNIVERSE_FILE,
        "source": "universe_file_with_live_ticks" if ticks_by_symbol else "universe_file",
    }


# ── /universe/symbols — POST (add) ──────────────────────────────────────────────

class UniverseSymbolsPayload(BaseModel):
    symbols: list[str]


@router.post("/universe/symbols")
async def add_universe_symbols(payload: UniverseSymbolsPayload):
    """
    Add one or more NSE symbols to the universe watchlist.

    Flow:
      1. Validate symbols against the in-process InstrumentCache.
      2. Append valid symbols to universe.txt (deduplicating).
      3. Invalidate the in-memory universe cache so the next /universe call
         returns the updated list.
      4. Re-subscribe on the live Kite WebSocket ticker if the engine is running.
      5. Trigger a coordinator reinit so candle builders are created for new symbols.
      6. Kick off historical SMA warmup for new symbols (background task).
    """
    from app.core.config import settings
    from engine.kite.instruments import instrument_cache
    from engine.market.universe import load_universe

    if not payload.symbols:
        raise HTTPException(status_code=400, detail="No symbols provided")

    requested = [s.upper().strip() for s in payload.symbols if s.strip()]
    if not requested:
        raise HTTPException(status_code=400, detail="No valid symbols provided")

    # ── 1. Validate each symbol against instrument cache ────────────────────
    added: list[str] = []
    errors: list[str] = []
    new_tokens: list[int] = []

    existing = set(_get_cached_universe())
    instruments = await _load_instrument_search_cache()
    instr_map = {item.get("symbol", ""): item for item in instruments}

    for sym in requested:
        if sym in existing:
            errors.append(f"{sym}: already in watchlist")
            continue
        info = instr_map.get(sym)
        if info is None:
            errors.append(f"{sym}: not found in NSE instrument list (engine may not be loaded yet)")
            continue
        added.append(sym)
        new_tokens.append(info.get("instrument_token"))

    if not added:
        return {"added": [], "errors": errors, "message": "No new symbols to add"}

    # ── 2. Append to universe file ───────────────────────────────────────────
    try:
        universe_path = Path(settings.UNIVERSE_FILE)
        if not universe_path.is_absolute():
            universe_path = Path(__file__).resolve().parents[2] / universe_path
        with open(universe_path, "a", encoding="utf-8") as f:
            for sym in added:
                f.write(f"\n{sym}")
        log.info("universe_symbols_added", symbols=added, file=str(universe_path))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to write universe file: {exc}")

    # ── 3. Invalidate the in-memory universe cache ───────────────────────────
    global _universe_cache, _universe_cache_ts
    _universe_cache = []
    _universe_cache_ts = 0.0

    # ── 4. Subscribe new tokens on live Kite WebSocket (if engine is running) ─
    try:
        from engine import runner as _runner
        ticker = getattr(_runner, "_ticker", None)
        coordinator = getattr(_runner, "_coordinator", None)

        if ticker is not None and coordinator is not None and new_tokens:
            # Subscribe new tokens in QUOTE mode (same as universe stocks)
            ticker.subscribe(new_tokens)
            ticker.set_mode("quote", new_tokens)
            # Also register in coordinator's token maps so ticks are routed
            from engine.market.candle_builder import CandleBuilder
            from app.core.config import settings as _s
            for sym in added:
                info = instr_map.get(sym)
                if info is None:
                    continue
                coordinator.token_to_symbol[info.get("instrument_token")] = sym
                coordinator.symbol_to_token[sym] = info.get("instrument_token")
                if sym not in coordinator.candle_builders:
                    coordinator.candle_builders[sym] = CandleBuilder(sym, _s.VOLUME_SMA_PERIOD)
            log.info("universe_symbols_subscribed", symbols=added, tokens=new_tokens)
    except Exception as exc:
        log.warning("universe_subscribe_failed", error=str(exc))
        errors.append(f"WS subscription failed: {exc} (symbols still saved to file)")

    # ── 5. Store token + tick_size in Redis for new symbols ──────────────────
    rs = _rs()
    if rs is not None:
        try:
            for sym in added:
                info = instr_map.get(sym)
                if info:
                    await rs.set_tick_size(sym, info.get("tick_size", 0.05))
                    await rs.set_instrument_token(sym, info.get("instrument_token"))
        except Exception as exc:
            log.warning("universe_redis_update_failed", error=str(exc))

    # ── 6. Kick off SMA warmup in background for new symbols ─────────────────
    try:
        from engine import runner as _runner
        kite_client = getattr(_runner, "_kite_client", None)
        coordinator = getattr(_runner, "_coordinator", None)
        redis_store = getattr(_runner, "_redis_store", None)
        if kite_client is not None and coordinator is not None and redis_store is not None and added:
            from engine.market.historical_warmup import warmup_from_historical
            asyncio.create_task(
                warmup_from_historical(
                    coordinator, kite_client, redis_store=redis_store, symbols_subset=added
                ),
                name=f"sma_warmup_new_symbols",
            )
            log.info("universe_sma_warmup_triggered", symbols=added)
    except Exception as exc:
        log.debug("universe_warmup_trigger_failed", error=str(exc))

    await broadcast({
        "event": "universe_updated",
        "added": added,
        "removed": [],
        "timestamp": datetime.now(IST_TZ).isoformat(),
    })

    return {
        "added": added,
        "errors": errors,
        "new_tokens": new_tokens,
        "message": f"{len(added)} symbol(s) added to universe",
    }


@router.delete("/universe/symbols")
async def remove_universe_symbols(payload: UniverseSymbolsPayload):
    """
    Remove one or more symbols from the universe watchlist.

    Flow:
      1. Rewrite universe.txt excluding the requested symbols.
      2. Invalidate in-memory cache.
      3. Unsubscribe tokens from Kite WebSocket (if engine running and no active SM).
      4. Broadcast universe_updated event.
    """
    from app.core.config import settings
    from engine.kite.instruments import instrument_cache

    if not payload.symbols:
        raise HTTPException(status_code=400, detail="No symbols provided")

    to_remove = {s.upper().strip() for s in payload.symbols if s.strip()}

    # ── 1. Rewrite universe file without removed symbols ─────────────────────
    try:
        universe_path = Path(settings.UNIVERSE_FILE)
        if not universe_path.is_absolute():
            universe_path = Path(__file__).resolve().parents[2] / universe_path

        existing_lines: list[str] = []
        removed_from_file: list[str] = []
        if universe_path.exists():
            with open(universe_path, encoding="utf-8") as f:
                for raw_line in f:
                    line = raw_line.rstrip("\n")
                    stripped = line.strip()
                    # Preserve blank lines and comments
                    if not stripped or stripped.startswith("#"):
                        existing_lines.append(line)
                        continue
                    sym = stripped.upper().removeprefix("NSE:").removesuffix(".NS").strip()
                    if sym in to_remove:
                        removed_from_file.append(sym)
                        continue
                    existing_lines.append(line)
        with open(universe_path, "w", encoding="utf-8") as f:
            f.write("\n".join(existing_lines))
            if existing_lines and not existing_lines[-1].endswith("\n"):
                f.write("\n")
        log.info("universe_symbols_removed", symbols=removed_from_file)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to rewrite universe file: {exc}")

    # ── 2. Invalidate in-memory cache ────────────────────────────────────────
    global _universe_cache, _universe_cache_ts
    _universe_cache = []
    _universe_cache_ts = 0.0

    # ── 3. Unsubscribe from Kite WS (only if symbol has no active state machine) ──
    tokens_to_unsub: list[int] = []
    try:
        from engine import runner as _runner
        ticker = getattr(_runner, "_ticker", None)
        coordinator = getattr(_runner, "_coordinator", None)

        if ticker is not None and coordinator is not None:
            instruments = await _load_instrument_search_cache()
            instr_map = {item.get("symbol", ""): item for item in instruments}

            for sym in removed_from_file:
                # Never unsubscribe a symbol with an active state machine
                if sym in coordinator.active_state_machines:
                    log.info("universe_remove_skipped_active_sm", symbol=sym)
                    continue
                info = instr_map.get(sym)
                if info:
                    tokens_to_unsub.append(info.get("instrument_token"))
                # Remove from coordinator maps
                coordinator.token_to_symbol.pop(info.get("instrument_token") if info else 0, None)
                coordinator.symbol_to_token.pop(sym, None)
                coordinator.candle_builders.pop(sym, None)

            if tokens_to_unsub:
                ticker.unsubscribe(tokens_to_unsub)
                log.info("universe_symbols_unsubscribed", tokens=tokens_to_unsub)
    except Exception as exc:
        log.warning("universe_unsubscribe_failed", error=str(exc))

    await broadcast({
        "event": "universe_updated",
        "added": [],
        "removed": removed_from_file,
        "timestamp": datetime.now(IST_TZ).isoformat(),
    })

    return {
        "removed": removed_from_file,
        "unsubscribed_tokens": tokens_to_unsub,
        "message": f"{len(removed_from_file)} symbol(s) removed from universe",
    }


# ── /instruments/search ──────────────────────────────────────────────────────────

# In-memory cache for the full NSE instrument list (for fast fuzzy search)
# Populated from Redis key "instruments:nse:eq" written by the engine runner.
_instrument_search_cache: list[dict] = []
_instrument_search_cache_ts: float = 0.0
_INSTRUMENT_SEARCH_TTL = 60.0   # 60s in-memory TTL — avoid Redis round-trip on every keystroke
_REDIS_INSTRUMENT_KEY = "instruments:nse:eq"


async def _load_instrument_search_cache() -> list[dict]:
    """
    Load and cache NSE EQ instrument list from Redis.

    The engine runner stores 'instruments:nse:eq' (JSON array) in Redis when it
    authenticates with Kite during pre-market setup. This endpoint reads that key
    so the FastAPI process never needs to call Kite directly.

    Returns [] if Redis key is missing (engine not yet authenticated).
    """
    import time as _time
    global _instrument_search_cache, _instrument_search_cache_ts

    now = _time.monotonic()
    # Return in-memory copy if fresh
    if _instrument_search_cache and (now - _instrument_search_cache_ts) < _INSTRUMENT_SEARCH_TTL:
        return _instrument_search_cache

    # Load from Redis
    try:
        rc = _rs()
        if rc is None:
            return _instrument_search_cache  # return stale rather than fail

        raw = await rc._r.get(_REDIS_INSTRUMENT_KEY)
        if not raw:
            return []

        import json as _json
        items: list[dict] = _json.loads(raw)
        items.sort(key=lambda x: x.get("symbol", ""))
        _instrument_search_cache = items
        _instrument_search_cache_ts = now
        log.debug("instrument_search_cache_loaded", count=len(items))
    except Exception as exc:
        log.debug("instrument_search_cache_load_failed", error=str(exc))

    return _instrument_search_cache


@router.get("/instruments/search")
async def search_instruments(q: str = "", exchange: str = "NSE", limit: int = 20):
    """
    Search NSE EQ instruments by symbol name prefix/substring.
    Used by the watchlist edit modal autocomplete.

    Data source: Redis key 'instruments:nse:eq' (written by the engine runner
    during pre-market setup). Prefix matches are returned first, then substring.
    Falls back to a hint if the engine has not yet authenticated with Kite.
    """
    if not q or len(q) < 2:
        return {"results": [], "count": 0, "query": q}

    q_upper = q.upper().strip()
    instruments = await _load_instrument_search_cache()

    if not instruments:
        return {
            "results": [],
            "count": 0,
            "query": q,
            "hint": "Instrument list not loaded — wait for engine to complete pre-market setup",
        }

    # Two-pass ranking: exact prefix matches first, then substring matches
    prefix_matches: list[dict] = []
    substr_matches: list[dict] = []

    for item in instruments:
        sym = item.get("symbol", "")
        if sym.startswith(q_upper):
            prefix_matches.append(item)
        elif q_upper in sym:
            substr_matches.append(item)

        if len(prefix_matches) + len(substr_matches) >= limit * 3:
            break  # Early exit — avoid scanning all 4000+ EQ instruments

    results = (prefix_matches + substr_matches)[:limit]

    return {
        "results": results,
        "count": len(results),
        "query": q,
        "total_in_cache": len(instruments),
    }


# ── /pipeline ───────────────────────────────────────────────────────────────────

@router.get("/pipeline")
async def get_pipeline():
    """Four-phase live strategy pipeline assembled from DB + Redis state."""
    rs = _rs()
    scanner = await get_scanner()
    positions = await get_positions()
    trades = await get_trades()
    orders = await get_orders()
    states = await rs.get_all_strategy_states() if rs is not None else {}

    latest_order_by_symbol: dict[str, dict[str, Any]] = {}
    for order in orders.get("orders", []):
        symbol = order.get("symbol")
        if symbol and symbol not in latest_order_by_symbol:
            latest_order_by_symbol[symbol] = order

    columns: dict[str, list[dict[str, Any]]] = {
        "scan_hit": [],
        "monitoring": [],
        "entry": [],
        "managing": [],
    }
    seen: set[str] = set()

    for hit in scanner.get("hits", []):
        symbol = hit.get("symbol")
        if not symbol:
            continue
        phase = _state_phase(hit.get("state"))
        if phase in {"CLOSED", "ABANDONED"}:
            continue
        card = {
            "symbol": symbol,
            "state": hit.get("state", "SCAN_HIT"),
            "signal_time": hit.get("signal_time"),
            "spike_multiple": hit.get("spike_multiple"),
            "volume": hit.get("volume"),
            "turnover_cr": hit.get("turnover_cr"),
            "close": hit.get("close"),
            "impact_high": hit.get("impact_high"),
            "impact_low": hit.get("impact_low"),
            "abandonment_reason": hit.get("abandonment_reason"),
        }
        state_data = states.get(symbol) or {}
        if state_data:
            card["state"] = state_data.get("state", card["state"])
            card["consolidation"] = state_data.get("consolidation")
            card["position"] = state_data.get("position")
            phase = _state_phase(card["state"])
        if symbol in latest_order_by_symbol:
            card["order"] = latest_order_by_symbol[symbol]

        target_column = {
            "SCAN_HIT": "scan_hit",
            "MONITORING": "monitoring",
            "ENTRY": "entry",
            "MANAGING": "managing",
        }.get(phase)
        if target_column:
            columns[target_column].append(card)
            seen.add(symbol)

    for symbol, state_data in (states or {}).items():
        if symbol in seen:
            continue
        phase = _state_phase(state_data.get("state"))
        target_column = {
            "SCAN_HIT": "scan_hit",
            "MONITORING": "monitoring",
            "ENTRY": "entry",
            "MANAGING": "managing",
        }.get(phase)
        if not target_column:
            continue
        card = {
            "symbol": symbol,
            "state": state_data.get("state"),
            "signal_time": state_data.get("impact_candle_time"),
            "spike_multiple": state_data.get("spike_multiple"),
            "volume": (state_data.get("impact_candle") or {}).get("volume"),
            "turnover_cr": (state_data.get("impact_candle") or {}).get("turnover_cr"),
            "close": state_data.get("impact_close"),
            "consolidation": state_data.get("consolidation"),
            "position": state_data.get("position"),
        }
        if symbol in latest_order_by_symbol:
            card["order"] = latest_order_by_symbol[symbol]
        columns[target_column].append(card)

    position_by_symbol = {p.get("symbol"): p for p in positions.get("positions", [])}
    for card in columns["managing"]:
        if card["symbol"] in position_by_symbol:
            card["position"] = position_by_symbol[card["symbol"]]

    counts = {name: len(items) for name, items in columns.items()}
    return {
        "columns": columns,
        "counts": counts,
        "summary": {
            "signals": scanner.get("count", 0),
            "monitored": sum(1 for h in scanner.get("hits", []) if h.get("progressed_to_monitor")),
            "trades_entered": trades.get("count", 0) + positions.get("count", 0),
            "wins": trades.get("wins", 0),
            "losses": trades.get("losses", 0),
            "net_pnl": trades.get("total_net_pnl", 0.0),
        },
    }


# ── /stock/{symbol} ─────────────────────────────────────────────────────────────

@router.get("/stock/{symbol}")
async def get_stock_detail(symbol: str):
    """Real per-symbol audit detail used by the slide-in drawer and charts."""
    from sqlalchemy import text

    sym = symbol.upper().strip()
    if not sym.replace("-", "").replace("&", "").replace(".", "").isalnum():
        raise HTTPException(status_code=400, detail="Invalid symbol")

    rs = _rs()
    state = await rs.get_strategy_state(sym) if rs is not None else None
    position = await rs.get_position(sym) if rs is not None else None
    tick = None
    candles: list[dict[str, Any]] = []
    if rs is not None:
        try:
            all_ticks = await rs.get_all_live_ticks()
            tick = all_ticks.get(sym)
            candles = await rs.get_recent_candles(sym, limit=180)
        except Exception:
            pass

    signals: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    orders: list[dict[str, Any]] = []
    try:
        engine = _get_db_engine()
        async with engine.connect() as conn:
            sig_result = await conn.execute(text(
                "SELECT symbol, signal_time, impact_candle_open, impact_candle_high, "
                "impact_candle_low, impact_candle_close, impact_candle_volume, "
                "impact_candle_turnover, volume_sma_500, volume_spike_multiple, "
                "progressed_to_monitor, progressed_to_action, resulted_in_trade, "
                "abandonment_reason, created_at "
                "FROM signals WHERE symbol = :symbol "
                "ORDER BY signal_time DESC LIMIT 10"
            ), {"symbol": sym})
            signals = [dict(r._mapping) for r in sig_result]

            trade_result = await conn.execute(text(
                "SELECT symbol, entry_order_id, entry_time, entry_price, quantity, "
                "initial_stop_loss, current_stop_loss, risk_per_share, risk_amount, "
                "target_1r2, target_1r4, sl_order_id, exit_order_id, exit_time, "
                "exit_price, gross_pnl, brokerage, stt, other_charges, net_pnl, "
                "status, cost_trailed, profit_locked, notes "
                "FROM trades WHERE symbol = :symbol "
                "ORDER BY entry_time DESC LIMIT 10"
            ), {"symbol": sym})
            trades = [dict(r._mapping) for r in trade_result]

            order_result = await conn.execute(text(
                "SELECT order_id, trade_id, symbol, event_type, status, price, "
                "trigger_price, quantity, filled_quantity, average_price, "
                "status_message, event_time "
                "FROM order_events WHERE symbol = :symbol "
                "ORDER BY event_time DESC LIMIT 50"
            ), {"symbol": sym})
            orders = [dict(r._mapping) for r in order_result]
    except Exception as exc:
        log.debug("stock_detail_db_query_failed", symbol=sym, error=str(exc))

    events: list[dict[str, Any]] = []
    if signals:
        sig = signals[0]
        events.append({
            "time": sig.get("signal_time"),
            "type": "SCAN HIT",
            "message": (
                f"{round(sig.get('volume_spike_multiple') or 0, 1)}x volume spike, "
                f"₹{round((sig.get('impact_candle_turnover') or 0) / 1e7, 2)} Cr turnover"
            ),
        })
        if sig.get("progressed_to_monitor"):
            events.append({
                "time": sig.get("signal_time"),
                "type": "MONITORING",
                "message": "Dry-up validation started",
            })
        if sig.get("abandonment_reason"):
            events.append({
                "time": sig.get("created_at"),
                "type": "ABANDONED",
                "message": str(sig.get("abandonment_reason")),
            })

    for order in orders:
        events.append({
            "time": order.get("event_time"),
            "type": f"ORDER {order.get('event_type') or ''}".strip(),
            "message": (
                f"{order.get('order_id')} {order.get('status') or ''} "
                f"qty {order.get('quantity') or order.get('filled_quantity') or '-'} "
                f"@ ₹{order.get('average_price') or order.get('price') or '-'}"
            ),
        })

    for trade in trades:
        events.append({
            "time": trade.get("entry_time"),
            "type": "TRADE ENTRY",
            "message": (
                f"{trade.get('quantity')} shares at ₹{trade.get('entry_price')} "
                f"risk ₹{trade.get('risk_amount')}"
            ),
        })
        if trade.get("exit_time"):
            events.append({
                "time": trade.get("exit_time"),
                "type": "TRADE CLOSED",
                "message": f"{trade.get('status')} net {trade.get('net_pnl')}",
            })

    events.sort(key=lambda e: str(e.get("time") or ""))

    return {
        "symbol": sym,
        "company_name": sym,
        "state": state,
        "position": position,
        "tick": tick,
        "candles": candles,
        "signals": signals,
        "trades": trades,
        "orders": orders,
        "events": events,
    }


# ── /candles/{symbol} ──────────────────────────────────────────────────────────

@router.get("/candles/{symbol}")
async def get_symbol_candles(symbol: str, limit: int = 60):
    """
    Lightweight Redis-only endpoint for mini chart popup.
    Returns the last `limit` 1-minute candles + strategy overlay data.
    No DB queries — fast enough to call on every drawer open.
    """
    sym = symbol.upper().strip()
    if not sym.replace("-", "").replace("&", "").replace(".", "").isalnum():
        raise HTTPException(status_code=400, detail="Invalid symbol")

    rs = _rs()
    candles: list[dict] = []
    state_data: dict = {}
    ltp: float | None = None
    impact_candle: dict = {}
    consolidation: dict = {}

    if rs is not None:
        try:
            candles = await rs.get_recent_candles(sym, limit=max(1, min(limit, 420)))
        except Exception:
            pass
        try:
            state_raw = await rs.get_strategy_state(sym)
            if state_raw:
                state_data = state_raw
                impact_candle = state_raw.get("impact_candle") or {}
                consolidation = state_raw.get("consolidation") or {}
        except Exception:
            pass
        try:
            ltp = await rs.get_last_ltp(sym)
        except Exception:
            pass

    # Compute chart overlay levels from strategy state
    breakout_level: float | None = (
        consolidation.get("breakout_trigger_price")
        or consolidation.get("high")
    )
    swing_low: float | None = consolidation.get("swing_low")
    impact_time: str | None = (
        state_data.get("impact_candle_time")
        or impact_candle.get("time")
    )
    impact_volume: int | None = impact_candle.get("volume")
    volume_readings: list = consolidation.get("volume_readings") or []

    return {
        "symbol": sym,
        "candles": candles,
        "count": len(candles),
        "ltp": ltp,
        "state": state_data.get("state"),
        "spike_multiple": state_data.get("spike_multiple") or impact_candle.get("spike_multiple"),
        "impact_candle_time": impact_time,
        "impact_volume": impact_volume,
        "breakout_level": breakout_level,
        "swing_low": swing_low,
        "candle_count": consolidation.get("candle_count", 0),
        "volume_readings": volume_readings,
        "avg_dryup_volume": (
            round(sum(volume_readings) / len(volume_readings))
            if volume_readings else None
        ),
        "impact_high": impact_candle.get("high") or state_data.get("impact_high"),
        "impact_low": impact_candle.get("low") or state_data.get("impact_low"),
        "impact_close": impact_candle.get("close") or state_data.get("impact_close"),
    }


# ── /journal ───────────────────────────────────────────────────────────────────

@router.get("/journal")
async def get_journal():
    from sqlalchemy import text

    try:
        engine = _get_db_engine()
        async with engine.connect() as conn:
            result = await conn.execute(text(
                "SELECT trade_date, total_capital, signals_fired, setups_abandoned, "
                "trades_taken, winning_trades, losing_trades, breakeven_trades, "
                "gross_pnl, total_charges, net_pnl, max_drawdown, notes "
                "FROM daily_pnl ORDER BY trade_date DESC LIMIT 30"
            ))
            rows = [dict(r._mapping) for r in result]
        return {"days": rows, "count": len(rows)}
    except Exception as exc:
        log.debug("journal_query_failed", error=str(exc))
        return {"days": [], "count": 0}


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
        _err_since: float | None = None
        import time as _time
        while True:
            try:
                await asyncio.sleep(0.5)  # 500ms
                ticks = await rs.get_all_live_ticks()
                last_ts = await rs.get_last_tick_timestamp()
                _err_since = None  # clear error streak on success
                if ticks:
                    await _send({
                        "event": "tick_batch",
                        "ticks": ticks,
                        "last_tick_at": last_ts,
                    })
            except asyncio.CancelledError:
                break
            except Exception as exc:
                # Track sustained errors — if Redis is down for >10s tell the UI
                now = _time.monotonic()
                if _err_since is None:
                    _err_since = now
                elif now - _err_since > 10:
                    try:
                        await _send({
                            "event": "feed_error",
                            "reason": "Redis unreachable — live ticks paused",
                            "error": str(exc),
                        })
                    except Exception:
                        pass
                    _err_since = now  # reset so we don't spam


    async def _pubsub_loop():
        r = None
        pubsub = None
        try:
            from app.store.redis_client import get_redis
            r = get_redis()
            pubsub = r.pubsub()
            await pubsub.subscribe(
                "pub:signals", "pub:state_changes", "pub:orders", "pub:pnl",
                "pub:candles", "pub:monitoring_ticks"
            )
            evt_map = {
                "pub:signals":       "scan_hit",
                "pub:state_changes": "state_change",
                "pub:orders":        "order_event",
                "pub:pnl":           "pnl_update",
                "pub:candles":       "candle_close",
                "pub:monitoring_ticks": "monitoring_tick",
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
                    # Spread data fields at top level so frontend can read
                    # msg.symbol, msg.signal_time, msg.status, etc. directly.
                    await _send({"event": evt_map.get(ch, "engine_event"), **data})
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
