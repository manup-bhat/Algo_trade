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
from engine.strategy import scanner
from engine.strategy.state_machine import SymbolStateMachine, StrategyState
from engine.core.strategy_router import StrategyRouter
from engine.strategies.ivbs.strategy import IVBSStrategy
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

    def __init__(
        self,
        redis_store: "RedisStore",
        db_writer: "DbWriter",
        strategy_router: "StrategyRouter | None" = None,
    ) -> None:
        self._redis = redis_store
        self._db = db_writer
        self.candle_builders: dict[str, CandleBuilder] = {}
        self.token_to_symbol: dict[int, str] = {}
        self.symbol_to_token: dict[str, int] = {}
        self._tick_count: int = 0
        self._candle_count: int = 0
        self._reconcile_count: int = 0
        self._last_reconcile_at: str | None = None
        self._accept_new_entries: bool = True
        self._monitoring_tick_sent_at: dict[str, float] = {}  # symbol → monotonic timestamp

        # Market direction gate: Nifty EMA
        # _nifty_ema tracks the rolling 20-period 5-min EWMA of Nifty 50.
        # Updated by _update_nifty_ema() on every Nifty candle close.
        self._nifty_ema: float | None = None
        self._nifty_ltp: float | None = None     # latest Nifty tick
        self._nifty_candle_builder: CandleBuilder | None = None
        self._vix_ltp: float | None = None       # latest India VIX tick

        # Wired via inject_dependencies()
        self._order_service: "OrderService | None" = None
        self._order_tracker: "OrderTracker | None" = None
        self._fill_timeout: "FillTimeoutManager | None" = None
        self._kite: "AsyncKiteClient | None" = None

        # ── Strategy plugins ────────────────────────────────────────
        # The coordinator is a pure data router; strategy decisions live in
        # BaseStrategy plugins behind the StrategyRouter. If no router is
        # supplied, default to a single IVBS strategy (legacy behavior).
        if strategy_router is None:
            strategy_router = StrategyRouter()
            strategy_router.register(IVBSStrategy("ivbs", redis_store, db_writer))
        self.strategy_router = strategy_router
        # Primary IVBS strategy reference for backward-compatible proxies
        # (active_state_machines / second_spike_detector) used by the engine-side
        # reconcile / orphan / dashboard-publish helpers below.
        self._ivbs = strategy_router.get("ivbs") or (
            strategy_router.strategies[0] if strategy_router.strategies else None
        )

    # ── Backward-compatible proxies to the primary strategy ───────────────

    @property
    def active_state_machines(self) -> dict[str, SymbolStateMachine]:
        """Proxy to the primary strategy's live state machines (legacy API)."""
        if self._ivbs is None:
            return {}
        return self._ivbs.active_state_machines

    @property
    def second_spike_detector(self):
        """Proxy to the primary strategy's second-spike detector (legacy API)."""
        return self._ivbs.second_spike_detector if self._ivbs is not None else None

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
        # Propagate execution deps to all registered strategies.
        self.strategy_router.inject_execution(
            order_service, order_tracker, fill_timeout_manager, kite
        )
        log.info(
            "coordinator_dependencies_injected",
            order_service=type(order_service).__name__,
            kite_wired=kite is not None,
        )

    def set_new_entries_enabled(self, enabled: bool) -> None:
        """Enable/disable fresh scanner-to-entry transitions (used by STOP/START control)."""
        self._accept_new_entries = enabled
        self.strategy_router.set_new_entries_enabled(enabled)
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

    def apply_watchlist(
        self,
        symbols: list[str],
        resolve: Any,  # Callable[[str], InstrumentInfo | None]
        sma_period: int = 500,
    ) -> tuple[list[int], list[int]]:
        """Reconcile live CandleBuilders to match ``symbols`` (hot watchlist edit).

        ``resolve(symbol)`` returns an InstrumentInfo (with ``instrument_token``)
        or None for unknown symbols, which are skipped. A symbol currently held
        by any strategy (open position / live setup) is never removed, so an
        edit can't strand an in-flight trade.

        Returns ``(added_tokens, removed_tokens)`` for the caller to apply to the
        WebSocket subscription.
        """
        desired = list(dict.fromkeys(symbols))  # de-dupe, preserve order
        desired_set = set(desired)
        current_set = set(self.candle_builders.keys())

        added_tokens: list[int] = []
        removed_tokens: list[int] = []
        skipped: list[str] = []

        for sym in desired:
            if sym in current_set:
                continue
            info = resolve(sym)
            if info is None:
                skipped.append(sym)
                continue
            self.candle_builders[sym] = CandleBuilder(sym, sma_period)
            self.token_to_symbol[info.instrument_token] = sym
            self.symbol_to_token[sym] = info.instrument_token
            added_tokens.append(info.instrument_token)

        for sym in current_set - desired_set:
            if self.strategy_router.any_strategy_has_active_symbol(sym):
                skipped.append(sym)  # keep — trade/setup in flight
                continue
            token = self.symbol_to_token.pop(sym, None)
            self.candle_builders.pop(sym, None)
            if token is not None:
                self.token_to_symbol.pop(token, None)
                removed_tokens.append(token)

        log.info(
            "coordinator_watchlist_applied",
            added=len(added_tokens),
            removed=len(removed_tokens),
            skipped=len(skipped),
            total=len(self.candle_builders),
        )
        return added_tokens, removed_tokens

    async def warm_builders(self, symbols: list[str]) -> None:
        """Best-effort SMA warm for freshly added symbols from persisted Redis history."""
        for sym in symbols:
            builder = self.candle_builders.get(sym)
            if builder is None:
                continue
            try:
                history = await self._redis.load_volume_sma_history(sym)
                if history:
                    builder.load_history(history)
            except Exception as exc:  # pragma: no cover - best effort
                log.warning("watchlist_warm_failed", symbol=sym, error=str(exc))

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

            # Per-tick routing: publish monitoring ticks for pre-entry states
            # (dashboard) and delegate MANAGING management to the owning strategy.
            sm = self.active_state_machines.get(symbol)
            if sm is not None:
                if sm.state in (
                    StrategyState.SCAN_HIT,
                    StrategyState.MONITORING,
                    StrategyState.ACTION_PENDING,
                    StrategyState.ACTION_PENDING_APPROVAL,
                ):
                    await self._maybe_publish_monitoring_tick(
                        symbol, ltp, day_open, prev_close, cum_vol, builder, sm, exch_ts
                    )
                elif sm.state == StrategyState.MANAGING:
                    await self.strategy_router.on_tick(symbol, ltp, exch_ts)

            # Collect for pipeline flush (only if ltp is valid)
            if ltp > 0:
                live_tick_updates.append((
                    symbol, ltp, day_open, prev_close, cum_vol,
                    builder.current_volume, builder.volume_sma,
                ))

        # Flush all live tick updates via RedisStore (one pipeline round-trip).
        # flush_live_ticks() also sets engine:last_tick_at inside the same pipeline.
        now_iso = datetime.datetime.now(IST_TZ).isoformat(timespec="seconds")
        if live_tick_updates:
            try:
                await self._redis.flush_live_ticks(live_tick_updates, now_iso)
            except Exception:
                pass  # Redis blip — dashboard will catch up on next tick batch
        else:
            # No symbols this batch — still update the staleness timestamp
            try:
                await self._redis.set_last_tick_at(now_iso)
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
        Called when a 1-minute candle completes. Persists engine-level state,
        delegates strategy decisions to the StrategyRouter, then publishes the
        candle close (with any active-SM overlay) for the dashboard.
        """
        # Engine-level: persist last LTP + recent candle for dashboard/entry logic.
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

        instrument_token = self.symbol_to_token.get(symbol, 0)

        # Capture the SM before/after routing so the dashboard publish reflects
        # the correct state even when a strategy closes (and removes) the SM on
        # this candle (sm_after is None → fall back to the pre-routing reference).
        sm_before = self.active_state_machines.get(symbol)
        await self.strategy_router.on_candle(symbol, candle, builder, instrument_token)
        sm_after = self.active_state_machines.get(symbol)
        sm_for_publish = sm_after if sm_after is not None else sm_before

        await self._publish_candle_close(symbol, candle, builder, sm_for_publish)



    async def on_websocket_connected(self) -> None:
        """Bug 4 fix: reset all baselines on every WS connect."""
        for builder in self.candle_builders.values():
            builder.reset_cumulative_baseline()
        log.info("ws_connected_baselines_reset", count=len(self.candle_builders))

    async def on_websocket_reconnect(self) -> None:
        log.warning("ws_reconnecting_in_progress")

    async def on_fatal_disconnect(self) -> None:
        """Emergency: force squareoff all open positions (delegated), set status."""
        log.critical("fatal_ws_disconnect_squaring_off_all")
        await self.strategy_router.on_fatal_disconnect()
        await self._redis.set_engine_status({
            "status": "FATAL_DISCONNECT",
            "timestamp": datetime.datetime.now(IST_TZ).isoformat(),
        })

    async def on_market_open(self) -> None:
        """9:15 AM: Reset all builders, then let strategies reset session state."""
        for builder in self.candle_builders.values():
            builder.reset()
        await self.strategy_router.on_market_open()
        log.info("market_open_builders_reset", symbol_count=len(self.candle_builders))

    async def on_squareoff(self) -> None:
        """3:20 PM: Force close all active positions (delegated to strategies)."""
        await self.strategy_router.on_squareoff()

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

                    # Close the open DB trade record so it doesn't stay OPEN forever
                    try:
                        position_data = state_data.get("position") or {}
                        trade_id = position_data.get("trade_id")
                        if trade_id is not None:
                            from app.models.db.trade import TradeStatus
                            await self._db.close_trade(
                                trade_id=trade_id,
                                exit_time=datetime.datetime.now(IST_TZ),
                                exit_price=exit_price or 0.0,
                                status=TradeStatus.CLOSED_BROKER,
                            )
                    except Exception as _db_exc:
                        log.warning("ghost_trade_close_db_failed", symbol=sym, error=str(_db_exc))

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
        self._reconcile_count += 1
        self._last_reconcile_at = datetime.datetime.now(IST_TZ).isoformat(timespec="seconds")
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
        combined = self.strategy_router.get_combined_stats()
        active = managing = signals = 0
        for s in combined.get("strategies", {}).values():
            active += s.get("active_state_machines", 0)
            managing += s.get("managing_positions", 0)
            signals += s.get("total_signals", 0)
        return {
            "total_builders": len(self.candle_builders),
            "warmed_up": warmed,
            "warming_up": len(self.candle_builders) - warmed,
            "active_state_machines": active,
            "managing_positions": managing,
            "total_signals": signals,
            "total_ticks": self._tick_count,
            "total_candles": self._candle_count,
            "reconcile_count": self._reconcile_count,
            "last_reconcile_at": self._last_reconcile_at,
        }
