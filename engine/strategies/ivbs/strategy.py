"""
engine/strategies/ivbs/strategy.py — IVBS plugin (BaseStrategy implementation).

This holds all IVBS-specific decision logic that previously lived inside the
Coordinator (scanner dispatch, second-spike & re-entry detection, per-symbol
state-machine lifecycle). The Coordinator now delegates to this via the
StrategyRouter; adding another strategy requires no coordinator change.

Behavior is byte-for-byte equivalent to the pre-refactor coordinator paths — the
same scanner, SymbolStateMachine, SecondSpikeDetector and abandoned_setup_tracker
are used, just owned here instead of by the engine core.

NOTE (migration): scanner / state_machine / second_spike_detector /
abandoned_setup_tracker still live under engine/strategy/* and are imported from
there. A later cleanup phase physically relocates them under this package with
re-export shims. abandoned_setup_tracker remains a module-level singleton for now
(the SymbolStateMachine writes to it in _abandon()); there is exactly one
IVBSStrategy instance so behavior is unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from engine.core.base_strategy import BaseStrategy
from engine.market import calendar as mkt_calendar
from engine.strategies.ivbs import scanner
from engine.strategies.ivbs.abandoned_setup_tracker import AbandonedRecord, abandoned_setup_tracker
from engine.strategies.ivbs.second_spike_detector import SecondSpikeDetector, SecondSpikeEntry
from engine.strategies.ivbs.state_machine import StrategyState, SymbolStateMachine

if TYPE_CHECKING:
    import datetime

    from engine.market.candle_builder import Candle, CandleBuilder
    from engine.store.db_writer import DbWriter
    from engine.store.redis_store import RedisStore

log = structlog.get_logger(__name__)


class IVBSStrategy(BaseStrategy):
    """Institutional Volume Breakout Strategy as a plugin."""

    def __init__(
        self,
        strategy_id: str,
        redis_store: "RedisStore",
        db_writer: "DbWriter",
    ) -> None:
        super().__init__(strategy_id, redis_store, db_writer)
        # Per-symbol state machines (one per active setup).
        self.active_state_machines: dict[str, SymbolStateMachine] = {}
        # v3: second-spike detector (per strategy instance).
        self.second_spike_detector = SecondSpikeDetector()
        self._signal_count: int = 0

    @property
    def signal_count(self) -> int:
        return self._signal_count

    # ── Candle routing (was Coordinator._on_candle_complete decision logic) ──

    async def on_candle(
        self,
        symbol: str,
        candle: "Candle",
        builder: "CandleBuilder",
        instrument_token: int,
    ) -> None:
        if symbol not in self.active_state_machines:
            # ── IDLE path: run Phase 1 scanner (+ re-entry / second-spike) ──
            if not self._accept_new_entries:
                return
            if not mkt_calendar.is_market_open(candle.timestamp):
                return
            if builder is None:
                return

            # v3: track inter-spike consolidation low for a later second spike.
            self.second_spike_detector.update_inter_spike_low(symbol, candle.low)
            # track price low for abandoned setups (re-entry system).
            abandoned_setup_tracker.update_low(symbol, candle.low)

            # Re-entry after abandonment (highest priority idle path).
            if abandoned_setup_tracker.has_record(symbol):
                volume_sma = builder.volume_sma
                if volume_sma and volume_sma > 0:
                    is_re_entry = abandoned_setup_tracker.evaluate(
                        symbol=symbol,
                        candle_open=candle.open,
                        candle_high=candle.high,
                        candle_low=candle.low,
                        candle_close=candle.close,
                        candle_volume=candle.volume,
                        candle_time=candle.timestamp,
                        volume_sma=volume_sma,
                    )
                    if is_re_entry:
                        rec = abandoned_setup_tracker.get_impact_data(symbol)
                        if rec is not None:
                            await self._handle_re_entry(
                                symbol=symbol,
                                instrument_token=instrument_token,
                                candle=candle,
                                rec=rec,
                                builder=builder,
                            )
                        return  # Do NOT run second-spike or first-wave scanner

            # v3: second-spike entry before first-wave scanner.
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
                        await self._handle_second_spike_entry(
                            second, instrument_token, builder
                        )
                        return  # Do NOT run first-wave scanner on this candle

            impact = scanner.evaluate(candle, builder, instrument_token)
            if impact is not None:
                self._signal_count += 1
                # v3: record this first spike for potential second-spike detection.
                self.second_spike_detector.record_first_spike(impact)

                sm = self._create_sm(symbol, instrument_token, builder)
                self.active_state_machines[symbol] = sm
                await sm.on_scan_hit(impact)

                if sm._signal_id:
                    try:
                        await self._db.update_signal_progression(
                            sm._signal_id, progressed_to_monitor=True
                        )
                    except Exception:
                        pass
        else:
            # ── Non-IDLE path: route to existing SM ──
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

    # ── Per-tick management (MANAGING only) ──────────────────────────────────

    async def on_tick(
        self,
        symbol: str,
        ltp: float,
        exchange_ts: "datetime.datetime",
    ) -> None:
        sm = self.active_state_machines.get(symbol)
        if sm is not None and sm.state == StrategyState.MANAGING:
            await sm.on_tick(ltp, exchange_ts)

    # ── SM factory + direct-entry handlers (moved from Coordinator) ──────────

    def _create_sm(
        self,
        symbol: str,
        instrument_token: int,
        builder: "CandleBuilder | None",
        is_second_spike: bool = False,
    ) -> SymbolStateMachine:
        """Create a SymbolStateMachine with all execution dependencies wired."""
        sm = SymbolStateMachine(
            symbol=symbol,
            instrument_token=instrument_token,
            redis_store=self._redis,
            db_writer=self._db,
            order_service=self._order_service,
            order_tracker=self._order_tracker,
            fill_timeout_manager=self._fill_timeout,
            is_second_spike=is_second_spike,
            strategy_id=self.strategy_id,
        )
        sm._kite = self._kite  # type: ignore[attr-defined]
        sm._candle_builder = builder  # type: ignore[attr-defined]
        return sm

    async def _handle_second_spike_entry(
        self,
        second: SecondSpikeEntry,
        instrument_token: int,
        builder: "CandleBuilder | None",
    ) -> None:
        """Direct entry path for second-spike signals (v3). Bypasses dry-up cycle."""
        symbol = second.symbol
        prior = second.prior_spike

        if symbol in self.active_state_machines:
            log.debug("second_spike_skipped_sm_already_active", symbol=symbol)
            self.second_spike_detector.clear(symbol)
            return

        sm = self._create_sm(symbol, instrument_token, builder, is_second_spike=True)
        sm.set_second_spike_sl(
            stop_loss=second.stop_loss,
            prior_spike_time=prior.spike_time,
            prior_spike_high=prior.spike_high,
            prior_spike_low=prior.spike_low,
        )
        self.active_state_machines[symbol] = sm
        self._signal_count += 1

        await sm._trigger_entry(second.entry_close, second.entry_time)

        if sm.state == StrategyState.CLOSED:
            del self.active_state_machines[symbol]

        self.second_spike_detector.clear(symbol)

        log.info(
            "second_spike_entry_routed",
            symbol=symbol,
            entry_close=second.entry_close,
            stop_loss=second.stop_loss,
            vol_ratio=round(second.vol_ratio, 2),
            gap_minutes=round(second.gap_minutes, 1),
        )

    async def _handle_re_entry(
        self,
        symbol: str,
        instrument_token: int,
        candle: "Candle",
        rec: AbandonedRecord,
        builder: "CandleBuilder | None",
    ) -> None:
        """Direct entry path for re-entry after an abandoned setup (v3)."""
        if symbol in self.active_state_machines:
            log.debug("re_entry_skipped_sm_already_active", symbol=symbol)
            abandoned_setup_tracker.clear(symbol)
            return

        try:
            tick_size = await self._redis.get_tick_size(symbol)
            if not tick_size:
                tick_size = 0.05
        except Exception:
            tick_size = 0.05

        sm = self._create_sm(symbol, instrument_token, builder, is_second_spike=False)
        sm.set_second_spike_sl(
            stop_loss=round(rec.inter_session_low - tick_size, 2),
            prior_spike_time=rec.abandon_time,
            prior_spike_high=rec.impact_candle_high,
            prior_spike_low=rec.impact_candle_low,
        )
        self.active_state_machines[symbol] = sm
        self._signal_count += 1

        await sm._trigger_entry(candle.close, candle.timestamp)

        if sm.state == StrategyState.CLOSED:
            del self.active_state_machines[symbol]

        log.info(
            "re_entry_routed",
            symbol=symbol,
            entry_close=candle.close,
            original_reason=rec.abandonment_reason,
            reentry_count=rec.reentry_count,
            inter_session_low=rec.inter_session_low,
        )

    # ── Lifecycle hooks ──────────────────────────────────────────────────────

    async def on_market_open(self) -> None:
        """09:15 — clear leftover SMs and reset the second-spike detector."""
        self.active_state_machines.clear()
        self.second_spike_detector.end_of_day_reset()
        log.info("ivbs_market_open_reset")

    async def on_squareoff(self) -> None:
        """15:20 — force close all active positions."""
        log.info("ivbs_squareoff_start", active_sms=len(self.active_state_machines))
        for sm in list(self.active_state_machines.values()):
            await sm.force_squareoff()
        closed = [
            s for s, m in self.active_state_machines.items()
            if m.state == StrategyState.CLOSED
        ]
        for s in closed:
            del self.active_state_machines[s]
        self.second_spike_detector.end_of_day_reset()

    async def on_fatal_disconnect(self) -> None:
        """WS reconnection exhausted — force squareoff only MANAGING positions."""
        for sm in list(self.active_state_machines.values()):
            if sm.state == StrategyState.MANAGING:
                await sm.force_squareoff()

    async def on_order_postback(self, message: dict[str, Any]) -> None:
        """Route a Kite order postback through this strategy's order tracker.

        Dormant in Phase 2 (the coordinator drives postbacks via order_tracker);
        provided for the future tag-based routing path. IVBS satisfies the
        order_tracker "owner" contract (has active_state_machines + _order_service).
        """
        if self._order_tracker is None:
            return
        await self._order_tracker.on_postback(message, self, self._db)

    # ── Queries ──────────────────────────────────────────────────────────────

    def is_symbol_active(self, symbol: str) -> bool:
        return symbol in self.active_state_machines

    def get_stats(self) -> dict[str, Any]:
        managing = sum(
            1 for sm in self.active_state_machines.values()
            if sm.state == StrategyState.MANAGING
        )
        return {
            "active_state_machines": len(self.active_state_machines),
            "managing_positions": managing,
            "total_signals": self._signal_count,
        }
