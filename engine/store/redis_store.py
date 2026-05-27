"""
engine/store/redis_store.py — ALL Redis operations through this single class.

No other module touches Redis directly. This centralizes key naming,
TTLs, serialization, and atomic operation semantics in one place,
making mocking in tests trivial (swap this class for a fake).

Key schema: see PART 5 of IVBS_Final_Spec.md
"""

from __future__ import annotations

import datetime
import json
from typing import Any

import redis.asyncio as aioredis
import structlog

log = structlog.get_logger(__name__)

# ── Key name constants ─────────────────────────────────────────────────────
_SESSION_TOKEN = "session:token"
_ENGINE_STATUS = "engine:status"
_ENGINE_CONTROL = "engine:control"
_ENGINE_CIRCUIT_BREAKER = "engine:circuit_breaker"
_ENGINE_DAILY_PNL = "engine:daily_pnl"
_ENGINE_CAPITAL = "engine:capital"
_ENGINE_BLOCKED_MARGIN = "engine:blocked_margin"
_ENGINE_SCANNER_READY = "engine:scanner:ready_count"
_ENGINE_SCANNER_WARMING = "engine:scanner:warming_count"
_ENGINE_CONFIG_PAPER_TRADE = "engine:config:paper_trade"
_ENGINE_CONFIG_MAX_CAPITAL = "engine:config:max_capital"        # fallback (no per-mode cap)
_ENGINE_CONFIG_MAX_CAPITAL_PAPER = "engine:config:max_capital_paper"  # cap for PAPER trades
_ENGINE_CONFIG_MAX_CAPITAL_LIVE  = "engine:config:max_capital_live"   # cap for LIVE trades
_ENGINE_CONFIG_TRADE_MODE = "engine:config:trade_mode"
_ENGINE_REINIT_TRIGGER    = "engine:reinit_trigger"
_ENGINE_RUNNER_HEARTBEAT = "engine:runner:heartbeat"
_ENGINE_PENDING_APPROVAL = "engine:pending_approval"
_APPROVAL_KEY_PREFIX = "approval:pending:"
_MARKET_EOD_SNAPSHOT = "market:eod_snapshot"

_PUB_SIGNALS = "pub:signals"
_PUB_ORDERS = "pub:orders"
_PUB_STATE_CHANGES = "pub:state_changes"
_PUB_PNL = "pub:pnl"
_PUB_CANDLES = "pub:candles"
_PUB_MONITORING_TICKS = "pub:monitoring_ticks"

_TTL_TOKEN = 86400       # 24 hours
_TTL_VOLUME_SMA = 172800 # 48 hours
_TTL_TICK_SIZE = 86400   # 24 hours
_TTL_LOCK = 10           # 10 seconds (auto-expires on crash)
_TTL_EOD = 90000         # ~25 hours (survives overnight)
_TTL_LIVE_TICK = 54000   # 15 hours
_TTL_EOD_MARKET_SNAPSHOT = 54000  # 15 hours
_TTL_RUNNER_HEARTBEAT = 20
_TTL_RECENT_CANDLES = 54000
_MAX_RECENT_CANDLES = 420

# Single Redis Hash for all live ticks: HGETALL is O(1) vs KEYS livetick:* O(N)
_LIVETICK_HASH = "livetick_hash"
# ISO timestamp updated every tick-batch so dashboard can detect stale data
_LAST_TICK_TS_KEY = "engine:last_tick_at"


class RedisStore:
    """
    Centralized Redis interface for the trading engine.
    Instantiated once in runner.py and passed to modules that need it.
    """

    def __init__(self, redis: aioredis.Redis) -> None:
        self._r = redis

    # ── Token / Auth ───────────────────────────────────────────────────────

    async def save_token(self, token_data: dict[str, Any]) -> None:
        await self._r.set(_SESSION_TOKEN, json.dumps(token_data), ex=_TTL_TOKEN)

    async def load_token(self) -> dict[str, Any] | None:
        raw = await self._r.get(_SESSION_TOKEN)
        return json.loads(raw) if raw else None

    # ── Engine Status / Control ────────────────────────────────────────────

    async def set_engine_status(self, status_data: dict[str, Any]) -> None:
        await self._r.set(_ENGINE_STATUS, json.dumps(status_data))

    async def get_engine_status(self) -> dict[str, Any] | None:
        val = await self._r.get(_ENGINE_STATUS)
        return json.loads(val) if val else None

    async def get_engine_control(self) -> str | None:
        return await self._r.get(_ENGINE_CONTROL)

    async def set_engine_control(self, command: str) -> None:
        await self._r.set(_ENGINE_CONTROL, command)

    # ── Circuit Breaker ────────────────────────────────────────────────────

    async def set_circuit_breaker(self, tripped: bool) -> None:
        await self._r.set(_ENGINE_CIRCUIT_BREAKER, "true" if tripped else "false")

    async def is_circuit_breaker_tripped(self) -> bool:
        val = await self._r.get(_ENGINE_CIRCUIT_BREAKER)
        return val == "true"

    # ── Config Overrides ───────────────────────────────────────────────────

    async def get_paper_trade_override(self) -> bool | None:
        val = await self._r.get(_ENGINE_CONFIG_PAPER_TRADE)
        return val == "true" if val else None

    async def set_paper_trade_override(self, paper_trade: bool) -> None:
        await self._r.set(_ENGINE_CONFIG_PAPER_TRADE, "true" if paper_trade else "false")

    async def get_max_capital_override(self) -> float | None:
        """Global max-capital override (fallback when per-mode keys are unset)."""
        val = await self._r.get(_ENGINE_CONFIG_MAX_CAPITAL)
        return float(val) if val else None

    async def set_max_capital_override(self, capital: float | None) -> None:
        if capital is None:
            await self._r.delete(_ENGINE_CONFIG_MAX_CAPITAL)
        else:
            await self._r.set(_ENGINE_CONFIG_MAX_CAPITAL, str(capital))

    async def get_max_capital_paper(self) -> float | None:
        """Capital cap applied to PAPER-mode trade sizing."""
        val = await self._r.get(_ENGINE_CONFIG_MAX_CAPITAL_PAPER)
        if val:
            return float(val)
        return await self.get_max_capital_override()  # fall back to global

    async def set_max_capital_paper(self, capital: float | None) -> None:
        if capital is None:
            await self._r.delete(_ENGINE_CONFIG_MAX_CAPITAL_PAPER)
        else:
            await self._r.set(_ENGINE_CONFIG_MAX_CAPITAL_PAPER, str(capital))

    async def get_max_capital_live(self) -> float | None:
        """Capital cap applied to LIVE-mode trade sizing."""
        val = await self._r.get(_ENGINE_CONFIG_MAX_CAPITAL_LIVE)
        if val:
            return float(val)
        return await self.get_max_capital_override()  # fall back to global

    async def set_max_capital_live(self, capital: float | None) -> None:
        if capital is None:
            await self._r.delete(_ENGINE_CONFIG_MAX_CAPITAL_LIVE)
        else:
            await self._r.set(_ENGINE_CONFIG_MAX_CAPITAL_LIVE, str(capital))

    async def get_trade_mode_override(self) -> str | None:
        """Return the Redis-overridden TRADE_MODE (PAPER/LIVE/SIMULTANEOUS), or None if unset."""
        val = await self._r.get(_ENGINE_CONFIG_TRADE_MODE)
        if val is None:
            return None
        return val.decode() if isinstance(val, bytes) else val

    async def set_trade_mode_override(self, mode: str) -> None:
        """Store a TRADE_MODE override in Redis. Mode must be PAPER, LIVE, or SIMULTANEOUS."""
        await self._r.set(_ENGINE_CONFIG_TRADE_MODE, mode.upper())

    async def set_reinit_trigger(self) -> None:
        """Signal the engine runner to call job_pre_market_setup (used after fresh login)."""
        await self._r.set(_ENGINE_REINIT_TRIGGER, "1", ex=300)  # expires in 5 minutes

    async def consume_reinit_trigger(self) -> bool:
        """Returns True and deletes the key if a reinit was requested."""
        val = await self._r.getdel(_ENGINE_REINIT_TRIGGER)
        return val is not None

    async def set_runner_heartbeat(self, status: str, pid: int | None = None) -> None:
        """Short TTL heartbeat proving an engine.runner process is currently alive."""
        payload = {
            "status": status,
            "pid": pid,
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        }
        await self._r.set(
            _ENGINE_RUNNER_HEARTBEAT,
            json.dumps(payload),
            ex=_TTL_RUNNER_HEARTBEAT,
        )

    async def get_runner_heartbeat(self) -> dict[str, Any] | None:
        raw = await self._r.get(_ENGINE_RUNNER_HEARTBEAT)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return {"raw": raw}

    async def clear_runner_heartbeat(self) -> None:
        await self._r.delete(_ENGINE_RUNNER_HEARTBEAT)

    # ── Capital & P&L ──────────────────────────────────────────────────────

    async def set_capital(self, capital: float) -> None:
        await self._r.set(_ENGINE_CAPITAL, str(capital), ex=_TTL_EOD)

    async def get_capital(self) -> float:
        val = await self._r.get(_ENGINE_CAPITAL)
        return float(val) if val else 0.0

    async def set_daily_pnl(self, pnl: float) -> None:
        await self._r.set(_ENGINE_DAILY_PNL, str(pnl), ex=_TTL_EOD)

    async def get_daily_pnl(self) -> float:
        val = await self._r.get(_ENGINE_DAILY_PNL)
        return float(val) if val else 0.0

    async def increment_daily_pnl(self, delta: float) -> float:
        """Atomically add delta to daily P&L. Returns new total."""
        # Use INCRBYFLOAT for atomic operation
        new_val = await self._r.incrbyfloat(_ENGINE_DAILY_PNL, delta)
        return float(new_val)

    # ── Blocked Margin ─────────────────────────────────────────────────────

    async def set_blocked_margin(self, amount: float) -> None:
        await self._r.set(_ENGINE_BLOCKED_MARGIN, str(amount))

    async def get_blocked_margin(self) -> float:
        val = await self._r.get(_ENGINE_BLOCKED_MARGIN)
        return float(val) if val else 0.0

    async def increment_blocked_margin(self, delta: float) -> None:
        await self._r.incrbyfloat(_ENGINE_BLOCKED_MARGIN, delta)

    async def decrement_blocked_margin(self, delta: float) -> None:
        await self._r.incrbyfloat(_ENGINE_BLOCKED_MARGIN, -delta)

    # ── Instrument Data (per-symbol, set at pre-market) ───────────────────

    async def set_tick_size(self, symbol: str, tick_size: float) -> None:
        await self._r.set(f"tick_size:{symbol}", str(tick_size), ex=_TTL_TICK_SIZE)

    async def get_tick_size(self, symbol: str) -> float:
        val = await self._r.get(f"tick_size:{symbol}")
        return float(val) if val else 0.05  # Default 5 paise

    async def set_instrument_token(self, symbol: str, token: int) -> None:
        await self._r.set(f"token:{symbol}", str(token), ex=_TTL_TICK_SIZE)

    async def get_instrument_token(self, symbol: str) -> int | None:
        val = await self._r.get(f"token:{symbol}")
        return int(val) if val else None

    # ── Volume SMA History (persisted across sessions) ─────────────────────

    async def save_volume_sma_history(self, symbol: str, volumes: list[int]) -> None:
        """Persist volume history at session end. 48h TTL survives the overnight gap."""
        await self._r.set(
            f"volume_sma:{symbol}",
            json.dumps(volumes),
            ex=_TTL_VOLUME_SMA,
        )

    async def load_volume_sma_history(self, symbol: str) -> list[int] | None:
        raw = await self._r.get(f"volume_sma:{symbol}")
        if raw is None:
            return None
        return json.loads(raw)

    # ── Strategy State (per active SM) ─────────────────────────────────────

    async def set_strategy_state(self, symbol: str, state_dict: dict[str, Any]) -> None:
        from datetime import datetime, timezone
        # Stamp every write with IST date so the dashboard can filter stale cross-day state.
        # 28-hour TTL ensures keys auto-expire overnight even if clear_strategy_state is
        # not called (e.g. crash mid-session).
        stamped = dict(state_dict)
        stamped["_updated_at"] = datetime.now(timezone.utc).isoformat()
        await self._r.set(f"strategy:state:{symbol}", json.dumps(stamped), ex=28 * 3600)

    async def get_strategy_state(self, symbol: str) -> dict[str, Any] | None:
        raw = await self._r.get(f"strategy:state:{symbol}")
        return json.loads(raw) if raw else None

    async def clear_stale_strategy_states(self, today_iso: str) -> int:
        """
        Sweep all strategy:state:* Redis keys and delete any whose _updated_at
        or impact_candle_time predates today_iso (YYYY-MM-DD).

        Called at the start of job_pre_market_setup() so the dashboard never
        shows phantom pipeline cards from a previous trading session.
        The 28-hour TTL on set_strategy_state() is a secondary safety net;
        this sweep is the primary guarantee.

        Returns the number of stale keys removed.
        """
        keys = await self._r.keys("strategy:state:*")
        if not keys:
            return 0
        removed = 0
        for key in keys:
            val = await self._r.get(key)
            if not val:
                continue
            try:
                data = json.loads(val)
                ts = data.get("_updated_at") or data.get("impact_candle_time")
                if ts and str(ts)[:10] < today_iso:
                    await self._r.delete(key)
                    removed += 1
            except Exception:
                pass  # malformed key — leave it for the TTL to expire
        return removed

    async def clear_strategy_state(self, symbol: str) -> None:
        await self._r.delete(f"strategy:state:{symbol}")

    async def get_all_strategy_states(self) -> dict[str, dict[str, Any]]:
        """Fetch all active strategy state keys (for dashboard polling)."""
        keys = await self._r.keys("strategy:state:*")
        if not keys:
            return {}
        values = await self._r.mget(keys)
        result = {}
        for key, val in zip(keys, values):
            if val:
                symbol = key.split(":")[-1]
                result[symbol] = json.loads(val)
        return result

    # ── Position (for open positions) ─────────────────────────────────────

    async def set_position(self, symbol: str, position_dict: dict[str, Any]) -> None:
        await self._r.set(f"position:{symbol}", json.dumps(position_dict))

    async def get_position(self, symbol: str) -> dict[str, Any] | None:
        raw = await self._r.get(f"position:{symbol}")
        return json.loads(raw) if raw else None

    async def clear_position(self, symbol: str) -> None:
        await self._r.delete(f"position:{symbol}")

    async def update_unrealized_pnl(self, symbol: str, unrealized: float) -> None:
        """Update unrealized P&L for dashboard display.

        Uses a dedicated lightweight key (unrealized:{symbol}) to avoid the
        expensive GET+deserialize+update+serialize+SET cycle on the full position
        dict on every tick. The dashboard reads this key separately.
        """
        await self._r.set(
            f"unrealized:{symbol}",
            str(round(unrealized, 2)),
            ex=_TTL_LIVE_TICK,
        )

    # ── Last LTP (for entry widen logic + dashboard feed) ─────────────────────

    async def set_last_ltp(self, symbol: str, ltp: float) -> None:
        await self._r.set(f"ltp:{symbol}", str(ltp))

    async def get_last_ltp(self, symbol: str) -> float | None:
        val = await self._r.get(f"ltp:{symbol}")
        return float(val) if val else None

    async def set_live_tick(
        self,
        symbol: str,
        ltp: float,
        day_open: float,
        volume: int,
        minute_volume: int | None = None,
        volume_sma_500: float | None = None,
        prev_close: float = 0.0,
    ) -> None:
        """Store rich live tick data for dashboard market feed. TTL = 15 hours.

        pct_chg is calculated against prev_close (previous day's closing price,
        = ohlc.close in Kite QUOTE tick) to match the Kite app display.
        Falls back to day_open if prev_close is not available.
        """
        ref = prev_close if prev_close > 0 else day_open
        pct_chg = round(((ltp - ref) / ref * 100), 2) if ref > 0 else 0.0
        payload: dict[str, Any] = {
            "ltp": ltp,
            "open": day_open,
            "prev_close": prev_close,
            "pct_chg": pct_chg,
            "volume": volume,
        }
        if minute_volume is not None:
            payload["minute_volume"] = minute_volume
        if volume_sma_500:
            payload["volume_sma_500"] = volume_sma_500
            payload["relative_volume"] = round((minute_volume or 0) / volume_sma_500, 2)
        await self._r.set(
            f"livetick:{symbol}",
            json.dumps(payload),
            ex=_TTL_LIVE_TICK,
        )
        # Also keep legacy ltp key for backward compat
        await self._r.set(f"ltp:{symbol}", str(ltp))

    async def _collect_live_ticks(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Collect live ticks using O(1) HGETALL on the livetick_hash.

        Falls back to legacy KEYS scan only on first run before hash is populated.
        The coordinator pipeline writes all symbols into livetick_hash in one batch.
        """
        raw_hash = await self._r.hgetall(_LIVETICK_HASH)
        if raw_hash:
            result: list[dict[str, Any]] = []
            for field, val in raw_hash.items():
                try:
                    sym = field.decode() if isinstance(field, bytes) else field
                    data = json.loads(val)
                    result.append({"symbol": sym, **data})
                except Exception:
                    pass
            result.sort(key=lambda x: abs(x.get("pct_chg", 0)), reverse=True)
            return result[:limit] if limit is not None else result

        # Fallback: legacy KEYS scan for first run / migration (before hash is populated)
        keys = await self._r.keys("livetick:*")
        if not keys:
            return []

        selected = keys if limit is None else keys[:limit]
        values = await self._r.mget(selected)

        result = []
        for key, val in zip(selected, values):
            if val:
                try:
                    data = json.loads(val)
                    symbol = key.split(":", 1)[1] if isinstance(key, str) else key.decode().split(":", 1)[1]
                    result.append({"symbol": symbol, **data})
                except Exception:
                    pass

        result.sort(key=lambda x: abs(x.get("pct_chg", 0)), reverse=True)
        return result

    async def get_market_snapshot(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return up to `limit` symbols with their live price, change%, volume."""
        return await self._collect_live_ticks(limit=limit)

    async def persist_eod_market_snapshot(self) -> int:
        """Persist latest market ticks for after-hours dashboard reads."""
        ticks = await self._collect_live_ticks(limit=None)
        payload = {
            "captured_at": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
            "ticks": ticks,
        }
        await self._r.set(
            _MARKET_EOD_SNAPSHOT,
            json.dumps(payload),
            ex=_TTL_EOD_MARKET_SNAPSHOT,
        )
        return len(ticks)

    async def load_eod_market_snapshot(self, limit: int = 50) -> list[dict[str, Any]]:
        """Load previously persisted end-of-day market snapshot."""
        raw = await self._r.get(_MARKET_EOD_SNAPSHOT)
        if not raw:
            return []
        try:
            payload = json.loads(raw)
            ticks = payload.get("ticks", [])
            if not isinstance(ticks, list):
                return []
            return ticks[:limit]
        except Exception:
            return []

    async def append_recent_candle(
        self,
        symbol: str,
        candle: Any,
        volume_sma_500: float | None = None,
    ) -> None:
        """Keep a bounded per-symbol list of real completed 1-minute candles."""
        payload = {
            "symbol": symbol,
            "timestamp": candle.timestamp.isoformat(),
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
            "volume": candle.volume,
            "turnover": candle.turnover,
            "volume_sma_500": volume_sma_500,
        }
        key = f"candles:{symbol}"
        await self._r.rpush(key, json.dumps(payload))
        await self._r.ltrim(key, -_MAX_RECENT_CANDLES, -1)
        await self._r.expire(key, _TTL_RECENT_CANDLES)

    async def get_recent_candles(self, symbol: str, limit: int = 120) -> list[dict[str, Any]]:
        raw_items = await self._r.lrange(f"candles:{symbol}", -limit, -1)
        candles: list[dict[str, Any]] = []
        for raw in raw_items:
            try:
                candles.append(json.loads(raw))
            except Exception:
                continue
        return candles

    async def get_all_live_ticks(self) -> dict[str, dict[str, Any]]:
        """
        Return ALL symbols' live tick data keyed by symbol.

        Uses HGETALL on _LIVETICK_HASH (O(1)) written by coordinator pipeline.
        Falls back to legacy KEYS scan on first run before hash is populated.
        """
        raw_hash = await self._r.hgetall(_LIVETICK_HASH)
        if raw_hash:
            result: dict[str, dict[str, Any]] = {}
            for field, val in raw_hash.items():
                try:
                    sym = field.decode() if isinstance(field, bytes) else field
                    result[sym] = json.loads(val)
                except Exception:
                    pass
            return result
        # Fallback: legacy KEYS scan for first run / migration
        keys = await self._r.keys("livetick:*")
        if not keys:
            return {}
        values = await self._r.mget(keys)
        result = {}
        for key, val in zip(keys, values):
            if val:
                try:
                    sym = key.split(":", 1)[1] if isinstance(key, str) else key.decode().split(":", 1)[1]
                    result[sym] = json.loads(val)
                except Exception:
                    pass
        return result

    async def get_last_tick_timestamp(self) -> str | None:
        """ISO timestamp of last tick batch. Used by dashboard to detect stale/frozen data."""
        raw = await self._r.get(_LAST_TICK_TS_KEY)
        return raw.decode() if isinstance(raw, bytes) else raw

    # ── Exit Race Condition Lock ───────────────────────────────────────────

    async def acquire_symbol_lock(self, symbol: str) -> bool:
        """
        Atomically acquire an exit lock for the symbol.
        Uses SET NX EX — returns True if lock was acquired, False if already held.
        Auto-expires in 10 seconds to handle crash scenarios.
        """
        result = await self._r.set(
            f"lock:symbol:{symbol}",
            "locked",
            nx=True,
            ex=_TTL_LOCK,
        )
        return result is True

    async def release_symbol_lock(self, symbol: str) -> None:
        await self._r.delete(f"lock:symbol:{symbol}")

    # \u2500\u2500 Market Direction Gate (Nifty EMA + India VIX) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

    _NIFTY_EMA_KEY = "nifty:ema_5min"
    _VIX_KEY = "vix:last"
    _NIFTY_LTP_KEY = "nifty:ltp"
    _TTL_MARKET_GATE = 7200  # 2 hours

    async def get_nifty_ema(self) -> float | None:
        """Return the latest Nifty 50 5-minute EMA, or None if not yet computed."""
        val = await self._r.get(self._NIFTY_EMA_KEY)
        return float(val) if val else None

    async def set_nifty_ema(self, ema: float) -> None:
        """Store the latest Nifty 5-min EMA. TTL = 2 hours so stale values expire."""
        await self._r.set(self._NIFTY_EMA_KEY, str(round(ema, 2)), ex=self._TTL_MARKET_GATE)

    async def get_nifty_ltp(self) -> float | None:
        """Return the latest Nifty 50 LTP tick."""
        val = await self._r.get(self._NIFTY_LTP_KEY)
        return float(val) if val else None

    async def set_nifty_ltp(self, ltp: float) -> None:
        await self._r.set(self._NIFTY_LTP_KEY, str(ltp), ex=self._TTL_MARKET_GATE)

    async def get_vix(self) -> float | None:
        """Return the latest India VIX value, or None if not yet received."""
        val = await self._r.get(self._VIX_KEY)
        return float(val) if val else None

    async def set_vix(self, vix: float) -> None:
        """Store latest India VIX. TTL = 2 hours."""
        await self._r.set(self._VIX_KEY, str(round(vix, 2)), ex=self._TTL_MARKET_GATE)

    # \u2500\u2500 Scanner Stats \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

    async def set_scanner_counts(self, ready: int, warming: int) -> None:
        await self._r.mset({
            _ENGINE_SCANNER_READY: str(ready),
            _ENGINE_SCANNER_WARMING: str(warming),
        })


    # ── Pub/Sub ───────────────────────────────────────────────────────────

    async def publish_signal(self, data: dict[str, Any]) -> None:
        await self._r.publish(_PUB_SIGNALS, json.dumps(data))

    async def publish_order_event(self, data: dict[str, Any]) -> None:
        await self._r.publish(_PUB_ORDERS, json.dumps(data))

    async def publish_state_change(self, data: dict[str, Any]) -> None:
        await self._r.publish(_PUB_STATE_CHANGES, json.dumps(data))

    async def publish_pnl(self, data: dict[str, Any]) -> None:
        await self._r.publish(_PUB_PNL, json.dumps(data))

    async def publish_candle_close(self, data: dict[str, Any]) -> None:
        await self._r.publish(_PUB_CANDLES, json.dumps(data))

    async def publish_monitoring_tick(self, data: dict[str, Any]) -> None:
        await self._r.publish(_PUB_MONITORING_TICKS, json.dumps(data))

    # ── Trade Approval Queue (Live Mode Gate) ─────────────────────────────────
    # When PAPER_TRADE=False, entries are held in ACTION_PENDING_APPROVAL until
    # the trader approves via the dashboard API.

    async def add_pending_approval(
        self,
        symbol: str,
        entry_data: dict[str, Any],
    ) -> None:
        """
        Store a pending trade approval request.
        Published to pub:approvals so the dashboard WS can alert the trader.
        """
        import time as _time
        key = f"{_APPROVAL_KEY_PREFIX}{symbol}"
        entry_data["_queued_at"] = _time.time()
        entry_data["symbol"] = symbol
        await self._r.set(key, json.dumps(entry_data))
        # Also add to a sorted set scored by timestamp for dashboard to enumerate
        await self._r.zadd(_ENGINE_PENDING_APPROVAL, {symbol: _time.time()})
        await self._r.publish(_PUB_SIGNALS, json.dumps({
            "event": "pending_approval",
            "symbol": symbol,
            **entry_data,
        }))

    async def get_pending_approval(self, symbol: str) -> dict[str, Any] | None:
        """Return pending approval data for a symbol, or None if none."""
        key = f"{_APPROVAL_KEY_PREFIX}{symbol}"
        raw = await self._r.get(key)
        return json.loads(raw) if raw else None

    async def remove_pending_approval(self, symbol: str) -> None:
        """Remove a symbol from the approval queue (approved or abandoned)."""
        key = f"{_APPROVAL_KEY_PREFIX}{symbol}"
        await self._r.delete(key)
        await self._r.zrem(_ENGINE_PENDING_APPROVAL, symbol)

    async def get_all_pending_approvals(self) -> dict[str, dict[str, Any]]:
        """Return all pending approvals keyed by symbol."""
        members = await self._r.zrange(_ENGINE_PENDING_APPROVAL, 0, -1)
        result = {}
        for sym in members:
            data = await self.get_pending_approval(sym)
            if data:
                result[sym] = data
        return result

    async def approve_trade(self, symbol: str) -> dict[str, Any] | None:
        """
        Approve a pending trade. Returns the stored entry data, or None if not found.
        Called by the dashboard /approvals POST endpoint.
        """
        data = await self.get_pending_approval(symbol)
        if data is None:
            return None
        await self.remove_pending_approval(symbol)
        return data

    async def reject_trade(self, symbol: str, reason: str = "manual_rejection") -> bool:
        """
        Reject a pending trade. Removes from queue and abandons the SM.
        """
        data = await self.get_pending_approval(symbol)
        if data is None:
            return False
        await self.remove_pending_approval(symbol)
        return True

    # ── Health Check ──────────────────────────────────────────────────────

    async def ping(self) -> bool:
        try:
            return await self._r.ping()
        except Exception:
            return False
