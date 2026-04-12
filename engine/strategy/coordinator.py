"""
engine/strategy/coordinator.py — Central dispatcher for all ticks and postbacks.

Phase 2 additions over Phase 1:
  - Routes candles to scanner.evaluate() for IDLE symbols
  - Creates SymbolStateMachine on scan hit
  - Routes candles to active SMs for SCAN_HIT / MONITORING
  - Routes ticks to MANAGING SMs (per-tick trailing/SL check)
  - Cleans up CLOSED SMs
  - Circuit breaker check integrated
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any

import pytz
import structlog

from engine.market.candle_builder import CandleBuilder, Candle
from engine.market import calendar as mkt_calendar
from engine.strategy import scanner
from engine.strategy.state_machine import SymbolStateMachine, StrategyState

if TYPE_CHECKING:
    from engine.store.redis_store import RedisStore
    from engine.store.db_writer import DbWriter

log = structlog.get_logger(__name__)
IST_TZ = pytz.timezone("Asia/Kolkata")


class Coordinator:
    """
    Central dispatcher. One instance per engine process.

    Responsibilities:
      - Initialize one CandleBuilder per universe symbol
      - Route ticks → CandleBuilders → (maybe) completed Candles
      - For completed Candles → scanner (IDLE) or active SM (non-IDLE)
      - For MANAGING SMs → route per-tick (ltp, ts) for P&L / trailing
      - Handle WS reconnect: call reset_cumulative_baseline() on all builders
      - Persist and load SMA history via RedisStore
      - Cleanup CLOSED SMs after each on_candle call
    """

    def __init__(self, redis_store: "RedisStore", db_writer: "DbWriter") -> None:
        self._redis = redis_store
        self._db = db_writer
        self.candle_builders: dict[str, CandleBuilder] = {}
        self.token_to_symbol: dict[int, str] = {}
        self.symbol_to_token: dict[str, int] = {}
        self.active_state_machines: dict[str, SymbolStateMachine] = {}
        self._tick_count: int = 0
        self._candle_count: int = 0
        self._signal_count: int = 0

    # ── Setup ──────────────────────────────────────────────────────────────

    def initialize_builders(
        self,
        universe: dict[str, Any],  # symbol → InstrumentInfo
        sma_period: int = 500,
    ) -> None:
        """Create one CandleBuilder per universe symbol. Called at 09:00 AM."""
        for symbol, info in universe.items():
            self.candle_builders[symbol] = CandleBuilder(symbol, sma_period)
            self.token_to_symbol[info.instrument_token] = symbol
            self.symbol_to_token[symbol] = info.instrument_token

        log.info("coordinator_builders_initialized", symbol_count=len(self.candle_builders))

    async def load_sma_histories(self) -> None:
        """Load persisted SMA histories from Redis. Called at 09:00 AM."""
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
        log.info("sma_history_loaded", symbols_loaded=loaded, symbols_warming=warming)

    async def persist_sma_histories(self) -> None:
        """Persist SMA histories to Redis. Called at 15:25 PM session end."""
        for symbol, builder in self.candle_builders.items():
            history = builder.volume_history_snapshot
            if history:
                await self._redis.save_volume_sma_history(symbol, history)
        log.info("sma_history_persisted", symbol_count=len(self.candle_builders))

    # ── Tick Routing (HOT PATH) ────────────────────────────────────────────

    async def process_ticks(self, ticks: list[dict]) -> None:
        """
        Main tick processing loop. Called from KiteTicker thread via _dispatch().
        This is the innermost hot path — keep it lean.

        Per-tick: symbol lookup + CandleBuilder update + optional SM tick routing.
        Per-candle: scanner evaluation or SM on_candle routing.
        """
        self._tick_count += len(ticks)

        for tick in ticks:
            token: int = tick.get("instrument_token", 0)
            symbol = self.token_to_symbol.get(token)
            if symbol is None:
                continue

            ltp: float = tick.get("last_price", 0.0)
            cum_vol: int = tick.get("volume_traded", 0)

            exch_ts = tick.get("exchange_timestamp")
            if exch_ts is None:
                exch_ts = datetime.datetime.now(IST_TZ)
            elif exch_ts.tzinfo is None:
                exch_ts = IST_TZ.localize(exch_ts)

            builder = self.candle_builders.get(symbol)
            if builder is None:
                continue

            candle = builder.on_tick(ltp, cum_vol, exch_ts)

            if candle is not None:
                self._candle_count += 1
                await self._on_candle_complete(symbol, candle)

            # Per-tick SM routing (MANAGING state only)
            sm = self.active_state_machines.get(symbol)
            if sm is not None and sm.state == StrategyState.MANAGING:
                await sm.on_tick(ltp, exch_ts)

    async def _on_candle_complete(self, symbol: str, candle: Candle) -> None:
        """
        Called when a 1-minute candle is completed for a symbol.
        Routes to scanner (IDLE symbols) or active SM (non-IDLE symbols).
        """
        # Store last LTP for entry widen logic
        try:
            await self._redis.set_last_ltp(symbol, candle.close)
        except Exception:
            pass

        if symbol not in self.active_state_machines:
            # IDLE path: run Phase 1 scanner
            if not mkt_calendar.is_market_open():
                return

            builder = self.candle_builders.get(symbol)
            if builder is None:
                return

            instrument_token = self.symbol_to_token.get(symbol, 0)
            impact = scanner.evaluate(candle, builder, instrument_token)

            if impact is not None:
                self._signal_count += 1
                sm = SymbolStateMachine(
                    symbol=symbol,
                    instrument_token=instrument_token,
                    redis_store=self._redis,
                    db_writer=self._db,
                )
                self.active_state_machines[symbol] = sm
                await sm.on_scan_hit(impact)

                # Update signal progression for monitoring
                if sm._signal_id:
                    try:
                        await self._db.update_signal_progression(
                            sm._signal_id, progressed_to_monitor=True
                        )
                    except Exception:
                        pass
        else:
            # Non-IDLE path: route to existing SM
            sm = self.active_state_machines[symbol]
            await sm.on_candle(
                candle.open,
                candle.high,
                candle.low,
                candle.close,
                candle.volume,
                candle.timestamp,
            )

            # Cleanup CLOSED SMs
            if sm.state == StrategyState.CLOSED:
                del self.active_state_machines[symbol]
                log.debug("sm_cleaned_up", symbol=symbol)

    # ── WebSocket Lifecycle ────────────────────────────────────────────────

    async def on_websocket_connected(self) -> None:
        """Bug 4 fix: reset all baselines on every WS connect."""
        for builder in self.candle_builders.values():
            builder.reset_cumulative_baseline()
        log.info("ws_connected_baselines_reset", count=len(self.candle_builders))

    async def on_websocket_reconnect(self) -> None:
        log.warning("ws_reconnecting_in_progress")

    async def on_fatal_disconnect(self) -> None:
        """Emergency: force squareoff all open positions."""
        log.critical("fatal_ws_disconnect_squaring_off_all")
        for sm in list(self.active_state_machines.values()):
            if sm.state == StrategyState.MANAGING:
                await sm.force_squareoff()
        await self._redis.set_engine_status({
            "status": "FATAL_DISCONNECT",
            "timestamp": datetime.datetime.now(IST_TZ).isoformat(),
        })

    async def on_market_open(self) -> None:
        """9:15 AM: Reset all builders for new trading session."""
        for builder in self.candle_builders.values():
            builder.reset()
        # Clear any leftover SMs from previous session
        self.active_state_machines.clear()
        log.info("market_open_builders_reset", symbol_count=len(self.candle_builders))

    async def on_squareoff(self) -> None:
        """3:20 PM: Force close all active positions."""
        log.info("squareoff_start", active_sms=len(self.active_state_machines))
        for sm in list(self.active_state_machines.values()):
            await sm.force_squareoff()
        # Clean up closed SMs
        closed = [s for s, m in self.active_state_machines.items()
                  if m.state == StrategyState.CLOSED]
        for s in closed:
            del self.active_state_machines[s]

    async def on_order_postback(self, message: dict) -> None:
        """Route order postback to appropriate SM (Phase 3+ wires order_tracker)."""
        log.debug("order_postback_phase2_noop", order_id=message.get("order_id"))

    # ── Diagnostics ────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        warmed = sum(1 for b in self.candle_builders.values() if b.is_warmed_up)
        managing = sum(
            1 for sm in self.active_state_machines.values()
            if sm.state == StrategyState.MANAGING
        )
        return {
            "total_builders": len(self.candle_builders),
            "warmed_up": warmed,
            "warming_up": len(self.candle_builders) - warmed,
            "active_state_machines": len(self.active_state_machines),
            "managing_positions": managing,
            "total_signals": self._signal_count,
            "total_ticks": self._tick_count,
            "total_candles": self._candle_count,
        }
