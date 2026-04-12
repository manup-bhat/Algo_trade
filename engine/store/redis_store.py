"""
engine/store/redis_store.py — ALL Redis operations through this single class.

No other module touches Redis directly. This centralizes key naming,
TTLs, serialization, and atomic operation semantics in one place,
making mocking in tests trivial (swap this class for a fake).

Key schema: see PART 5 of IVBS_Final_Spec.md
"""

from __future__ import annotations

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

_PUB_SIGNALS = "pub:signals"
_PUB_ORDERS = "pub:orders"
_PUB_STATE_CHANGES = "pub:state_changes"
_PUB_PNL = "pub:pnl"

_TTL_TOKEN = 86400       # 24 hours
_TTL_VOLUME_SMA = 172800 # 48 hours
_TTL_TICK_SIZE = 86400   # 24 hours
_TTL_LOCK = 10           # 10 seconds (auto-expires on crash)
_TTL_EOD = 90000         # ~25 hours (survives overnight)


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

    async def set_engine_status(self, status: dict[str, Any]) -> None:
        await self._r.set(_ENGINE_STATUS, json.dumps(status))

    async def get_engine_status(self) -> dict[str, Any] | None:
        raw = await self._r.get(_ENGINE_STATUS)
        return json.loads(raw) if raw else None

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
        await self._r.set(f"strategy:state:{symbol}", json.dumps(state_dict))

    async def get_strategy_state(self, symbol: str) -> dict[str, Any] | None:
        raw = await self._r.get(f"strategy:state:{symbol}")
        return json.loads(raw) if raw else None

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
        """Update unrealized P&L in the position snapshot for dashboard display."""
        pos_raw = await self._r.get(f"position:{symbol}")
        if pos_raw:
            pos = json.loads(pos_raw)
            pos["unrealized_pnl"] = unrealized
            await self._r.set(f"position:{symbol}", json.dumps(pos))

    # ── Last LTP (for entry widen logic) ──────────────────────────────────

    async def set_last_ltp(self, symbol: str, ltp: float) -> None:
        await self._r.set(f"ltp:{symbol}", str(ltp))

    async def get_last_ltp(self, symbol: str) -> float | None:
        val = await self._r.get(f"ltp:{symbol}")
        return float(val) if val else None

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

    # ── Scanner Stats ─────────────────────────────────────────────────────

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

    # ── Health Check ──────────────────────────────────────────────────────

    async def ping(self) -> bool:
        try:
            return await self._r.ping()
        except Exception:
            return False
