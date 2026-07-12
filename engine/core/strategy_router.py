"""
engine/core/strategy_router.py — Fan-out dispatcher for registered strategies.

The Coordinator (pure data router) forwards lifecycle events here; the router
fans them out to every registered BaseStrategy with per-strategy failure
isolation, so a bug in one strategy can never crash the engine or a sibling.

Registration happens once at startup in runner.py:

    router = StrategyRouter()
    router.register(IVBSStrategy("ivbs", redis_store, db_writer))
    router.register(OptionsStrategy("opt_momentum", redis_store, db_writer))
    coordinator = Coordinator(redis_store, db_writer, strategy_router=router)

Adding a strategy requires NO change to the engine core.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from engine.core.base_strategy import BaseStrategy

if TYPE_CHECKING:
    import datetime

    from engine.kite.client import AsyncKiteClient
    from engine.market.candle_builder import Candle, CandleBuilder
    from engine.orders.fill_timeout import FillTimeoutManager
    from engine.orders.order_service import OrderService
    from engine.orders.order_tracker import OrderTracker

log = structlog.get_logger(__name__)


class StrategyRouter:
    """Holds all registered strategies and dispatches engine events to them."""

    def __init__(self) -> None:
        self._strategies: dict[str, BaseStrategy] = {}

    # ── Registration / lookup ────────────────────────────────────────────────

    def register(self, strategy: BaseStrategy) -> None:
        sid = strategy.strategy_id
        if sid in self._strategies:
            raise ValueError(f"strategy_id already registered: {sid!r}")
        self._strategies[sid] = strategy
        log.info("strategy_registered", strategy_id=sid, cls=type(strategy).__name__)

    def get(self, strategy_id: str) -> BaseStrategy | None:
        return self._strategies.get(strategy_id)

    @property
    def strategies(self) -> list[BaseStrategy]:
        return list(self._strategies.values())

    @property
    def strategy_ids(self) -> list[str]:
        return list(self._strategies.keys())

    def __len__(self) -> int:
        return len(self._strategies)

    # ── Dependency injection / control ───────────────────────────────────────

    def inject_execution(
        self,
        order_service: "OrderService",
        order_tracker: "OrderTracker",
        fill_timeout_manager: "FillTimeoutManager",
        kite: "AsyncKiteClient | None" = None,
    ) -> None:
        for strat in self._strategies.values():
            strat.inject_execution(order_service, order_tracker, fill_timeout_manager, kite)

    def set_new_entries_enabled(self, enabled: bool) -> None:
        for strat in self._strategies.values():
            strat.set_new_entries_enabled(enabled)

    # ── Event fan-out (each call isolated per strategy) ──────────────────────

    async def on_candle(
        self,
        symbol: str,
        candle: "Candle",
        builder: "CandleBuilder",
        instrument_token: int,
    ) -> None:
        for strat in self._strategies.values():
            try:
                await strat.on_candle(symbol, candle, builder, instrument_token)
            except Exception:
                log.exception(
                    "strategy_on_candle_failed",
                    strategy_id=strat.strategy_id,
                    symbol=symbol,
                )

    async def on_tick(
        self,
        symbol: str,
        ltp: float,
        exchange_ts: "datetime.datetime",
    ) -> None:
        for strat in self._strategies.values():
            # Only forward ticks to strategies actively managing this symbol.
            try:
                if not strat.is_symbol_active(symbol):
                    continue
                await strat.on_tick(symbol, ltp, exchange_ts)
            except Exception:
                log.exception(
                    "strategy_on_tick_failed",
                    strategy_id=strat.strategy_id,
                    symbol=symbol,
                )

    async def on_order_postback(self, message: dict[str, Any]) -> None:
        """Broadcast a raw postback to all strategies with isolation.

        Each strategy ignores orders it does not own (must be idempotent).
        Phase 2 will add tag-based targeted routing (order tag carries strategy_id)
        so only the owning strategy is invoked.
        """
        for strat in self._strategies.values():
            try:
                await strat.on_order_postback(message)
            except Exception:
                log.exception(
                    "strategy_on_postback_failed",
                    strategy_id=strat.strategy_id,
                    order_id=message.get("order_id"),
                )

    async def on_market_open(self) -> None:
        await self._broadcast("on_market_open")

    async def on_squareoff(self) -> None:
        await self._broadcast("on_squareoff")

    async def on_session_end(self) -> None:
        await self._broadcast("on_session_end")

    async def on_websocket_connected(self) -> None:
        await self._broadcast("on_websocket_connected")

    async def on_fatal_disconnect(self) -> None:
        await self._broadcast("on_fatal_disconnect")

    # ── Queries / stats ──────────────────────────────────────────────────────

    def any_strategy_has_active_symbol(self, symbol: str) -> bool:
        for strat in self._strategies.values():
            try:
                if strat.is_symbol_active(symbol):
                    return True
            except Exception:
                log.exception("strategy_is_active_failed", strategy_id=strat.strategy_id)
        return False

    def get_combined_stats(self) -> dict[str, Any]:
        out: dict[str, Any] = {"strategy_count": len(self._strategies), "strategies": {}}
        for sid, strat in self._strategies.items():
            try:
                out["strategies"][sid] = strat.get_stats()
            except Exception:
                log.exception("strategy_get_stats_failed", strategy_id=sid)
                out["strategies"][sid] = {"error": "stats_failed"}
        return out

    # ── Internal ─────────────────────────────────────────────────────────────

    async def _broadcast(self, method_name: str) -> None:
        for strat in self._strategies.values():
            try:
                await getattr(strat, method_name)()
            except Exception:
                log.exception(
                    "strategy_broadcast_failed",
                    strategy_id=strat.strategy_id,
                    method=method_name,
                )
