"""
engine/strategies/options_momentum/strategy.py — Index Options Momentum (buyer).

A self-contained BaseStrategy plugin that proves the engine supports a DIFFERENT
asset class (F&O options) with zero engine-core changes. It:

  - loads the NFO option chain (OptionChainResolver) via load_option_chain()
  - watches the underlying's 1-min candles for an N-bar breakout
  - on breakout up → buys the ATM CE; on breakdown → buys the ATM PE (nearest expiry)
  - sizes in whole lots (compute_lots) with a premium-exposure cap
  - manages each position on the option premium: %-stop-loss, %-target, EOD squareoff
  - is fully driven by its own config.yaml (authoritative, not app.core.config)

Scope note (Phase 4): PAPER mode is complete and unit-tested. LIVE order params are
correct (exchange=NFO, product, lot quantity), but LIVE fill confirmation via
per-strategy order postbacks + reconciliation is completed in Phase 5. Options
transaction-cost modelling (STT/brokerage on premium) is a documented follow-up —
paper net P&L currently equals gross.
"""

from __future__ import annotations

import datetime
import time as _time
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pytz
import structlog

from app.core.config import settings
from app.models.db.trade import TradeStatus
from engine.core.base_strategy import BaseStrategy
from engine.core.instrument import Instrument, OptionType
from engine.market.option_chain import OptionChainResolver
from engine.risk.circuit_breaker import circuit_breaker
from engine.risk.position_sizer import compute_lots

if TYPE_CHECKING:
    from engine.market.candle_builder import Candle, CandleBuilder
    from engine.store.db_writer import DbWriter
    from engine.store.redis_store import RedisStore

log = structlog.get_logger(__name__)
IST_TZ = pytz.timezone("Asia/Kolkata")

# Paper-fill slippage for options (wider spreads than cash equity).
_PAPER_SLIPPAGE = 0.002

_STATUS_BY_REASON = {
    "CLOSED_STOPLOSS": TradeStatus.CLOSED_STOPLOSS,
    "CLOSED_TARGET": TradeStatus.CLOSED_TARGET,
    "CLOSED_TIME": TradeStatus.CLOSED_TIME,
}


@dataclass
class _OptionPosition:
    option: Instrument
    option_type: OptionType
    entry_price: float
    quantity: int
    stop_loss: float
    target: float
    entry_time: datetime.datetime
    trade_id: int | None = None
    entry_order_id: str = ""
    last_ltp: float = 0.0
    exit_initiated: bool = False


class OptionsMomentumStrategy(BaseStrategy):
    """ATM option-buying on an N-bar breakout of the underlying."""

    def __init__(
        self,
        strategy_id: str,
        redis_store: "RedisStore",
        db_writer: "DbWriter",
    ) -> None:
        super().__init__(strategy_id, redis_store, db_writer)
        cfg = self.config
        self.underlying: str = cfg.get("underlying", "NIFTY")
        self.underlying_symbol: str = cfg.get("underlying_symbol", self.underlying)
        self.product: str = cfg.get("product", "MIS")

        sig = cfg.get("signal", {})
        self.lookback: int = int(sig.get("lookback_candles", 5))

        risk = cfg.get("risk", {})
        self.sl_pct: float = float(risk.get("stop_loss_pct", 30)) / 100.0
        self.target_pct: float = float(risk.get("target_pct", 60)) / 100.0
        self.max_lots: int | None = risk.get("max_lots")
        self.max_exposure_pct: float | None = risk.get("max_premium_exposure_pct")
        self.max_positions: int = int(risk.get("max_positions", 1))

        self.entry_cutoff: datetime.time = self._parse_time(
            cfg.get("timing", {}).get("entry_cutoff", "14:30")
        )

        self.chain = OptionChainResolver()
        self._chain_loaded = False
        self._nearest_expiry: datetime.date | None = None

        self._recent_highs: deque[float] = deque(maxlen=self.lookback)
        self._recent_lows: deque[float] = deque(maxlen=self.lookback)
        self._positions: dict[str, _OptionPosition] = {}
        self._entries_today: int = 0
        self._signal_count: int = 0

    # ── Setup ────────────────────────────────────────────────────────────────

    def load_option_chain(self, nfo_dump: list[dict]) -> None:
        """Load the NFO instrument dump into the resolver (called at pre-market)."""
        self.chain.load(nfo_dump)
        self._chain_loaded = True
        self._nearest_expiry = self.chain.nearest_expiry(self.underlying)
        log.info(
            "opt_chain_ready",
            strategy_id=self.strategy_id,
            underlying=self.underlying,
            expiry=str(self._nearest_expiry),
        )

    async def on_market_open(self) -> None:
        self._positions.clear()
        self._entries_today = 0
        self._recent_highs.clear()
        self._recent_lows.clear()
        if self._chain_loaded:
            self._nearest_expiry = self.chain.nearest_expiry(self.underlying)

    # ── Signal (underlying candles) ──────────────────────────────────────────

    async def on_candle(
        self,
        symbol: str,
        candle: "Candle",
        builder: "CandleBuilder",
        instrument_token: int,
    ) -> None:
        if symbol != self.underlying_symbol:
            return

        # N-bar breakout using ONLY prior candles (no lookahead).
        signal: OptionType | None = None
        if len(self._recent_highs) >= self.lookback:
            prior_high = max(self._recent_highs)
            prior_low = min(self._recent_lows)
            if candle.close > prior_high and candle.close > candle.open:
                signal = OptionType.CE
            elif candle.close < prior_low and candle.close < candle.open:
                signal = OptionType.PE

        self._recent_highs.append(candle.high)
        self._recent_lows.append(candle.low)

        if signal is not None:
            await self._maybe_enter(signal, candle)

    async def _maybe_enter(self, opt_type: OptionType, candle: "Candle") -> None:
        if not self._accept_new_entries:
            return
        if len(self._positions) >= self.max_positions or self._entries_today >= self.max_positions:
            return
        if candle.timestamp.timetz().replace(tzinfo=None) >= self.entry_cutoff:
            return
        if not self._chain_loaded or self._nearest_expiry is None:
            return

        ok, reason = await circuit_breaker.check(self._redis)
        if not ok:
            log.info("opt_entry_blocked_circuit_breaker", reason=reason)
            return

        option = self.chain.atm_option(
            self.underlying, candle.close, opt_type, self._nearest_expiry
        )
        if option is None:
            log.warning("opt_atm_not_found", underlying=self.underlying, spot=candle.close)
            return

        premium = await self._redis.get_last_ltp(option.tradingsymbol)
        if not premium or premium <= 0:
            log.info("opt_no_premium_ltp_skip", option=option.tradingsymbol)
            return

        stop_loss = round(premium * (1.0 - self.sl_pct), 2)
        target = round(premium * (1.0 + self.target_pct), 2)
        capital = await self._redis.get_capital()
        quantity = compute_lots(
            capital=capital,
            entry_price=premium,
            stop_loss=stop_loss,
            lot_size=option.lot_size,
            max_lots=self.max_lots,
            max_premium_exposure_pct=self.max_exposure_pct,
        )
        if quantity < 1:
            log.info("opt_size_zero_skip", option=option.tradingsymbol, premium=premium)
            return

        await self._enter(option, opt_type, premium, stop_loss, target, quantity, candle.timestamp)

    async def _enter(
        self,
        option: Instrument,
        opt_type: OptionType,
        premium: float,
        stop_loss: float,
        target: float,
        quantity: int,
        ts: datetime.datetime,
    ) -> None:
        is_paper = settings.is_paper_trade
        if is_paper:
            fill = round(premium * (1.0 + _PAPER_SLIPPAGE), 2)
            order_id = f"PAPER_{self.strategy_id}_{option.tradingsymbol}_{int(_time.time())}"
        else:
            if self._order_service is None:
                log.error("opt_no_order_service", option=option.tradingsymbol)
                return
            order_id = await self._order_service.place_entry(
                option.tradingsymbol,
                limit_price=round(premium * 1.01, 2),  # marketable-limit buffer
                quantity=quantity,
                sm=None,
                exchange="NFO",
                product=self.product,
                tag=self.strategy_id,
            )
            if not order_id:
                return
            # LIVE fill confirmation is completed in Phase 5 (per-strategy postbacks).
            fill = premium
            log.warning("opt_live_fill_pending_phase5", option=option.tradingsymbol, order_id=order_id)

        trade_id: int | None = None
        try:
            trade_id = await self._db.open_trade(
                signal_id=None,
                symbol=option.tradingsymbol,
                instrument_token=option.instrument_token,
                entry_order_id=order_id,
                entry_time=ts,
                entry_price=fill,
                quantity=quantity,
                initial_stop_loss=stop_loss,
                risk_per_share=round(fill - stop_loss, 2),
                risk_amount=round((fill - stop_loss) * quantity, 2),
                target_1r2=target,
                target_1r3=target,
                target_1r4=target,
                sl_order_id=None,
                trade_mode=("PAPER" if is_paper else "LIVE"),
                strategy_id=self.strategy_id,
            )
        except Exception as exc:
            log.error("opt_trade_write_failed", option=option.tradingsymbol, error=str(exc))

        self._positions[option.tradingsymbol] = _OptionPosition(
            option=option,
            option_type=opt_type,
            entry_price=fill,
            quantity=quantity,
            stop_loss=stop_loss,
            target=target,
            entry_time=ts,
            trade_id=trade_id,
            entry_order_id=order_id,
            last_ltp=fill,
        )
        self._entries_today += 1
        self._signal_count += 1
        log.info(
            "opt_entry",
            strategy_id=self.strategy_id,
            option=option.tradingsymbol,
            side=opt_type.value,
            fill=fill,
            qty=quantity,
            sl=stop_loss,
            target=target,
            mode=("PAPER" if is_paper else "LIVE"),
        )

    # ── Per-tick management ──────────────────────────────────────────────────

    async def on_tick(
        self,
        symbol: str,
        ltp: float,
        exchange_ts: datetime.datetime,
    ) -> None:
        pos = self._positions.get(symbol)
        if pos is None or pos.exit_initiated:
            return
        pos.last_ltp = ltp
        if ltp <= pos.stop_loss:
            await self._close(pos, ltp, "CLOSED_STOPLOSS")
        elif ltp >= pos.target:
            await self._close(pos, ltp, "CLOSED_TARGET")

    async def _close(self, pos: _OptionPosition, exit_price: float, reason: str) -> None:
        pos.exit_initiated = True
        if not settings.is_paper_trade and self._order_service is not None:
            await self._order_service.place_exit_market(
                pos.option.tradingsymbol,
                pos.quantity,
                reason=reason,
                exchange="NFO",
                product=self.product,
                tag=self.strategy_id,
            )

        gross = round((exit_price - pos.entry_price) * pos.quantity, 2)
        # NOTE: options-specific transaction costs (STT on premium, brokerage) are a
        # documented follow-up; paper net == gross for now.
        net = gross
        if pos.trade_id is not None:
            try:
                await self._db.close_trade(
                    trade_id=pos.trade_id,
                    exit_price=exit_price,
                    exit_time=datetime.datetime.now(IST_TZ),
                    exit_order_id=None,
                    gross_pnl=gross,
                    net_pnl=net,
                    brokerage=0.0,
                    stt=0.0,
                    other_charges=0.0,
                    status=_STATUS_BY_REASON.get(reason, TradeStatus.CLOSED_MANUAL),
                )
            except Exception as exc:
                log.error("opt_close_write_failed", option=pos.option.tradingsymbol, error=str(exc))

        self._positions.pop(pos.option.tradingsymbol, None)
        log.info(
            "opt_exit",
            strategy_id=self.strategy_id,
            option=pos.option.tradingsymbol,
            exit=exit_price,
            reason=reason,
            gross_pnl=gross,
        )

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def on_squareoff(self) -> None:
        for pos in list(self._positions.values()):
            ltp = pos.last_ltp
            if ltp <= 0:
                live = await self._redis.get_last_ltp(pos.option.tradingsymbol)
                ltp = live if live and live > 0 else pos.entry_price
            await self._close(pos, ltp, "CLOSED_TIME")

    async def on_order_postback(self, message: dict[str, Any]) -> None:
        # LIVE postback routing for this strategy is wired in Phase 5.
        return None

    # ── Queries ──────────────────────────────────────────────────────────────

    def is_symbol_active(self, symbol: str) -> bool:
        return symbol in self._positions

    def get_stats(self) -> dict[str, Any]:
        return {
            "asset_class": "OPTION",
            "underlying": self.underlying,
            "open_positions": len(self._positions),
            "entries_today": self._entries_today,
            "total_signals": self._signal_count,
            "chain_loaded": self._chain_loaded,
            "nearest_expiry": str(self._nearest_expiry) if self._nearest_expiry else None,
        }

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_time(hhmm: str) -> datetime.time:
        try:
            hh, mm = str(hhmm).split(":")
            return datetime.time(int(hh), int(mm))
        except (ValueError, AttributeError):
            return datetime.time(14, 30)
