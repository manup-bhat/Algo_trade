"""
engine/strategy/coordinator.py — Central dispatcher for all ticks and postbacks.

Phase 1: Manages CandleBuilders only. Routes ticks → candles → scanner (stub).
Phase 2+: Manages SymbolStateMachines and scanner.

Coordinator is the ONLY place that:
  - Holds all CandleBuilder instances
  - Holds all active SymbolStateMachine instances  
  - Routes ticks to the correct builder/SM
  - Handles WebSocket lifecycle events
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any

import pytz
import structlog

from engine.market.candle_builder import CandleBuilder, Candle

if TYPE_CHECKING:
    from engine.store.redis_store import RedisStore

log = structlog.get_logger(__name__)

IST_TZ = pytz.timezone("Asia/Kolkata")


class Coordinator:
    """
    Central dispatcher. One instance per engine process.

    Phase 1 responsibilities:
      - Initialize one CandleBuilder per universe symbol
      - Route ticks from KiteTicker → correct CandleBuilder
      - Handle WS reconnect: call reset_cumulative_baseline() on all builders
      - Handle market open: call reset() on all builders
      - Persist and load SMA history via RedisStore

    Attributes:
        candle_builders: dict[symbol → CandleBuilder] for ALL subscribed symbols
        token_to_symbol: dict[instrument_token → symbol] for O(1) tick routing
        active_state_machines: dict[symbol → SymbolStateMachine] (Phase 2+)
    """

    def __init__(self, redis_store: "RedisStore") -> None:
        self._redis = redis_store
        self.candle_builders: dict[str, CandleBuilder] = {}
        self.token_to_symbol: dict[int, str] = {}
        self.active_state_machines: dict[str, Any] = {}  # Populated in Phase 2
        self._tick_count: int = 0
        self._candle_count: int = 0

    # ── Setup ──────────────────────────────────────────────────────────────

    def initialize_builders(
        self,
        universe: dict[str, Any],  # symbol → InstrumentInfo
        sma_period: int = 500,
    ) -> None:
        """
        Create one CandleBuilder per universe symbol.
        Also populate token_to_symbol map for O(1) tick routing.
        Called during pre-market setup (09:00 AM).
        """
        for symbol, info in universe.items():
            self.candle_builders[symbol] = CandleBuilder(symbol, sma_period)
            self.token_to_symbol[info.instrument_token] = symbol

        log.info(
            "coordinator_builders_initialized",
            symbol_count=len(self.candle_builders),
        )

    async def load_sma_histories(self) -> None:
        """
        Load persisted SMA histories from Redis into CandleBuilders.
        Called at 09:00 AM pre-market setup after initialize_builders().
        """
        loaded = 0
        warming = 0
        for symbol, builder in self.candle_builders.items():
            history = await self._redis.load_volume_sma_history(symbol)
            if history:
                builder.load_history(history)
                loaded += 1
            else:
                warming += 1

        await self._redis.set_scanner_counts(loaded, warming)
        log.info(
            "sma_history_loaded",
            symbols_loaded=loaded,
            symbols_warming=warming,
        )

    async def persist_sma_histories(self) -> None:
        """
        Persist all current SMA histories to Redis.
        Called at 15:25 PM session end.
        """
        for symbol, builder in self.candle_builders.items():
            history = builder.volume_history_snapshot
            if history:
                await self._redis.save_volume_sma_history(symbol, history)
        log.info("sma_history_persisted", symbol_count=len(self.candle_builders))

    # ── Tick routing (hot path) ────────────────────────────────────────────

    async def process_ticks(self, ticks: list[dict]) -> None:
        """
        Main tick processing loop. Called from KiteTicker thread via _dispatch().

        For each tick:
          1. Resolve instrument_token → symbol (O(1) lookup)
          2. Route to CandleBuilder → may emit a completed Candle
          3. If MANAGING state: route ltp to SM for P&L / trailing (Phase 2+)
        """
        self._tick_count += len(ticks)

        for tick in ticks:
            token: int = tick.get("instrument_token", 0)
            symbol = self.token_to_symbol.get(token)
            if symbol is None:
                continue  # Not in our universe

            ltp: float = tick.get("last_price", 0.0)
            cum_vol: int = tick.get("volume_traded", 0)

            # Exchange timestamp: use tick data if available, else current IST time
            exch_ts = tick.get("exchange_timestamp")
            if exch_ts is None:
                exch_ts = datetime.datetime.now(IST_TZ)
            elif not hasattr(exch_ts, "tzinfo") or exch_ts.tzinfo is None:
                exch_ts = IST_TZ.localize(exch_ts)

            # CandleBuilder: accumulate tick, get candle if minute boundary crossed
            builder = self.candle_builders.get(symbol)
            if builder is None:
                continue

            candle = builder.on_tick(ltp, cum_vol, exch_ts)

            if candle is not None:
                self._candle_count += 1
                await self._on_candle_complete(symbol, candle)

            # Phase 1: No SM tick routing yet. Phase 2+ adds SM.on_tick() here.

    async def _on_candle_complete(self, symbol: str, candle: Candle) -> None:
        """
        Called when a 1-minute candle is completed.
        Phase 1: Just logs + updates LTP. Scanner added in Phase 2.
        """
        # Store latest close as LTP for entry widen logic (Phase 2+)
        await self._redis.set_last_ltp(symbol, candle.close)

        # Phase 2 will add: scanner.evaluate() + SM routing here
        log.debug(
            "candle_complete",
            symbol=symbol,
            time=candle.timestamp.strftime("%H:%M"),
            close=candle.close,
            volume=candle.volume,
            warmed_up=self.candle_builders[symbol].is_warmed_up,
        )

    # ── WebSocket lifecycle ────────────────────────────────────────────────

    async def on_websocket_connected(self) -> None:
        """
        Called on every WS connect/reconnect (Bug 4 fix).
        Resets cumulative volume baselines on ALL builders so the next tick
        from each symbol doesn't create a phantom volume spike.
        """
        count = 0
        for builder in self.candle_builders.values():
            builder.reset_cumulative_baseline()
            count += 1
        log.info("ws_connected_baselines_reset", builder_count=count)

    async def on_websocket_reconnect(self) -> None:
        """Called when a reconnect attempt starts (before success/failure)."""
        log.warning("ws_reconnecting_in_progress")

    async def on_fatal_disconnect(self) -> None:
        """
        Called when all reconnect attempts are exhausted.
        Phase 3+: Emergency close all MANAGING positions.
        Phase 1: Just log and update engine status.
        """
        log.critical(
            "fatal_ws_disconnect_no_positions_to_close_in_phase1"
        )
        await self._redis.set_engine_status({
            "status": "FATAL_DISCONNECT",
            "timestamp": datetime.datetime.now(IST_TZ).isoformat(),
            "active_sms": 0,
        })

    async def on_market_open(self) -> None:
        """
        Called at 09:15 AM by the APScheduler job.
        Resets all CandleBuilders for the new session (clears candle state,
        preserves SMA history).
        """
        for builder in self.candle_builders.values():
            builder.reset()
        log.info(
            "market_open_builders_reset",
            symbol_count=len(self.candle_builders),
        )

    async def on_order_postback(self, message: dict) -> None:
        """
        Route order postback to the appropriate SM.
        Phase 1: no-op (no orders). Phase 3+: wired to OrderTracker.
        """
        log.debug("order_postback_received_phase1_noop", order_id=message.get("order_id"))

    # ── Diagnostics ────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Return coordinator stats for health checks and logging."""
        warmed = sum(1 for b in self.candle_builders.values() if b.is_warmed_up)
        return {
            "total_builders": len(self.candle_builders),
            "warmed_up": warmed,
            "warming_up": len(self.candle_builders) - warmed,
            "active_state_machines": len(self.active_state_machines),
            "total_ticks_processed": self._tick_count,
            "total_candles_emitted": self._candle_count,
        }
