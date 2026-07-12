"""
engine/core/base_strategy.py — Abstract base class for all strategy plugins.

Part of the multi-strategy engine refactor (Phase 1). Every trading strategy
(IVBS, ORB, an options strategy, ...) subclasses this. The engine (Coordinator +
StrategyRouter) calls these lifecycle hooks at the right points and never needs
to know anything strategy-specific.

Design principles:
  - Open/Closed        : add a strategy by implementing this ABC; never edit the engine.
  - Dependency Inversion: the engine depends on BaseStrategy, not on concretes.
  - Isolated failure   : the router wraps every call in try/except; one strategy's
                         exception must not crash the engine or sibling strategies.
  - No cross-coupling  : a strategy must NOT import another strategy.

Lifecycle (called by the engine):
    inject_execution()      once, after auth succeeds (before WS subscription)
    on_market_open()        09:15 — reset per-session state
    on_candle()             every completed 1-min candle, every universe symbol
    on_tick()               per tick, only for symbols this strategy marks active
    on_order_postback()     raw Kite order update — route to this strategy's tracking
    on_squareoff()          15:20 — force-close everything this strategy owns
    on_session_end()        15:25 — optional persistence/cleanup
    on_fatal_disconnect()   WS gave up — emergency close (defaults to squareoff)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from engine.core.strategy_config import load_strategy_config

if TYPE_CHECKING:
    import datetime

    from engine.kite.client import AsyncKiteClient
    from engine.market.candle_builder import Candle, CandleBuilder
    from engine.orders.fill_timeout import FillTimeoutManager
    from engine.orders.order_service import OrderService
    from engine.orders.order_tracker import OrderTracker
    from engine.store.db_writer import DbWriter
    from engine.store.redis_store import RedisStore


class BaseStrategy(ABC):
    """Abstract interface for a pluggable trading strategy."""

    def __init__(
        self,
        strategy_id: str,
        redis_store: "RedisStore",
        db_writer: "DbWriter",
    ) -> None:
        self.strategy_id = strategy_id
        self._redis = redis_store
        self._db = db_writer
        # Per-strategy config from engine/strategies/<id>/config.yaml ({} if none).
        self.config: dict[str, Any] = load_strategy_config(strategy_id)

        # Wired later by inject_execution() (after auth). None in warmup/paper-only.
        self._order_service: "OrderService | None" = None
        self._order_tracker: "OrderTracker | None" = None
        self._fill_timeout: "FillTimeoutManager | None" = None
        self._kite: "AsyncKiteClient | None" = None

        # STOP/START gate for fresh entries (managing existing positions continues).
        self._accept_new_entries: bool = True

    # ── Dependency injection ─────────────────────────────────────────────────

    def inject_execution(
        self,
        order_service: "OrderService",
        order_tracker: "OrderTracker",
        fill_timeout_manager: "FillTimeoutManager",
        kite: "AsyncKiteClient | None" = None,
    ) -> None:
        """Wire live-execution dependencies. Called once after auth succeeds."""
        self._order_service = order_service
        self._order_tracker = order_tracker
        self._fill_timeout = fill_timeout_manager
        self._kite = kite

    def set_new_entries_enabled(self, enabled: bool) -> None:
        """Enable/disable fresh entries (used by the STOP/START control)."""
        self._accept_new_entries = enabled

    @property
    def new_entries_enabled(self) -> bool:
        return self._accept_new_entries

    # ── Required lifecycle hooks ─────────────────────────────────────────────

    @abstractmethod
    async def on_market_open(self) -> None:
        """09:15 AM — reset internal per-session state for a fresh trading day."""
        raise NotImplementedError

    @abstractmethod
    async def on_candle(
        self,
        symbol: str,
        candle: "Candle",
        builder: "CandleBuilder",
        instrument_token: int,
    ) -> None:
        """Called for every completed 1-minute candle for every universe symbol."""
        raise NotImplementedError

    @abstractmethod
    async def on_order_postback(self, message: dict[str, Any]) -> None:
        """Route a raw Kite order postback to this strategy's order tracking.

        Must be idempotent and must ignore orders this strategy does not own.
        """
        raise NotImplementedError

    @abstractmethod
    async def on_squareoff(self) -> None:
        """15:20 PM — force-close every open position this strategy owns."""
        raise NotImplementedError

    @abstractmethod
    def get_stats(self) -> dict[str, Any]:
        """Return a JSON-serializable stats dict for the dashboard/logging."""
        raise NotImplementedError

    @abstractmethod
    def is_symbol_active(self, symbol: str) -> bool:
        """True if this strategy currently has live/managing state for the symbol.

        Used by the router to decide whether to forward per-tick updates.
        """
        raise NotImplementedError

    # ── Optional lifecycle hooks (safe defaults) ─────────────────────────────

    async def on_tick(
        self,
        symbol: str,
        ltp: float,
        exchange_ts: "datetime.datetime",
    ) -> None:
        """Per-tick hook for active (MANAGING) symbols only. Default: no-op."""
        return None

    async def on_session_end(self) -> None:
        """15:25 PM — optional cleanup/persistence. Default: no-op."""
        return None

    async def on_websocket_connected(self) -> None:
        """WS (re)connected. Default: no-op."""
        return None

    async def on_fatal_disconnect(self) -> None:
        """WS reconnection exhausted. Default: emergency square off."""
        await self.on_squareoff()
