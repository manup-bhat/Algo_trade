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

import asyncio
from typing import TYPE_CHECKING, Any

import structlog

from engine.core.base_strategy import BaseStrategy

if TYPE_CHECKING:
    import datetime

    from engine.kite.client import AsyncKiteClient
    from engine.market.candle_builder import Candle, CandleBuilder
    from engine.market.market_data_gateway import MarketDataGateway
    from engine.orders.fill_timeout import FillTimeoutManager
    from engine.orders.order_service import OrderService
    from engine.orders.order_tracker import OrderTracker
    from engine.risk.capital_allocator import CapitalAllocator

log = structlog.get_logger(__name__)


class StrategyRouter:
    """Holds all registered strategies and dispatches engine events to them."""

    def __init__(self) -> None:
        self._strategies: dict[str, BaseStrategy] = {}
        # Phase 2 optional dependencies (injected via wire() after startup)
        self._market_data_gateway: MarketDataGateway | None = None
        self._capital_allocator: CapitalAllocator | None = None

    # ── Dependency injection ─────────────────────────────────────────────────

    def wire(
        self,
        market_data_gateway: MarketDataGateway | None = None,
        capital_allocator: CapitalAllocator | None = None,
    ) -> None:
        """
        Inject Phase 2 dependencies for manifest-based subscription.

        Called from runner.py after all services are initialized. Safe to
        call multiple times (idempotent — new refs overwrite old ones).

        Args:
            market_data_gateway: Gateway for refcounted WS subscriptions.
            capital_allocator:   Ledger for per-strategy capital tracking.
        """
        if market_data_gateway is not None:
            self._market_data_gateway = market_data_gateway
        if capital_allocator is not None:
            self._capital_allocator = capital_allocator
        log.info(
            "strategy_router_wired",
            gateway=market_data_gateway is not None,
            allocator=capital_allocator is not None,
        )

    # ── Registration / lookup ────────────────────────────────────────────────

    def register(
        self,
        strategy: BaseStrategy,
        manifest: Any | None = None,  # StrategyManifest (avoid circular import)
    ) -> None:
        """
        Register a strategy and optionally resolve its manifest.

        If a manifest is provided AND gateway/capital_allocator are wired:
          - Calls market_data_gateway.on_strategy_activated(sid, manifest)
            so the gateway subscribes required instruments.
          - Calls capital_allocator.allocate(sid, manifest.capital.allocated)
            so the 10th pre-trade check is armed.

        Backwards-compatible: manifest=None → same behaviour as before.

        Edge cases:
          - Manifest has no `requirements` block → no subscription, no error.
          - Gateway not wired → subscription skipped, warning logged.
          - Duplicate strategy_id → raises ValueError (unchanged).
        """
        sid = strategy.strategy_id
        if sid in self._strategies:
            raise ValueError(f"strategy_id already registered: {sid!r}")
        self._strategies[sid] = strategy
        log.info("strategy_registered", strategy_id=sid, cls=type(strategy).__name__)

        # Manifest-resolution side-effects (Phase 2)
        if manifest is not None:
            self._resolve_manifest(sid, manifest)

    def _resolve_manifest(self, sid: str, manifest: Any) -> None:
        """
        Trigger gateway subscription + capital allocation from manifest.

        Uses asyncio.create_task so it doesn't block the synchronous register() call.
        This is safe because register() is always called from an async context
        (runner.py's async main or job functions).
        """
        # Capital allocation (sync — CapitalAllocator.allocate is not async)
        if self._capital_allocator is not None:
            try:
                allocated = 0.0
                capital_block = getattr(manifest, "capital", None)
                if capital_block and isinstance(capital_block, dict):
                    allocated = float(capital_block.get("allocated", 0.0))
                elif capital_block and hasattr(capital_block, "allocated"):
                    allocated = float(capital_block.allocated)
                if allocated > 0:
                    self._capital_allocator.allocate(sid, allocated)
                    log.info(
                        "strategy_capital_allocated_from_manifest",
                        strategy_id=sid,
                        allocated_inr=allocated,
                    )
            except Exception as exc:
                log.error(
                    "strategy_manifest_capital_allocation_failed",
                    strategy_id=sid,
                    error=str(exc),
                )

        # Gateway subscription (async — schedule as background task)
        if self._market_data_gateway is not None:
            requirements = getattr(manifest, "requirements", None)
            if requirements:
                asyncio.create_task(
                    self._market_data_gateway.on_strategy_activated(sid, manifest),
                    name=f"gateway_subscribe_{sid}",
                )
                log.info(
                    "strategy_gateway_subscription_scheduled",
                    strategy_id=sid,
                )
            else:
                log.debug(
                    "strategy_manifest_no_requirements",
                    strategy_id=sid,
                    hint="Strategy will use universe watchlist path (backwards-compatible).",
                )

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
