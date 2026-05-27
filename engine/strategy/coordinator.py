"""
engine/strategy/coordinator.py — Central dispatcher for all ticks and postbacks.

Phase 4 additions over Phase 2:
  - inject_dependencies(): wire order_service, order_tracker, fill_timeout_manager
    and kite_client into every new SM and into the coordinator itself
  - on_order_postback(): real routing via order_tracker (was noop in Phase 2)
  - orphan_check(): detect stale positions on startup (spec §12.1)
  - reconcile_orders(): 5-minute safety net for missed WS postbacks (spec §12.2)
"""

from __future__ import annotations

import asyncio
import datetime
from typing import TYPE_CHECKING, Any

import pytz
import structlog

from engine.market.candle_builder import CandleBuilder, Candle
from engine.market import calendar as mkt_calendar
from engine.strategy import scanner
from engine.strategy.state_machine import SymbolStateMachine, StrategyState
from engine.strategy.second_spike_detector import SecondSpikeDetector, SecondSpikeEntry
from engine.store import sma_file_store
from app.core.config import settings

if TYPE_CHECKING:
    from engine.kite.client import AsyncKiteClient
    from engine.orders.fill_timeout import FillTimeoutManager
    from engine.orders.order_service import OrderService
    from engine.orders.order_tracker import OrderTracker
    from engine.store.db_writer import DbWriter
    from engine.store.redis_store import RedisStore

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
      - Route order postbacks to the correct SM via order_tracker
      - Orphan detection and 5-minute reconciliation
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
        self._accept_new_entries: bool = True
        self._monitoring_tick_sent_at: dict[str, float] = {}  # symbol → monotonic timestamp

        # Market direction gate: Nifty EMA
        # _nifty_ema tracks the rolling 20-period 5-min EWMA of Nifty 50.
        # Updated by _update_nifty_ema() on every Nifty candle close.
        self._nifty_ema: float | None = None
        self._nifty_ltp: float | None = None     # latest Nifty tick
        self._nifty_candle_builder: CandleBuilder | None = None
        self._vix_ltp: float | None = None       # latest India VIX tick

        # Phase 4: wired via inject_dependencies()
        self._order_service: "OrderService | None" = None
        self._order_tracker: "OrderTracker | None" = None
        self._fill_timeout: "FillTimeoutManager | None" = None
        self._kite: "AsyncKiteClient | None" = None

        # v3 NEW: Second spike detector (singleton per engine process)
        self.second_spike_detector = SecondSpikeDetector()

    # ── Dependency injection ─────────────────────────────────────────────────

    def inject_dependencies(
        self,
        order_service: "OrderService",
        order_tracker: "OrderTracker",
        fill_timeout_manager: "FillTimeoutManager",
        kite: "AsyncKiteClient | None" = None,
    ) -> None:
        """
        Wire live-mode dependencies into the coordinator.
        Called by runner.py after auth succeeds, before WS subscription.
        """
        self._order_service = order_service
        self._order_tracker = order_tracker
        self._fill_timeout = fill_timeout_manager
        self._kite = kite
        log.info(
            "coordinator_dependencies_injected",
            order_service=type(order_service).__name__,
            kite_wired=kite is not None,
        )

    def set_new_entries_enabled(self, enabled: bool) -> None:
        """Enable/disable fresh scanner-to-entry transitions (used by STOP/START control)."""
        self._accept_new_entries = enabled
        log.info("coordinator_new_entries_gate", enabled=enabled)

    # ── Market Gate: Nifty EMA ──────────────────────────────────────────────

    def _update_nifty_ema(self, nifty_ltp: float) -> None:
        """
        Update the rolling 5-minute Nifty EMA using EWMA.
        Called when a Nifty 50 tick is received (on each candle boundary we
        use the LTP at candle close for a clean per-bar EMA).

        EWMA: ema = alpha * price + (1 - alpha) * prev_ema
              alpha = 2 / (period + 1)
        """
        period = settings.NIFTY_EMA_PERIOD
        alpha = 2.0 / (period + 1)
        if self._nifty_ema is None:
            # Cold start: seed EMA with first observed price
            self._nifty_ema = nifty_ltp
        else:
            self._nifty_ema = alpha * nifty_ltp + (1.0 - alpha) * self._nifty_ema

        gate_open = nifty_ltp >= self._nifty_ema
        # Push to scanner module cache (sync — no await needed)
        scanner.update_market_gate(vix=self._vix_ltp, gate_open=gate_open)

        log.debug(
            "nifty_ema_updated",
            nifty_ltp=round(nifty_ltp, 2),
            nifty_ema=round(self._nifty_ema, 2),
            gate_open=gate_open,
            vix=self._vix_ltp,
        )

        # Persist to Redis for dashboard display and across restarts
        asyncio.create_task(
            self._persist_market_gate(nifty_ltp, gate_open),
            name="persist_market_gate",
        )

    async def _persist_market_gate(self, nifty_ltp: float, gate_open: bool) -> None:
        """Persist Nifty EMA + VIX to Redis (non-blocking — runs as a task)."""
        try:
            if self._nifty_ema is not None:
                await self._redis.set_nifty_ema(self._nifty_ema)
            await self._redis.set_nifty_ltp(nifty_ltp)
            if self._vix_ltp is not None:
                await self._redis.set_vix(self._vix_ltp)
        except Exception as exc:
            log.debug("market_gate_persist_failed", error=str(exc))

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
        """
        Load persisted SMA histories from disk file first, then Redis.
        Called at 09:00 AM pre-market BEFORE warmup_from_historical().

        Priority order:
          1. Disk file (./data/sma_histories.json.gz) — survives Redis restarts
          2. Redis volume_sma:{symbol} keys — 48h TTL fallback
          For each symbol, the source with MORE history wins.
        """
        # Step 1: Load from disk file (fastest, survives Redis restart)
        file_age = sma_file_store.get_file_age_hours()
        file_histories = await asyncio.to_thread(sma_file_store.load_sma_histories)
        if file_histories:
            log.info(
                "sma_file_histories_available",
                symbols=len(file_histories),
                file_age_hours=file_age,
            )

        loaded_from_file = 0
        loaded_from_redis = 0
        warming = 0

        for symbol, builder in self.candle_builders.items():
            file_hist = file_histories.get(symbol)
            redis_hist = await self._redis.load_volume_sma_history(symbol)

            # Pick the richer source (more history = better SMA accuracy)
            if file_hist and redis_hist:
                history = file_hist if len(file_hist) >= len(redis_hist) else redis_hist
                loaded_from_file += 1  # count as file since file triggered the choice
            elif file_hist:
                history = file_hist
                loaded_from_file += 1
            elif redis_hist:
                history = redis_hist
                loaded_from_redis += 1
            else:
                warming += 1
                continue

            builder.load_history(history)

        await self._redis.set_scanner_counts(
            loaded_from_file + loaded_from_redis, warming
        )
        log.info(
            "sma_history_loaded",
            from_file=loaded_from_file,
            from_redis=loaded_from_redis,
            warming=warming,
        )

    async def persist_sma_histories(self) -> None:
        """Persist SMA histories to BOTH Redis and disk file. Called at 15:25 PM session end."""
        import pytz as _pytz
        today_ist = datetime.datetime.now(_pytz.timezone("Asia/Kolkata")).date().isoformat()

        histories: dict[str, list[int]] = {}
        for symbol, builder in self.candle_builders.items():
            history = builder.volume_history_snapshot
            if history:
                histories[symbol] = history
                await self._redis.save_volume_sma_history(symbol, history)

        # Save to disk file with today's date as as_of_date.
        # Next morning warmup reads this date and fetches ONLY the gap days.
        if histories:
            await asyncio.to_thread(
                sma_file_store.save_sma_histories, histories, today_ist
            )

        log.info(
            "sma_history_persisted",
            symbol_count=len(histories),
            as_of_date=today_ist,
            saved_to_file=bool(histories),
        )

    # ── Tick Routing (HOT PATH) ────────────────────────────────────────────

    async def process_ticks(self, ticks: list[dict]) -> None:
        """
        Main tick processing loop. Called from KiteTicker thread via _dispatch().
        This is the innermost hot path — keep it lean.

        Per-tick: symbol lookup + CandleBuilder update + optional SM tick routing.
        Per-candle: scanner evaluation or SM on_candle routing.

        Live tick persistence: every call flushes all received symbols to Redis in one
        pipeline (no per-symbol round-trips), keeping livetick:* keys fresh for the
        dashboard's 1-second WebSocket tick_batch poll.
        """
        self._tick_count += len(ticks)

        # Accumulate (symbol, data) for a single pipeline flush at the end.
        # This replaces the old "every 50 ticks" throttle which starved the dashboard.
        live_tick_updates: list[tuple] = []

        for tick in ticks:
            token: int = tick.get("instrument_token", 0)

            # \u2500\u2500 Market Gate: route Nifty 50 and India VIX ticks separately \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
            # These index tokens are NOT in token_to_symbol (universe symbols only).
            # We update internal EMA/VIX state and skip all stock SM routing.
            if token == settings.NIFTY_INSTRUMENT_TOKEN:
                nifty_ltp = tick.get("last_price", 0.0)
                if nifty_ltp > 0:
                    self._nifty_ltp = nifty_ltp
                    # Update EWMA on every tick (updates gate on each bar for simplicity)
                    self._update_nifty_ema(nifty_ltp)
                continue

            if token == settings.VIX_INSTRUMENT_TOKEN:
                vix_ltp = tick.get("last_price", 0.0)
                if vix_ltp > 0:
                    self._vix_ltp = vix_ltp
                    # Also sync VIX into scanner cache directly
                    scanner.update_market_gate(
                        vix=self._vix_ltp,
                        gate_open=self._nifty_ltp is not None and (
                            self._nifty_ema is None or self._nifty_ltp >= self._nifty_ema
                        ),
                    )
                continue

            symbol = self.token_to_symbol.get(token)
            if symbol is None:
                continue

            ltp: float = tick.get("last_price", 0.0)
            cum_vol: int = tick.get("volume_traded", 0)
            ohlc = tick.get("ohlc", {})
            day_open = ohlc.get("open", 0.0) if ohlc else 0.0
            # prev_close = ohlc.close in Kite QUOTE mode ticks
            # This is the PREVIOUS DAY'S closing price — used for % change
            # to match the Kite app display (same reference as NSE official change%)
            prev_close = ohlc.get("close", 0.0) if ohlc else 0.0

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
            if sm is not None and sm.state in (
                StrategyState.SCAN_HIT,
                StrategyState.MONITORING,
                StrategyState.ACTION_PENDING,
                StrategyState.ACTION_PENDING_APPROVAL,
            ):
                await self._maybe_publish_monitoring_tick(
                    symbol, ltp, day_open, prev_close, cum_vol, builder, sm, exch_ts
                )
            if sm is not None and sm.state == StrategyState.MANAGING:
                await sm.on_tick(ltp, exch_ts)

            # Collect for pipeline flush (only if ltp is valid)
            if ltp > 0:
                live_tick_updates.append((
                    symbol, ltp, day_open, prev_close, cum_vol,
                    builder.current_volume, builder.volume_sma,
                ))

        # Flush all live tick updates in one Redis pipeline round-trip.
        # Avoids hundreds of individual SET calls (one per symbol per batch).
        if live_tick_updates:
            try:
                import json as _json
                _LIVETICK_TTL = 54000  # 15 hours — matches redis_store._TTL_LIVE_TICK
                now_iso = datetime.datetime.now(IST_TZ).isoformat(timespec="seconds")
                pipe = self._redis._r.pipeline(transaction=False)
                for sym, ltp, day_open, prev_close, cum_vol, min_vol, vol_sma in live_tick_updates:
                    # pct_chg uses prev_close (= ohlc.close from Kite tick)
                    # which is the PREVIOUS DAY'S closing price — matches Kite app display
                    ref = prev_close if prev_close > 0 else day_open
                    pct_chg = round(((ltp - ref) / ref * 100), 2) if ref > 0 else 0.0
                    payload: dict = {
                        "ltp": ltp,
                        "open": day_open,
                        "prev_close": prev_close,
                        "pct_chg": pct_chg,
                        "volume": cum_vol,
                        "minute_volume": min_vol,
                    }
                    if vol_sma:
                        payload["volume_sma_500"] = vol_sma
                        payload["relative_volume"] = round((min_vol or 0) / vol_sma, 2)
                    encoded = _json.dumps(payload)
                    # Primary: write to hash (O(1) HGETALL for dashboard)
                    pipe.hset("livetick_hash", sym, encoded)
                    # Legacy: per-symbol key (backward compat)
                    pipe.set(f"livetick:{sym}", encoded, ex=_LIVETICK_TTL)
                    pipe.set(f"ltp:{sym}", str(ltp))  # backward compat
                await pipe.execute()
            except Exception:
                pass  # Redis blip — dashboard will catch up on next tick batch

        # Always write last_tick_at — outside the symbol pipeline so this key is
        # updated even when no symbols had live_tick_updates this batch.
        try:
            _LIVETICK_TTL = 54000
            now_iso = datetime.datetime.now(IST_TZ).isoformat(timespec="seconds")
            await self._redis._r.set("engine:last_tick_at", now_iso, ex=_LIVETICK_TTL)
        except Exception:
            pass

    async def _maybe_publish_monitoring_tick(
        self,
        symbol: str,
        ltp: float,
        day_open: float,
        prev_close: float,
        cumulative_volume: int,
        builder: CandleBuilder,
        sm: SymbolStateMachine,
        exchange_ts: datetime.datetime,
    ) -> None:
        """Push sub-second live LTP/volume only for symbols the trader is watching.

        Throttle uses wall-clock monotonic time (not exchange_ts) to prevent
        flooding Redis pub/sub on reconnect when stale ticks arrive in bursts.
        """
        import time as _time
        now_mono = _time.monotonic()
        last_mono = self._monitoring_tick_sent_at.get(symbol)
        if last_mono is not None and (now_mono - last_mono) < 1.0:
            return
        self._monitoring_tick_sent_at[symbol] = now_mono

        con = sm.consolidation
        volume_sma = builder.volume_sma
        ref = prev_close if prev_close > 0 else day_open
        payload: dict[str, Any] = {
            "symbol": symbol,
            "ltp": ltp,
            "open": day_open,
            "prev_close": prev_close,
            "pct_chg": round(((ltp - ref) / ref * 100), 2) if ref > 0 else 0.0,
            "cumulative_volume": cumulative_volume,
            "volume_delta_1min": builder.current_volume,
            "volume_sma_500": volume_sma,
            "relative_volume": round(builder.current_volume / volume_sma, 2) if volume_sma else None,
            "state": sm.state.value,
            "timestamp": exchange_ts.isoformat(),
        }
        if con is not None:
            payload.update({
                "breakout_level": con.breakout_trigger_price,
                "swing_low": con.swing_low,
                "candle_count": con.candle_count,
                "volume_readings": con.volume_readings,
            })
        try:
            await self._redis.publish_monitoring_tick(payload)
        except Exception:
            pass

    async def _publish_candle_close(
        self,
        symbol: str,
        candle: Candle,
        builder: CandleBuilder | None,
        sm: SymbolStateMachine | None = None,
    ) -> None:
        """Publish a real completed candle for dashboard cells/charts."""
        volume_sma = builder.volume_sma if builder else None
        payload: dict[str, Any] = {
            "symbol": symbol,
            "timestamp": candle.timestamp.isoformat(),
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
            "volume": candle.volume,
            "turnover": candle.turnover,
            "volume_sma_500": volume_sma,
            "spike_multiple": round(candle.volume / volume_sma, 2) if volume_sma else None,
            "relative_volume": round(candle.volume / volume_sma, 2) if volume_sma else None,
            "state": sm.state.value if sm else "IDLE",
        }
        if sm and sm.consolidation:
            payload.update({
                "breakout_level": sm.consolidation.breakout_trigger_price,
                "swing_low": sm.consolidation.swing_low,
                "candle_count": sm.consolidation.candle_count,
                "volume_readings": sm.consolidation.volume_readings,
            })
        try:
            await self._redis.publish_candle_close(payload)
        except Exception:
            pass

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

        builder = self.candle_builders.get(symbol)
        try:
            await self._redis.append_recent_candle(
                symbol,
                candle,
                volume_sma_500=builder.volume_sma if builder else None,
            )
        except Exception:
            pass

        if symbol not in self.active_state_machines:
            # IDLE path: run Phase 1 scanner
            if not self._accept_new_entries:
                await self._publish_candle_close(symbol, candle, builder)
                return

            if not mkt_calendar.is_market_open():
                await self._publish_candle_close(symbol, candle, builder)
                return

            if builder is None:
                await self._publish_candle_close(symbol, candle, builder)
                return

            # v3 NEW: Track inter-spike consolidation low for ALL idle candles.
            # This keeps the SL anchor accurate for any eventual second-spike entry.
            self.second_spike_detector.update_inter_spike_low(symbol, candle.low)

            instrument_token = self.symbol_to_token.get(symbol, 0)

            # v3 NEW: Check for second-spike entry BEFORE running first-wave scanner.
            # If a prior spike record exists and today's candle meets all 7 conditions,
            # route directly to the second-spike entry path and skip the normal scanner.
            if self.second_spike_detector.has_record(symbol):
                volume_sma = builder.volume_sma
                if volume_sma and volume_sma > 0:
                    tick_size = await self._redis.get_tick_size(symbol)
                    second = self.second_spike_detector.evaluate_second_spike(
                        symbol=symbol,
                        candle_close=candle.close,
                        candle_open=candle.open,
                        candle_low=candle.low,
                        candle_volume=candle.volume,
                        candle_time=candle.timestamp,
                        volume_sma=volume_sma,
                        tick_size=tick_size if tick_size else 0.05,
                    )
                    if second is not None:
                        await self._handle_second_spike_entry(second, instrument_token)
                        await self._publish_candle_close(symbol, candle, builder)
                        return  # Do NOT run first-wave scanner on this candle

            impact = scanner.evaluate(candle, builder, instrument_token)

            if impact is not None:
                self._signal_count += 1
                # v3 NEW: Record this first spike for potential second-spike detection later.
                self.second_spike_detector.record_first_spike(impact)

                sm = self._create_sm(symbol, instrument_token)
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
                await self._publish_candle_close(symbol, candle, builder, sm)
            else:
                await self._publish_candle_close(symbol, candle, builder)
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
            await self._publish_candle_close(symbol, candle, builder, sm)

            # Cleanup CLOSED SMs
            if sm.state == StrategyState.CLOSED:
                del self.active_state_machines[symbol]
                log.debug("sm_cleaned_up", symbol=symbol)

    def _create_sm(self, symbol: str, instrument_token: int, is_second_spike: bool = False) -> SymbolStateMachine:
        """
        Create a SymbolStateMachine with all Phase 4 dependencies wired.
        Pass is_second_spike=True for second-spike direct entry SMs.
        """
        sm = SymbolStateMachine(
            symbol=symbol,
            instrument_token=instrument_token,
            redis_store=self._redis,
            db_writer=self._db,
            order_service=self._order_service,
            order_tracker=self._order_tracker,
            fill_timeout_manager=self._fill_timeout,
            is_second_spike=is_second_spike,
        )
        # Wire kite client and candle builder for pre-trade checks
        sm._kite = self._kite  # type: ignore[attr-defined]
        sm._candle_builder = self.candle_builders.get(symbol)  # type: ignore[attr-defined]
        return sm

    async def _handle_second_spike_entry(
        self,
        second: SecondSpikeEntry,
        instrument_token: int,
    ) -> None:
        """
        Direct entry path for second-spike signals. (v3 NEW)

        Bypasses the scan -> monitoring -> re-ignition cycle entirely because
        the inter-spike period already served as the dry-up phase.

        SL = second.stop_loss (= inter_spike_low - 1 tick).
        All other risk checks still run inside SM._trigger_entry().
        """
        symbol = second.symbol
        prior = second.prior_spike

        # Guard: don't create a second SM if one is already active (race condition)
        if symbol in self.active_state_machines:
            log.debug("second_spike_skipped_sm_already_active", symbol=symbol)
            self.second_spike_detector.clear(symbol)
            return

        # Create SM pre-loaded with the inter-spike SL — no dry-up phase needed
        sm = self._create_sm(symbol, instrument_token, is_second_spike=True)
        sm.set_second_spike_sl(
            stop_loss=second.stop_loss,
            prior_spike_time=prior.spike_time,
            prior_spike_high=prior.spike_high,
            prior_spike_low=prior.spike_low,
        )
        self.active_state_machines[symbol] = sm
        self._signal_count += 1

        # Trigger entry immediately on the second spike candle's close.
        # This calls the exact same _trigger_entry() used by the normal path,
        # so all pre-trade checks, position sizing, and order placement run.
        await sm._trigger_entry(second.entry_close, second.entry_time)

        # If entry was rejected or SM moved to CLOSED, clean up
        if sm.state == StrategyState.CLOSED:
            del self.active_state_machines[symbol]

        # Clear the prior spike record — this symbol has been acted on
        self.second_spike_detector.clear(symbol)

        log.info(
            "second_spike_entry_routed",
            symbol=symbol,
            entry_close=second.entry_close,
            stop_loss=second.stop_loss,
            vol_ratio=round(second.vol_ratio, 2),
            gap_minutes=round(second.gap_minutes, 1),
        )

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
        # v3 NEW: Reset second spike detector at end-of-day
        self.second_spike_detector.end_of_day_reset()

    # ── Order Postback Routing (Phase 4) ────────────────────────────────────

    async def on_order_postback(self, message: dict) -> None:
        """
        Route order postback from KiteTicker to order_tracker.
        order_tracker then calls the correct SM method (on_order_filled, on_sl_triggered...).
        """
        if self._order_tracker is None:
            log.debug("order_postback_no_tracker", order_id=message.get("order_id"))
            return

        await self._order_tracker.on_postback(message, self, self._db)

    # ── Orphan Detection (spec §12.1) ────────────────────────────────────────

    async def orphan_check(self, kite: "AsyncKiteClient") -> None:
        """
        Run after authentication, before market open.
        Detects stale positions from prior crashes and closes them.

        1. Any Kite open position with NO Redis state → close immediately
        2. Any Redis MANAGING state with NO Kite position → mark CLOSED_BROKER
        """
        log.info("orphan_check_start")
        try:
            positions_resp = await kite.positions()
            day_positions: list[dict] = positions_resp.get("day", [])
            net_positions: list[dict] = positions_resp.get("net", [])

            # Build set of symbols with non-zero NSE quantity
            kite_open: dict[str, int] = {}
            for pos in net_positions:
                sym = pos.get("tradingsymbol", "")
                qty = int(pos.get("quantity", 0))
                if qty != 0 and pos.get("exchange") == "NSE":
                    kite_open[sym] = qty

            # Check for orphans: Kite has position but no Redis state
            for sym, qty in kite_open.items():
                if sym not in self.active_state_machines:
                    log.warning(
                        "orphan_position_detected",
                        symbol=sym,
                        quantity=qty,
                        action="emergency_market_sell",
                    )
                    if self._order_service:
                        await self._order_service.place_exit_market(
                            sym, abs(qty), reason="orphan_close"
                        )
                    # Write to DB
                    try:
                        await self._db.write_order_event(
                            order_id=f"ORPHAN_{sym}",
                            symbol=sym,
                            event_type="ORPHAN_CLOSE",
                            event_time=datetime.datetime.now(IST_TZ),
                            status="ORPHAN",
                            raw_payload={"qty": qty},
                        )
                    except Exception:
                        pass

            # Check for ghost: Redis MANAGING but no Kite open position
            redis_states = await self._redis.get_all_strategy_states()
            for sym, state_data in redis_states.items():
                if state_data.get("state") == "MANAGING" and sym not in kite_open:
                    log.warning(
                        "ghost_managing_state_detected",
                        symbol=sym,
                        action="clearing_redis_state",
                    )
                    # Try to get exit price from Kite trades
                    exit_price: float | None = None
                    try:
                        all_trades = await kite.trades()
                        for t in reversed(all_trades):
                            if t.get("tradingsymbol") == sym:
                                exit_price = float(t.get("average_price", 0.0))
                                break
                    except Exception:
                        pass

                    await self._redis.clear_strategy_state(sym)
                    await self._redis.clear_position(sym)
                    log.info(
                        "ghost_state_cleared",
                        symbol=sym,
                        recovered_exit_price=exit_price,
                    )

        except Exception as exc:
            log.error("orphan_check_failed", error=str(exc), exc_info=True)

    # ── 5-Minute Reconciliation (spec §12.2) ────────────────────────────────

    async def reconcile_orders(self, kite: "AsyncKiteClient") -> None:
        """
        Called every 5 minutes during market hours.
        Detects missed WS postbacks and routes them to the correct SM.

        1. MANAGING SMs: check if SL was triggered silently
        2. ACTION_PENDING SMs: check if fill arrived without postback
        """
        if not self.active_state_machines:
            return

        try:
            all_orders: list[dict] = await kite.orders()
        except Exception as exc:
            log.warning("reconcile_orders_fetch_failed", error=str(exc))
            return

        order_map: dict[str, dict] = {o["order_id"]: o for o in all_orders}

        for symbol, sm in list(self.active_state_machines.items()):

            # ── MANAGING: check if SL was silently triggered ─────────────
            if sm.state == StrategyState.MANAGING and sm.position is not None:
                # Exit-in-progress path: reconcile MARKET exit fill/reject.
                exit_id = sm.position.exit_order_id
                if sm.position._exit_initiated and exit_id and exit_id in order_map:
                    exit_order = order_map[exit_id]
                    exit_status = exit_order.get("status", "")

                    if exit_status == "COMPLETE":
                        avg = float(exit_order.get("average_price", 0.0))
                        reason = sm.position.exit_reason or "CLOSED_MANUAL"
                        log.warning(
                            "reconcile_exit_filled_missed",
                            symbol=symbol,
                            exit_id=exit_id,
                            avg_price=avg,
                            reason=reason,
                        )
                        await sm._close_position(avg, exit_id, reason)
                        continue

                    if exit_status in ("REJECTED", "CANCELLED", "CANCELLED AMO"):
                        reason = sm.position.exit_reason or "CLOSED_ERROR"
                        log.critical(
                            "reconcile_exit_rejected_retrying",
                            symbol=symbol,
                            exit_id=exit_id,
                            status=exit_status,
                            reason=reason,
                        )
                        if self._order_service:
                            retry_id = await self._order_service.place_exit_market(
                                symbol,
                                sm.position.quantity,
                                reason=reason,
                            )
                            if retry_id:
                                sm.position.exit_order_id = retry_id
                                if self._order_tracker is not None:
                                    self._order_tracker.register_exit(retry_id, symbol, reason)
                        continue

                sl_id = sm.position.sl_order_id
                if sl_id and sl_id in order_map:
                    sl_order = order_map[sl_id]
                    sl_status = sl_order.get("status", "")

                    if sl_status == "COMPLETE" and not sm.position._exit_initiated:
                        avg = float(sl_order.get("average_price", 0.0))
                        log.warning(
                            "reconcile_sl_triggered_missed",
                            symbol=symbol,
                            sl_id=sl_id,
                            avg_price=avg,
                        )
                        await sm.on_sl_triggered(sl_id, avg)

                    elif sl_status == "REJECTED":
                        log.critical(
                            "reconcile_sl_rejected_emergency_close",
                            symbol=symbol,
                            sl_id=sl_id,
                        )
                        if self._order_service:
                            await self._order_service.place_exit_market(
                                symbol, sm.position.quantity, reason="sl_rejected"
                            )

            # ── ACTION_PENDING: check if fill was missed ──────────────────
            elif sm.state == StrategyState.ACTION_PENDING and sm._pending_order_id:
                entry_id = sm._pending_order_id
                if entry_id in order_map:
                    entry_order = order_map[entry_id]
                    entry_status = entry_order.get("status", "")

                    if entry_status == "COMPLETE":
                        avg = float(entry_order.get("average_price", 0.0))
                        filled = int(entry_order.get("filled_quantity", 0))
                        fill_ts_raw = entry_order.get("exchange_update_timestamp")
                        try:
                            fill_ts = datetime.datetime.fromisoformat(str(fill_ts_raw)) if fill_ts_raw else datetime.datetime.now(IST_TZ)
                        except (ValueError, TypeError):
                            fill_ts = datetime.datetime.now(IST_TZ)

                        log.warning(
                            "reconcile_entry_filled_missed",
                            symbol=symbol,
                            order_id=entry_id,
                            avg_price=avg,
                        )
                        await sm.on_order_filled(entry_id, avg, filled, fill_ts)

                    elif entry_status in ("REJECTED", "CANCELLED"):
                        log.warning(
                            "reconcile_entry_rejected",
                            symbol=symbol,
                            order_id=entry_id,
                            status=entry_status,
                        )
                        await sm.on_order_rejected(
                            entry_id, entry_order.get("status_message", "")
                        )

            # Cleanup CLOSED SMs discovered during reconciliation.
            if sm.state == StrategyState.CLOSED:
                del self.active_state_machines[symbol]

        log.debug("reconcile_done", active_sms=len(self.active_state_machines))

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
