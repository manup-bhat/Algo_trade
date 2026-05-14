"""
engine/strategy/state_machine.py — Per-symbol strategy FSM with ALL 4 bugs fixed.

States: IDLE → SCAN_HIT → MONITORING → ACTION_PENDING → MANAGING → CLOSED

CRITICAL BUG FIXES (see IVBS_Final_Spec.md Part 8):
  Bug 1: Breakout level check uses PRE-UPDATE consolidation.high (snapshot before update)
  Bug 2: Volume spike check uses PRE-UPDATE prev_volumes (snapshot before update)
  Bug 3: Swing low uses candle wick LOW, not close
  Bug 4: Reconnect baseline reset (in candle_builder.py — already fixed in Phase 1)

All four bugs have mandatory unit test regression coverage in test_state_machine.py.
"""

from __future__ import annotations

import asyncio
import datetime
import enum
import statistics
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pytz
import structlog

from app.core.config import settings
from engine.strategy.scanner import ImpactCandle

if TYPE_CHECKING:
    from engine.store.redis_store import RedisStore
    from engine.store.db_writer import DbWriter
    from engine.orders.order_service import OrderService
    from engine.orders.order_tracker import OrderTracker
    from engine.orders.fill_timeout import FillTimeoutManager

log = structlog.get_logger(__name__)
IST_TZ = pytz.timezone("Asia/Kolkata")


# ─────────────────────────────────────────────────────────────────────────────
# State Enum
# ─────────────────────────────────────────────────────────────────────────────

class StrategyState(str, enum.Enum):
    IDLE = "IDLE"
    SCAN_HIT = "SCAN_HIT"
    MONITORING = "MONITORING"
    ACTION_PENDING = "ACTION_PENDING"
    MANAGING = "MANAGING"
    CLOSED = "CLOSED"


# ─────────────────────────────────────────────────────────────────────────────
# Data Classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ConsolidationData:
    """
    Tracks the dry-up consolidation zone after an impact candle.

    BUG 3 FIX: update() uses the wick LOW (candle low), not the candle close,
    for the swing_low calculation. The SL is placed at the wick bottom because
    institutions probe below close levels to trigger retail stops.
    """
    start_time: datetime.datetime
    high: float              # Highest point in consolidation zone (breakout trigger)
    low: float               # Lowest point in zone (informational)
    swing_low: float         # Wick-based swing low (used for SL placement)
    candle_count: int = 0
    volume_readings: list[int] = field(default_factory=list)

    @property
    def breakout_trigger_price(self) -> float:
        """Price that must be broken for re-ignition. Uses the HIGHEST of all candles."""
        return self.high

    @property
    def avg_volume(self) -> float:
        """Average volume of dry-up candles accumulated so far."""
        return statistics.mean(self.volume_readings) if self.volume_readings else 0.0

    def update(self, h: float, l: float, c: float, volume: int) -> None:
        """
        Absorb a new dry-up candle.

        BUG 3 FIX: swing_low uses `l` (candle wick low), NOT `c` (close).
        The API spec and strategy design both require wick-based swing lows.
        """
        self.candle_count += 1
        self.high = max(self.high, h)
        self.low = min(self.low, l)
        self.swing_low = min(self.swing_low, l)   # BUG 3 FIX: wick low
        self.volume_readings.append(volume)

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_time": self.start_time.isoformat(),
            "high": self.high,
            "low": self.low,
            "swing_low": self.swing_low,
            "breakout_trigger_price": self.breakout_trigger_price,
            "candle_count": self.candle_count,
            "volume_readings": self.volume_readings,
        }


@dataclass
class OpenPosition:
    """State of an open MANAGING position."""
    trade_id: int | None
    entry_price: float
    quantity: int
    initial_sl: float
    current_sl: float
    risk_per_share: float
    risk_amount: float
    target_1r2: float
    target_1r3: float
    target_1r4: float
    entry_order_id: str
    sl_order_id: str | None = None
    margin_blocked: float = 0.0
    exit_order_id: str | None = None
    exit_reason: str | None = None
    cost_trailed: bool = False
    profit_locked: bool = False
    _exit_initiated: bool = False
    max_favorable_excursion: float | None = None
    max_adverse_excursion: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "entry_price": self.entry_price,
            "quantity": self.quantity,
            "initial_sl": self.initial_sl,
            "current_sl": self.current_sl,
            "risk_per_share": self.risk_per_share,
            "risk_amount": self.risk_amount,
            "target_1r2": self.target_1r2,
            "target_1r3": self.target_1r3,
            "target_1r4": self.target_1r4,
            "margin_blocked": self.margin_blocked,
            "exit_order_id": self.exit_order_id,
            "exit_reason": self.exit_reason,
            "cost_trailed": self.cost_trailed,
            "profit_locked": self.profit_locked,
        }


# ─────────────────────────────────────────────────────────────────────────────
# State Machine
# ─────────────────────────────────────────────────────────────────────────────

class SymbolStateMachine:
    """
    Per-symbol strategy lifecycle manager.

    One instance per scan hit. Created by coordinator when Phase 1 scanner fires.
    Destroyed (removed from coordinator.active_state_machines) when state == CLOSED.

    Thread safety: All methods are async and must be called from the asyncio event loop.
    The coordinator guarantees this — it uses asyncio.run_coroutine_threadsafe() from
    the KiteTicker thread.

    Paper trade mode: When settings.PAPER_TRADE=True:
      - Entry is simulated immediately at limit_price × 1.001
      - No Kite API calls are made
      - SL/target checks happen against live LTP in on_tick()
    """

    def __init__(
        self,
        symbol: str,
        instrument_token: int,
        redis_store: "RedisStore",
        db_writer: "DbWriter",
        order_service: "OrderService | None" = None,
        order_tracker: "OrderTracker | None" = None,
        fill_timeout_manager: "FillTimeoutManager | None" = None,
    ) -> None:
        self.symbol = symbol
        self.instrument_token = instrument_token
        self._redis = redis_store
        self._db = db_writer
        self._order_service = order_service
        self._order_tracker = order_tracker
        self._fill_timeout = fill_timeout_manager

        self.state: StrategyState = StrategyState.IDLE
        self.impact_candle: ImpactCandle | None = None
        self.consolidation: ConsolidationData | None = None
        self.position: OpenPosition | None = None
        self._pending_order_id: str | None = None
        self._signal_id: int | None = None
        self._abandonment_reason: str | None = None

    # ── Phase 1: Scan Hit ─────────────────────────────────────────────────────

    async def on_scan_hit(self, impact_candle: ImpactCandle) -> None:
        """
        Called by coordinator when Phase 1 scanner fires.
        Transitions IDLE → SCAN_HIT.
        """
        if self.state != StrategyState.IDLE:
            log.warning(
                "scan_hit_non_idle",
                symbol=self.symbol,
                current_state=self.state,
            )
            return

        self.impact_candle = impact_candle
        self.consolidation = ConsolidationData(
            start_time=impact_candle.time,
            high=impact_candle.high,     # Initial high = impact candle high
            low=impact_candle.low,       # Initial low = impact candle low
            swing_low=impact_candle.low, # Initial swing low = impact wick low
        )

        self.state = StrategyState.SCAN_HIT
        log.info(
            "state_scan_hit",
            symbol=self.symbol,
            candle_time=impact_candle.time.strftime("%H:%M"),
            spike=f"{impact_candle.spike_multiple:.1f}x",
            close=impact_candle.close,
        )

        # Write signal record to DB
        try:
            self._signal_id = await self._db.write_signal(
                symbol=self.symbol,
                instrument_token=self.instrument_token,
                signal_time=impact_candle.time,
                impact_open=impact_candle.open,
                impact_high=impact_candle.high,
                impact_low=impact_candle.low,
                impact_close=impact_candle.close,
                impact_volume=impact_candle.volume,
                impact_turnover=impact_candle.turnover,
                volume_sma_500=impact_candle.volume_sma_500,
                volume_spike_multiple=impact_candle.spike_multiple,
            )
        except Exception as exc:
            log.error("signal_db_write_failed", symbol=self.symbol, error=str(exc))

        # Publish to Redis pub:signals for dashboard
        try:
            await self._redis.publish_signal({
                "symbol": self.symbol,
                "time": impact_candle.time.isoformat(),
                "signal_time": impact_candle.time.isoformat(),
                "spike_multiple": round(impact_candle.spike_multiple, 1),
                "close": impact_candle.close,
                "impact_high": impact_candle.high,
                "impact_low": impact_candle.low,
                "turnover_cr": round(impact_candle.turnover / 1e7, 2),
                "signal_id": self._signal_id,
                "state": StrategyState.SCAN_HIT.value,
            })
        except Exception as exc:
            log.warning("signal_publish_failed", symbol=self.symbol, error=str(exc))

        await self._persist_state()

    # ── Phase 2: Dry-Up Monitoring ────────────────────────────────────────────

    async def on_candle(
        self,
        o: float,
        h: float,
        l: float,
        c: float,
        volume: int,
        candle_time: datetime.datetime,
    ) -> None:
        """
        Called for every new 1-minute candle when this SM is active.
        Handles SCAN_HIT → MONITORING and all dry-up / re-ignition logic.

        This is the most critical method — all 3 spec bugs (Bug 1, 2, 3) are fixed here.
        Step order from spec Part 8.3 must be followed EXACTLY.
        """
        if self.state not in (StrategyState.SCAN_HIT, StrategyState.MONITORING):
            return

        assert self.impact_candle is not None
        assert self.consolidation is not None

        # Transition SCAN_HIT → MONITORING on first candle after scan hit
        if self.state == StrategyState.SCAN_HIT:
            self.state = StrategyState.MONITORING
            log.info(
                "state_monitoring_start",
                symbol=self.symbol,
                candle_time=candle_time.strftime("%H:%M"),
            )

        # ═══════════════════════════════════════════════════════════════
        # STEP 1: SNAPSHOT BEFORE UPDATE (Bug 1 + Bug 2 fix)
        # These snapshots must happen BEFORE consolidation.update()
        # ═══════════════════════════════════════════════════════════════
        prev_volumes = list(self.consolidation.volume_readings)  # Bug 2 fix
        breakout_level = self.consolidation.breakout_trigger_price  # Bug 1 fix

        # ═══════════════════════════════════════════════════════════════
        # STEP 2: ABANDONMENT CHECKS (on current candle)
        # ═══════════════════════════════════════════════════════════════

        # 2a. Price broke below impact candle low → abandon
        if c < self.impact_candle.low:
            await self._abandon("price_broke_impact_low")
            return

        # 2b. Timeout check — use total_seconds() for robustness (spec Part 8.3)
        elapsed_minutes = (candle_time - self.impact_candle.time).total_seconds() / 60
        if elapsed_minutes > settings.DRYUP_MAX_MINUTES:
            await self._abandon("timeout")
            return

        # 2c. A-shape reversal check (only after minimum dry-up candles)
        if self.consolidation.candle_count >= settings.ASHAPE_MIN_CANDLE_COUNT:
            candle_range_pct = (h - l) / self.impact_candle.close * 100
            is_large_red = (c < o) and (candle_range_pct > settings.ASHAPE_RED_CANDLE_PCT)
            avg_vol = self.consolidation.avg_volume
            volume_elevated = avg_vol > 0 and volume > (avg_vol * settings.ASHAPE_VOLUME_MULTIPLE)
            if is_large_red and volume_elevated:
                log.info(
                    "abandonment_ashape",
                    symbol=self.symbol,
                    candle_range_pct=round(candle_range_pct, 2),
                    volume=volume,
                    avg_vol=round(avg_vol, 0),
                )
                await self._abandon("a_shape_reversal")
                return

        # ═══════════════════════════════════════════════════════════════
        # STEP 3: UPDATE CONSOLIDATION (after abandonment checks)
        # BUG 3 FIX: update() uses wick low (l), not close (c)
        # ═══════════════════════════════════════════════════════════════
        self.consolidation.update(h, l, c, volume)

        # ═══════════════════════════════════════════════════════════════
        # STEP 4: RE-IGNITION CHECK (using PRE-UPDATE snapshots)
        # ═══════════════════════════════════════════════════════════════
        # Minimum dry-up candles needed before re-ignition is valid
        if self.consolidation.candle_count >= settings.MIN_DRYUP_CANDLES:
            # Need at least 2 prev_volumes to form a meaningful comparison window
            if len(prev_volumes) >= 2:
                # Comparison window: last N dry-up candles (pre-update snapshot)
                comparison_window = prev_volumes[-settings.REIGNITION_LOOKBACK_CANDLES:]
                max_prev_vol = max(comparison_window)

                # All four conditions must pass simultaneously
                is_volume_spike = volume > max_prev_vol * settings.REIGNITION_VOLUME_MULTIPLE
                is_price_breakout = c > breakout_level  # Bug 1 fix: pre-update level
                is_green = c > o
                now_ist = datetime.datetime.now(IST_TZ)
                is_before_cutoff = candle_time.time() < settings.max_entry_time

                if is_volume_spike and is_price_breakout and is_green and is_before_cutoff:
                    log.info(
                        "reignition_detected",
                        symbol=self.symbol,
                        candle_time=candle_time.strftime("%H:%M"),
                        volume=volume,
                        max_prev_vol=max_prev_vol,
                        breakout_level=breakout_level,
                        close=c,
                        dry_up_candles=self.consolidation.candle_count,
                    )
                    await self._trigger_entry(c, candle_time)
                    return

        # ═══════════════════════════════════════════════════════════════
        # STEP 5: PERSIST STATE
        # ═══════════════════════════════════════════════════════════════
        log.debug(
            "monitoring_candle",
            symbol=self.symbol,
            candle_time=candle_time.strftime("%H:%M"),
            h=h, l=l, c=c, volume=volume,
            dryup_count=self.consolidation.candle_count,
            breakout_level=breakout_level,
            elapsed_min=round(elapsed_minutes, 1),
        )
        await self._persist_state()

    # ── Phase 3: Entry Trigger ────────────────────────────────────────────────

    async def _trigger_entry(self, entry_close: float, candle_time: datetime.datetime) -> None:
        """
        Trigger an entry order based on re-ignition signal.
        Paper mode: simulate fill immediately via order_service._paper_entry().
        Live mode: place real LIMIT order via order_service.place_entry().
        """
        assert self.consolidation is not None
        assert self.impact_candle is not None

        # Get tick size for SL calculation (default 5 paise)
        try:
            tick_size = await self._redis.get_tick_size(self.symbol)
        except Exception:
            tick_size = 0.05

        # SL = wick-based swing low - 1 tick (Bug 3 fix ensures swing_low is wick)
        stop_loss = round(self.consolidation.swing_low - tick_size, 2)

        # Entry price: close × (1 + ENTRY_BUFFER_PCT)
        limit_price = round(entry_close * (1 + settings.ENTRY_BUFFER_PCT), 2)
        risk_per_share = limit_price - stop_loss

        # Pre-trade risk check
        if risk_per_share < settings.MIN_RISK_PER_SHARE_INR:
            await self._abandon(
                f"risk_per_share_too_small:{risk_per_share:.2f}<{settings.MIN_RISK_PER_SHARE_INR}"
            )
            return

        # Compute quantity using position sizer
        try:
            capital = await self._redis.get_capital()
        except Exception:
            capital = 0.0

        if capital <= 0:
            log.warning("entry_skipped_no_capital", symbol=self.symbol)
            await self._abandon("no_capital_available")
            return

        from engine.risk.position_sizer import compute as compute_qty
        quantity = compute_qty(capital, limit_price, stop_loss)
        if quantity < 1:
            await self._abandon("insufficient_capital_for_quantity")
            return

        # Run all 9 pre-trade checks before placing order (spec §8.4)
        from engine.risk.pre_trade_checks import pre_trade_checks
        from engine.kite.client import AsyncKiteClient

        # Lazy get builder — coordinator stores it; SM accesses via _candle_builder
        builder = getattr(self, "_candle_builder", None)
        if builder is None:
            log.warning("pre_trade_no_builder", symbol=self.symbol)
        kite_client: AsyncKiteClient | None = getattr(self, "_kite", None)

        if builder is not None:  # only run if builder is wired (prod + integration tests)
            ok, reason = await pre_trade_checks.run(
                symbol=self.symbol,
                limit_price=limit_price,
                stop_loss=stop_loss,
                candle_builder=builder,
                redis_store=self._redis,
                kite=kite_client,
            )
            if not ok:
                log.info("pre_trade_check_failed", symbol=self.symbol, reason=reason)
                await self._abandon(f"pre_trade_failed:{reason}")
                return

        # Transition to ACTION_PENDING
        self.state = StrategyState.ACTION_PENDING
        self._pending_order_id = None

        # Get or lazy-import order_service
        if self._order_service is None:
            from engine.orders.order_service import order_service as _os
            self._order_service = _os

        order_id = await self._order_service.place_entry(
            symbol=self.symbol,
            limit_price=limit_price,
            quantity=quantity,
            sm=self,
        )

        if order_id is None:
            # Order placement failed — revert to MONITORING (don't abandon)
            log.warning("entry_order_failed_reverting_to_monitoring", symbol=self.symbol)
            self.state = StrategyState.MONITORING
        else:
            self._pending_order_id = order_id
            # Register in order tracker
            if self._order_tracker is None:
                from engine.orders.order_tracker import order_tracker as _ot
                self._order_tracker = _ot
            self._order_tracker.register_entry(order_id, self.symbol)

            # Start fill timeout watchdog
            if not settings.is_paper_trade:
                if self._fill_timeout is None:
                    from engine.orders.fill_timeout import fill_timeout_manager as _ftm
                    self._fill_timeout = _ftm
                self._fill_timeout.start_timeout(order_id, self, self._order_service)

                # 5-second widen task (spec §8.5)
                asyncio.create_task(
                    self._maybe_widen_limit(order_id, limit_price),
                    name=f"widen_{order_id}",
                )

        await self._persist_state()

    async def _maybe_widen_limit(self, order_id: str, original_limit: float) -> None:
        """
        After ENTRY_WIDEN_AFTER_SECONDS, if still ACTION_PENDING and price is not
        too far away, widen the limit by another ENTRY_BUFFER_PCT (spec §8.5).
        """
        await asyncio.sleep(settings.ENTRY_WIDEN_AFTER_SECONDS)

        if self.state != StrategyState.ACTION_PENDING:
            return  # Already filled or timed out
        if self._order_service is None:
            return

        try:
            current_ltp = await self._redis.get_last_ltp(self.symbol)
            if current_ltp and current_ltp > original_limit * (1 + settings.ENTRY_ABANDON_PCT):
                # Price ran too far — abandon rather than chase
                log.warning(
                    "entry_price_moved_away_abandoning",
                    symbol=self.symbol,
                    ltp=current_ltp,
                    limit=original_limit,
                )
                await self._order_service.cancel_order(order_id, symbol=self.symbol)
                await self._handle_fill_timeout(order_id)  # Reverts to MONITORING
                return

            new_limit = round(original_limit * (1 + settings.ENTRY_BUFFER_PCT), 2)
            await self._order_service._kite.modify_order(
                order_id=order_id,
                price=new_limit,
            ) if (self._order_service and self._order_service._kite) else None
            log.info("entry_limit_widened", order_id=order_id, new_limit=new_limit)
        except Exception as exc:
            log.warning("entry_widen_failed", order_id=order_id, error=str(exc))

    # ── Phase 3: Order Fill / Reject / Timeout ────────────────────────────────

    async def on_order_filled(
        self,
        order_id: str,
        fill_price: float,
        fill_qty: int,
        fill_time: datetime.datetime,
    ) -> None:
        """
        Called when entry order is confirmed filled (real postback or paper simulation).
        Transitions ACTION_PENDING → MANAGING.
        Also cancels fill timeout watchdog and places SL order.
        """
        if self.state != StrategyState.ACTION_PENDING:
            log.warning(
                "fill_in_wrong_state",
                symbol=self.symbol,
                state=self.state,
                order_id=order_id,
            )
            return

        # Cancel fill timeout — order arrived
        if self._fill_timeout is not None:
            self._fill_timeout.cancel_timeout(order_id)

        assert self.consolidation is not None

        # Recalculate from ACTUAL fill price (not limit price)
        try:
            tick_size = await self._redis.get_tick_size(self.symbol)
        except Exception:
            tick_size = 0.05

        stop_loss = round(self.consolidation.swing_low - tick_size, 2)
        risk_per_share = fill_price - stop_loss
        risk_amount = risk_per_share * fill_qty
        target_1r2 = round(fill_price + 2 * risk_per_share, 2)
        target_1r3 = round(fill_price + 3 * risk_per_share, 2)
        target_1r4 = round(fill_price + 4 * risk_per_share, 2)

        # Place SL-M order immediately on fill
        sl_order_id: str | None = None
        margin_blocked = 0.0
        if not settings.is_paper_trade and self._order_service is not None:
            sl_order_id = await self._order_service.place_stop_loss(
                symbol=self.symbol,
                quantity=fill_qty,
                trigger_price=stop_loss,
            )
            if sl_order_id is None:
                log.critical(
                    "sl_placement_failed_position_unprotected",
                    symbol=self.symbol,
                    fill_price=fill_price,
                )
                # Emergency: close position immediately
                if self._order_service:
                    await self._order_service.place_exit_market(
                        self.symbol, fill_qty, reason="sl_placement_failed"
                    )
                self.state = StrategyState.CLOSED
                await self._persist_state()
                return
            if self._order_tracker:
                self._order_tracker.register_sl(sl_order_id, self.symbol)

            # Reserve blocked margin after a confirmed live entry fill.
            kite = getattr(self, "_kite", None)
            if kite is not None:
                try:
                    order_params = [{
                        "exchange": "NSE",
                        "tradingsymbol": self.symbol,
                        "transaction_type": "BUY",
                        "variety": "regular",
                        "product": "MIS",
                        "order_type": "LIMIT",
                        "quantity": fill_qty,
                        "price": fill_price,
                    }]
                    margin_resp = await kite.order_margins(order_params)
                    margin_blocked = float(
                        margin_resp[0].get("initial", {}).get("total", 0.0)
                    )
                    if margin_blocked > 0:
                        from engine.risk.margin_tracker import margin_tracker

                        await margin_tracker.increment(margin_blocked, self._redis)
                except Exception as exc:
                    log.warning(
                        "margin_block_increment_failed",
                        symbol=self.symbol,
                        error=str(exc),
                    )
        elif settings.is_paper_trade:
            # Paper SL is tracked internally — checked via on_tick() LTP
            sl_order_id = f"PAPER_SL_{self.symbol}_{int(__import__('time').time())}"

        # Record trade in DB
        try:
            trade_id = await self._db.open_trade(
                signal_id=self._signal_id,
                symbol=self.symbol,
                instrument_token=self.instrument_token,
                entry_order_id=order_id,
                entry_time=fill_time,
                entry_price=fill_price,
                quantity=fill_qty,
                initial_stop_loss=stop_loss,
                risk_per_share=risk_per_share,
                risk_amount=risk_amount,
                target_1r2=target_1r2,
                target_1r4=target_1r4,
                sl_order_id=sl_order_id,
                notes="PAPER_TRADE" if settings.is_paper_trade else None,
            )
        except Exception as exc:
            log.error("trade_db_write_failed", symbol=self.symbol, error=str(exc))
            trade_id = None

        self.position = OpenPosition(
            trade_id=trade_id,
            entry_price=fill_price,
            quantity=fill_qty,
            initial_sl=stop_loss,
            current_sl=stop_loss,
            risk_per_share=risk_per_share,
            risk_amount=risk_amount,
            target_1r2=target_1r2,
            target_1r3=target_1r3,
            target_1r4=target_1r4,
            entry_order_id=order_id,
            sl_order_id=sl_order_id,
            margin_blocked=margin_blocked,
        )

        self.state = StrategyState.MANAGING

        log.info(
            "state_managing",
            symbol=self.symbol,
            fill_price=fill_price,
            qty=fill_qty,
            sl=stop_loss,
            sl_order_id=sl_order_id,
            target_1r2=target_1r2,
            target_1r4=target_1r4,
            paper=settings.is_paper_trade,
        )

        # Update signal progression in DB
        if self._signal_id:
            try:
                await self._db.update_signal_progression(
                    self._signal_id,
                    progressed_to_action=True,
                    resulted_in_trade=True,
                )
            except Exception as exc:
                log.warning("signal_progression_update_failed", error=str(exc))

        # Save position to Redis
        try:
            await self._redis.set_position(self.symbol, self.position.to_dict())
        except Exception as exc:
            log.warning("position_redis_save_failed", error=str(exc))

        await self._persist_state()

    async def on_order_rejected(self, order_id: str, reason: str) -> None:
        """
        Called when entry order is rejected by the exchange.
        Reverts ACTION_PENDING → MONITORING (spec §8.4: don't abandon on failure).
        """
        if self.state != StrategyState.ACTION_PENDING:
            return
        log.warning(
            "entry_rejected_reverting_to_monitoring",
            symbol=self.symbol,
            order_id=order_id,
            reason=reason,
        )
        if self._fill_timeout is not None:
            self._fill_timeout.cancel_timeout(order_id)
        self._pending_order_id = None
        self.state = StrategyState.MONITORING
        await self._persist_state()

    async def _handle_fill_timeout(self, order_id: str) -> None:
        """
        Called by FillTimeoutManager when order hasn't filled within timeout.
        Reverts ACTION_PENDING → MONITORING.
        """
        if self.state != StrategyState.ACTION_PENDING:
            return
        log.warning(
            "fill_timeout_order_not_filled_reverting",
            symbol=self.symbol,
            order_id=order_id,
            timeout_sec=settings.ORDER_FILL_TIMEOUT_SECONDS,
        )
        self._pending_order_id = None
        self.state = StrategyState.MONITORING
        await self._persist_state()

    async def on_sl_triggered(self, order_id: str, avg_price: float) -> None:
        """
        Called when SL order is filled (postback from order_tracker or reconciliation).
        Race-condition-safe: checks _exit_initiated flag.
        """
        if self.state != StrategyState.MANAGING or self.position is None:
            return
        if self.position.sl_order_id != order_id:
            log.warning(
                "sl_triggered_unknown_order",
                symbol=self.symbol,
                received=order_id,
                expected=self.position.sl_order_id,
            )
            return
        if self.position._exit_initiated:
            return  # Exit sequence already running

        reason = "CLOSED_TRAILSTOP" if self.position.cost_trailed else "CLOSED_STOPLOSS"
        log.info(
            "sl_order_triggered",
            symbol=self.symbol,
            order_id=order_id,
            avg_price=avg_price,
            reason=reason,
        )
        await self._close_position(avg_price, order_id, reason)

    # ── Phase 4: Tick Handler (MANAGING) ─────────────────────────────────────

    async def on_tick(self, ltp: float, tick_time: datetime.datetime) -> None:
        """
        Called for every tick while in MANAGING state.
        Checks SL, trails at 1:2 and 1:3, exits at 1:4.
        Paper mode: all checks against live LTP directly.
        """
        if self.state != StrategyState.MANAGING or self.position is None:
            return

        pos = self.position

        # Update unrealized P&L in Redis for dashboard
        unrealized = (ltp - pos.entry_price) * pos.quantity
        try:
            await self._redis.update_unrealized_pnl(self.symbol, unrealized)
        except Exception:
            pass

        # Track MAE/MFE
        if pos.max_favorable_excursion is None or unrealized > pos.max_favorable_excursion:
            pos.max_favorable_excursion = unrealized
        if pos.max_adverse_excursion is None or unrealized < pos.max_adverse_excursion:
            pos.max_adverse_excursion = unrealized

        # ── Paper mode SL check ───────────────────────────────────────
        if settings.is_paper_trade and ltp <= pos.current_sl and not pos._exit_initiated:
            reason = "CLOSED_TRAILSTOP" if pos.cost_trailed else "CLOSED_STOPLOSS"
            log.info(
                "paper_sl_hit",
                symbol=self.symbol,
                ltp=ltp,
                current_sl=pos.current_sl,
                reason=reason,
            )
            await self._close_position(ltp, None, reason)
            return

        # ── Trail at 1:2 ──────────────────────────────────────────────
        if not pos.cost_trailed and ltp >= pos.target_1r2:
            new_sl = pos.entry_price
            pos.current_sl = new_sl
            pos.cost_trailed = True
            log.info(
                "sl_trailed_to_cost",
                symbol=self.symbol,
                ltp=ltp,
                new_sl=new_sl,
            )
            # Live mode: modify the actual SL-M order at the exchange
            if not settings.is_paper_trade and self._order_service and pos.sl_order_id:
                success = await self._order_service.modify_stop_loss(
                    pos.sl_order_id, new_trigger=new_sl, symbol=self.symbol, sm=self
                )
                if not success:
                    log.warning("sl_trail_modify_failed_cost", symbol=self.symbol)
            try:
                await self._redis.set_position(self.symbol, pos.to_dict())
                await self._redis.publish_state_change({
                    "event": "sl_trailed_to_cost",
                    "symbol": self.symbol,
                    "new_sl": new_sl,
                })
            except Exception:
                pass

        # ── Trail at 1:3 ──────────────────────────────────────────────
        if pos.cost_trailed and not pos.profit_locked and ltp >= pos.target_1r3:
            new_sl = pos.entry_price + pos.risk_per_share
            pos.current_sl = new_sl
            pos.profit_locked = True
            log.info(
                "sl_trailed_to_profit",
                symbol=self.symbol,
                ltp=ltp,
                new_sl=new_sl,
            )
            # Live mode: modify the actual SL-M order at the exchange
            if not settings.is_paper_trade and self._order_service and pos.sl_order_id:
                success = await self._order_service.modify_stop_loss(
                    pos.sl_order_id, new_trigger=new_sl, symbol=self.symbol, sm=self
                )
                if not success:
                    log.warning("sl_trail_modify_failed_profit", symbol=self.symbol)
            try:
                await self._redis.set_position(self.symbol, pos.to_dict())
                await self._redis.publish_state_change({
                    "event": "sl_trailed_to_profit",
                    "symbol": self.symbol,
                    "new_sl": new_sl,
                })
            except Exception:
                pass

        # ── Full exit at 1:4 ─────────────────────────────────────────
        if ltp >= pos.target_1r4 and not pos._exit_initiated:
            log.info(
                "target_1r4_reached",
                symbol=self.symbol,
                ltp=ltp,
                target=pos.target_1r4,
            )
            if settings.is_paper_trade:
                # Paper: close directly — no Redis lock needed
                await self._close_position(ltp, None, "CLOSED_TARGET")
            else:
                # Live: race-safe exit with SL cancel + market sell
                await self._initiate_exit("CLOSED_TARGET")

    # ── Squareoff (3:20 PM) ───────────────────────────────────────────────────

    async def force_squareoff(self) -> None:
        """
        Called at 3:20 PM by APScheduler for any open position.
        Live mode: uses _initiate_exit() (cancel SL + place MARKET sell).
        Paper mode: simulate exit at current LTP.
        """
        if self.state == StrategyState.MANAGING and self.position is not None:
            if settings.is_paper_trade:
                try:
                    ltp = await self._redis.get_last_ltp(self.symbol) or self.position.entry_price
                except Exception:
                    ltp = self.position.entry_price
                log.info("forced_squareoff", symbol=self.symbol, ltp=ltp)
                await self._close_position(ltp, None, "CLOSED_TIME")
            else:
                log.info("forced_squareoff_live", symbol=self.symbol)
                await self._initiate_exit("CLOSED_TIME")

        elif self.state in (StrategyState.SCAN_HIT, StrategyState.MONITORING):
            await self._abandon("session_end_time")

        elif self.state == StrategyState.ACTION_PENDING:
            if self._pending_order_id and self._order_service:
                await self._order_service.cancel_order(self._pending_order_id, symbol=self.symbol)
            self._pending_order_id = None
            self.state = StrategyState.CLOSED
            await self._persist_state()
            log.info("squareoff_pending_cancelled", symbol=self.symbol)

    # ── Internal: Race-safe Exit ──────────────────────────────────────────────

    async def _initiate_exit(self, reason: str) -> None:
        """
        Race-condition-safe exit sequence (spec §8.8).
        1. Acquire Redis NX lock (auto-expires in 10s on crash)
        2. Set _exit_initiated = True
        3. Cancel SL order
        4. Wait EXIT_SL_CANCEL_DELAY_MS
        5. If state already CLOSED (SL triggered during wait) → release lock, return
        6. Place MARKET exit
        7. Register exit order and wait for postback/reconciliation to close

        Paper mode: skips SL cancel + market order (uses _close_position directly).
        """
        if self.position is None or self.position._exit_initiated:
            return

        if settings.is_paper_trade:
            # Paper: close directly
            try:
                ltp = await self._redis.get_last_ltp(self.symbol) or self.position.entry_price
            except Exception:
                ltp = self.position.entry_price
            await self._close_position(ltp, None, reason)
            return

        # Live: acquire exit lock atomically
        lock_acquired = await self._redis.acquire_symbol_lock(self.symbol)
        if not lock_acquired:
            log.warning("exit_lock_contention", symbol=self.symbol, reason=reason)
            return  # Another exit already running for this symbol

        try:
            self.position._exit_initiated = True
            pos = self.position

            # Cancel SL order first
            if pos.sl_order_id and self._order_service:
                await self._order_service.cancel_order(pos.sl_order_id, symbol=self.symbol)

            # Wait for cancel to propagate
            await asyncio.sleep(settings.EXIT_SL_CANCEL_DELAY_MS / 1000)

            # Guard: SL may have triggered during the wait
            if self.state == StrategyState.CLOSED:
                log.info("exit_sl_triggered_during_cancel_wait", symbol=self.symbol)
                return

            # Place market exit
            if self._order_service:
                exit_order_id = await self._order_service.place_exit_market(
                    symbol=self.symbol,
                    quantity=pos.quantity,
                    reason=reason,
                )
            else:
                exit_order_id = None

            if exit_order_id is None:
                log.critical(
                    "exit_order_placement_failed",
                    symbol=self.symbol,
                    reason=reason,
                )
                # Allow retry paths (reconciliation/next trigger) if order placement failed.
                self.position._exit_initiated = False
                return

            pos.exit_order_id = exit_order_id
            pos.exit_reason = reason
            if self._order_tracker is not None:
                self._order_tracker.register_exit(exit_order_id, self.symbol, reason)

            log.info(
                "exit_order_placed_waiting_fill",
                symbol=self.symbol,
                order_id=exit_order_id,
                reason=reason,
            )
            await self._persist_state()
        finally:
            await self._redis.release_symbol_lock(self.symbol)

    # ── Internal: Close Position ──────────────────────────────────────────────

    async def _close_position(
        self,
        exit_price: float,
        exit_order_id: str | None,
        reason: str,
    ) -> None:
        """Close an open position, compute P&L, write to DB, publish event."""
        if self.position is None:
            return

        pos = self.position
        pos._exit_initiated = True

        gross_pnl = round((exit_price - pos.entry_price) * pos.quantity, 2)

        # Phase 3: use full cost calculator
        from engine.orders.cost_calculator import calculate as calc_charges
        charges = calc_charges(pos.entry_price, exit_price, pos.quantity)
        estimated_charges = charges.total
        net_pnl = round(gross_pnl - estimated_charges, 2)

        log.info(
            "position_closed",
            symbol=self.symbol,
            reason=reason,
            exit_price=exit_price,
            entry_price=pos.entry_price,
            qty=pos.quantity,
            gross_pnl=gross_pnl,
            charges=estimated_charges,
            net_pnl=net_pnl,
            paper=settings.is_paper_trade,
        )

        # Update trade in DB
        if pos.trade_id is not None:
            try:
                from app.models.db.trade import TradeStatus
                status_map = {
                    "CLOSED_TARGET": TradeStatus.CLOSED_TARGET,
                    "CLOSED_STOPLOSS": TradeStatus.CLOSED_STOPLOSS,
                    "CLOSED_TRAILSTOP": TradeStatus.CLOSED_TRAILSTOP,
                    "CLOSED_TIME": TradeStatus.CLOSED_TIME,
                    "CLOSED_MANUAL": TradeStatus.CLOSED_MANUAL,
                    "CLOSED_ERROR": TradeStatus.CLOSED_ERROR,
                }
                status = status_map.get(reason, TradeStatus.CLOSED_MANUAL)
                await self._db.close_trade(
                    trade_id=pos.trade_id,
                    exit_price=exit_price,
                    exit_time=datetime.datetime.now(IST_TZ),
                    exit_order_id=exit_order_id,
                    gross_pnl=gross_pnl,
                    net_pnl=net_pnl,
                    brokerage=charges.brokerage,
                    stt=charges.stt,
                    other_charges=charges.nse_fee + charges.sebi_fee + charges.gst + charges.stamp_duty,
                    status=status,
                    mfe=pos.max_favorable_excursion,
                    mae=pos.max_adverse_excursion,
                )
            except Exception as exc:
                log.error("trade_close_db_failed", symbol=self.symbol, error=str(exc))

        # Update daily P&L in Redis
        try:
            await self._redis.increment_daily_pnl(net_pnl)
        except Exception:
            pass

        # Release blocked margin for this position.
        if pos.margin_blocked > 0:
            try:
                from engine.risk.margin_tracker import margin_tracker

                await margin_tracker.decrement(pos.margin_blocked, self._redis)
            except Exception as exc:
                log.warning(
                    "margin_block_decrement_failed",
                    symbol=self.symbol,
                    blocked=pos.margin_blocked,
                    error=str(exc),
                )

        # Clear position from Redis
        try:
            await self._redis.clear_position(self.symbol)
        except Exception:
            pass

        # Publish trade closed event
        try:
            await self._redis.publish_state_change({
                "event": "trade_closed",
                "symbol": self.symbol,
                "reason": reason,
                "exit_price": exit_price,
                "net_pnl": net_pnl,
            })
        except Exception:
            pass

        self.position = None
        self.state = StrategyState.CLOSED
        await self._persist_state()

    # ── Internal: Abandon ─────────────────────────────────────────────────────

    async def _abandon(self, reason: str) -> None:
        """Abandon a setup that didn't progress to a trade."""
        self._abandonment_reason = reason
        self.state = StrategyState.CLOSED

        log.info(
            "setup_abandoned",
            symbol=self.symbol,
            reason=reason,
            state_before="MONITORING" if self.consolidation else "SCAN_HIT",
        )

        # Update signal record with abandonment reason
        if self._signal_id:
            try:
                await self._db.update_signal_progression(
                    self._signal_id,
                    progressed_to_monitor=bool(self.consolidation and self.consolidation.candle_count > 0),
                    abandonment_reason=reason,
                )
            except Exception as exc:
                log.warning("signal_abandon_update_failed", error=str(exc))

        # Publish abandonment event  
        try:
            await self._redis.publish_state_change({
                "event": "setup_abandoned",
                "symbol": self.symbol,
                "reason": reason,
            })
        except Exception:
            pass

        await self._persist_state()

    # ── Internal: Persist State ───────────────────────────────────────────────

    async def _persist_state(self) -> None:
        """Snapshot current SM state to Redis for dashboard polling."""
        try:
            data: dict[str, Any] = {
                "symbol": self.symbol,
                "state": self.state.value,
                "signal_id": self._signal_id,
            }
            if self.impact_candle:
                data["impact_candle_time"] = self.impact_candle.time.isoformat()
                data["impact_close"] = self.impact_candle.close
                data["spike_multiple"] = round(self.impact_candle.spike_multiple, 1)
                data["impact_candle"] = {
                    "time": self.impact_candle.time.isoformat(),
                    "close": self.impact_candle.close,
                    "high": self.impact_candle.high,
                    "low": self.impact_candle.low,
                    "volume": self.impact_candle.volume,
                    "spike_multiple": round(self.impact_candle.spike_multiple, 1),
                    "turnover_cr": round(self.impact_candle.turnover / 1e7, 2),
                }
            if self.consolidation:
                data["consolidation"] = self.consolidation.to_dict()
            if self.position:
                data["position"] = self.position.to_dict()

            if self.state == StrategyState.CLOSED:
                await self._redis.clear_strategy_state(self.symbol)
            else:
                await self._redis.set_strategy_state(self.symbol, data)
        except Exception as exc:
            log.warning("state_persist_failed", symbol=self.symbol, error=str(exc))

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def is_active(self) -> bool:
        """True if this SM is still alive (not CLOSED)."""
        return self.state != StrategyState.CLOSED

    def __repr__(self) -> str:
        return f"SM({self.symbol}:{self.state.value})"
