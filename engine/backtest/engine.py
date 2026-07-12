"""
engine/backtest/engine.py — candle/tick replay driver for strategy validation.

Wires the SAME StrategyRouter + BaseStrategy plugins used live against a fake
Redis, a deterministic SimBroker, and a CapturingDbWriter that funnels the
strategy's own trade records into a BacktestPortfolio (so realized P&L already
includes the strategy's cost model). Runs in paper mode (strategies must be able
to fill via the injected order service).

Usage:
    eng = BacktestEngine(lambda r, d: [IVBSStrategy("ivbs", r, d)])
    await eng.set_capital(500_000)
    await eng.market_open()
    for candle in candles:
        await eng.feed_candle(candle)
    await eng.squareoff()
    report = eng.summary()
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

import structlog

from engine.backtest.portfolio import BacktestPortfolio, BacktestTrade
from engine.backtest.sim_broker import SimBroker
from engine.core.strategy_router import StrategyRouter
from engine.market.candle_builder import CandleBuilder
from engine.orders.fill_timeout import FillTimeoutManager
from engine.orders.order_tracker import OrderTracker

if TYPE_CHECKING:
    import datetime

    from engine.core.base_strategy import BaseStrategy
    from engine.market.candle_builder import Candle
    from engine.store.db_writer import DbWriter
    from engine.store.redis_store import RedisStore

log = structlog.get_logger(__name__)

BuildStrategies = Callable[["RedisStore", "DbWriter"], "list[BaseStrategy]"]


class CapturingDbWriter:
    """DbWriter-compatible sink that records completed trades into a portfolio."""

    def __init__(self, portfolio: BacktestPortfolio) -> None:
        self._portfolio = portfolio
        self._trade_seq = 0
        self._signal_seq = 0
        self._open: dict[int, dict[str, Any]] = {}

    async def write_signal(self, **kwargs: Any) -> int:
        self._signal_seq += 1
        return self._signal_seq

    async def update_signal_progression(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def write_signal_snapshot(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def open_trade(self, **kwargs: Any) -> int:
        self._trade_seq += 1
        tid = self._trade_seq
        self._open[tid] = {
            "symbol": kwargs.get("symbol", ""),
            "strategy_id": kwargs.get("strategy_id", "ivbs"),
            "entry_time": kwargs.get("entry_time"),
            "entry_price": float(kwargs.get("entry_price", 0.0)),
            "quantity": int(kwargs.get("quantity", 0)),
        }
        return tid

    async def close_trade(self, **kwargs: Any) -> None:
        tid = kwargs.get("trade_id")
        entry = self._open.pop(tid, None) if tid is not None else None
        if entry is None:
            return
        status = kwargs.get("status")
        self._portfolio.record_trade(BacktestTrade(
            symbol=entry["symbol"],
            strategy_id=entry["strategy_id"],
            entry_time=entry["entry_time"],
            entry_price=entry["entry_price"],
            quantity=entry["quantity"],
            exit_time=kwargs.get("exit_time"),
            exit_price=float(kwargs.get("exit_price", 0.0)),
            gross_pnl=float(kwargs.get("gross_pnl", 0.0)),
            net_pnl=float(kwargs.get("net_pnl", 0.0)),
            status=getattr(status, "value", str(status)),
        ))

    async def write_order_event(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def write_daily_pnl(self, *args: Any, **kwargs: Any) -> None:
        return None


class BacktestEngine:
    """Replays candles/ticks through real strategy plugins and tallies results."""

    def __init__(
        self,
        build_strategies: BuildStrategies,
        starting_capital: float = 500000.0,
        redis_store: "RedisStore | None" = None,
    ) -> None:
        self.portfolio = BacktestPortfolio(starting_capital)
        self._starting_capital = starting_capital
        self.redis = redis_store if redis_store is not None else self._make_fake_redis()
        self.db: Any = CapturingDbWriter(self.portfolio)
        self.broker = SimBroker()
        self.router = StrategyRouter()
        for strat in build_strategies(self.redis, self.db):
            self.router.register(strat)
        self.router.inject_execution(self.broker, OrderTracker(), FillTimeoutManager(), None)
        self.builders: dict[str, CandleBuilder] = {}
        self.tokens: dict[str, int] = {}

    @staticmethod
    def _make_fake_redis() -> "RedisStore":
        import fakeredis.aioredis  # lazy: test/analysis-only dependency

        from engine.store.redis_store import RedisStore
        return RedisStore(fakeredis.aioredis.FakeRedis(decode_responses=True))

    # ── Setup ────────────────────────────────────────────────────────────────

    async def set_capital(self, capital: float) -> None:
        await self.redis.set_capital(capital)

    async def set_ltp(self, symbol: str, price: float) -> None:
        await self.redis.set_last_ltp(symbol, price)

    def warmup_builder(self, symbol: str, volumes: list[int], token: int = 0) -> CandleBuilder:
        b = CandleBuilder(symbol)
        if volumes:
            b.load_history(volumes)
        self.builders[symbol] = b
        self.tokens[symbol] = token
        return b

    def _builder(self, symbol: str) -> CandleBuilder:
        b = self.builders.get(symbol)
        if b is None:
            b = CandleBuilder(symbol)
            self.builders[symbol] = b
        return b

    # ── Replay primitives ────────────────────────────────────────────────────

    async def market_open(self) -> None:
        await self.router.on_market_open()

    async def squareoff(self) -> None:
        await self.router.on_squareoff()

    async def feed_candle(self, candle: "Candle", *, intrabar_sl_target: bool = True) -> None:
        """Replay one completed candle: route it, then simulate intrabar SL/target ticks."""
        symbol = candle.symbol
        await self.redis.set_last_ltp(symbol, candle.close)
        self.broker.set_fill(candle.close, candle.timestamp)
        builder = self._builder(symbol)
        token = self.tokens.get(symbol, 0)

        await self.router.on_candle(symbol, candle, builder, token)
        builder.record_completed_volume(candle.volume)

        # Simulate intrabar price path for SL/target: low first (conservative for
        # longs), then high. Only if a strategy holds this symbol.
        if intrabar_sl_target and self.router.any_strategy_has_active_symbol(symbol):
            await self.feed_tick(symbol, candle.low, candle.timestamp)
            await self.feed_tick(symbol, candle.high, candle.timestamp)

    async def feed_tick(self, symbol: str, price: float, ts: "datetime.datetime") -> None:
        await self.redis.set_last_ltp(symbol, price)
        if self.router.any_strategy_has_active_symbol(symbol):
            await self.router.on_tick(symbol, price, ts)

    # ── Convenience single-symbol run ────────────────────────────────────────

    async def run(
        self,
        candles: list["Candle"],
        warmup_volumes: list[int] | None = None,
        token: int = 0,
    ) -> dict[str, Any]:
        if candles and warmup_volumes:
            self.warmup_builder(candles[0].symbol, warmup_volumes, token)
        await self.market_open()
        for candle in candles:
            await self.feed_candle(candle)
        await self.squareoff()
        return self.summary()

    def summary(self) -> dict[str, Any]:
        return self.portfolio.summary()
