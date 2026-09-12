"""
engine/market/candle_aggregator.py — Shared CandleBuilder management service.

Owns ALL CandleBuilder instances for the session so:
  1. Multiple strategies needing the same symbol share one builder (dedup).
  2. Coordinator delegates builder lifecycle here instead of managing a raw dict.
  3. Reconnect baseline resets and session resets are handled centrally.

This is the Phase 1 generalisation of the `_builders: dict[str, CandleBuilder]`
dict previously embedded in Coordinator (engine/strategy/coordinator.py).

Key invariant:
  A symbol is unregistered ONLY if no strategy currently holds it as active.
  This is checked via StrategyRouter.any_strategy_has_active_symbol() before
  removal — the same guard used for watchlist hot-removal.

Thread safety: all methods run on the asyncio event loop (called only from
coroutines dispatched by AsyncKiteTicker via run_coroutine_threadsafe).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from engine.market.candle_builder import CandleBuilder

if TYPE_CHECKING:
    pass

log = structlog.get_logger(__name__)


class CandleAggregator:
    """
    Central registry and lifecycle manager for per-symbol CandleBuilder instances.

    Usage:
        aggregator = CandleAggregator()
        builder = aggregator.register_symbol("RELIANCE")   # idempotent

        # In tick handler:
        candle = aggregator.on_tick(symbol, ltp, cum_vol, exchange_ts)
        if candle:
            await strategy_router.on_candle(symbol, candle, aggregator.get_builder(symbol), token)

        # On reconnect:
        aggregator.reset_all_baselines()

        # On 09:15 market open:
        aggregator.reset_session()
    """

    def __init__(self, sma_period: int = 500, atr_period: int = 14) -> None:
        self._builders: dict[str, CandleBuilder] = {}
        self._sma_period = sma_period
        self._atr_period = atr_period

    # ── Registration ──────────────────────────────────────────────────────────

    def register_symbol(self, symbol: str) -> CandleBuilder:
        """
        Register *symbol* and return its CandleBuilder.

        Idempotent: if *symbol* is already registered, returns the existing
        builder without creating a new one.  This is the correct behaviour
        when two strategies both declare the same symbol — they share one builder.

        Returns:
            The CandleBuilder for *symbol* (new or existing).
        """
        if symbol not in self._builders:
            self._builders[symbol] = CandleBuilder(
                symbol,
                sma_period=self._sma_period,
                atr_period=self._atr_period,
            )
            log.debug("candle_aggregator_symbol_registered", symbol=symbol)
        return self._builders[symbol]

    def unregister_symbol(
        self,
        symbol: str,
        strategy_router: Any | None = None,
    ) -> bool:
        """
        Unregister *symbol* and discard its CandleBuilder.

        Safety gate: if *strategy_router* is provided, checks
        `strategy_router.any_strategy_has_active_symbol(symbol)` first.
        If any strategy still holds *symbol* active (MANAGING state), the
        unregister is blocked and returns False.

        Args:
            symbol:          Symbol to remove.
            strategy_router: Optional router for the active-symbol guard.

        Returns:
            True if unregistered, False if blocked by active strategy.
        """
        if symbol not in self._builders:
            return True  # Already gone — idempotent

        if strategy_router is not None:
            try:
                if strategy_router.any_strategy_has_active_symbol(symbol):
                    log.warning(
                        "candle_aggregator_unregister_blocked",
                        symbol=symbol,
                        reason="strategy_has_active_position",
                    )
                    return False
            except Exception:
                log.exception("candle_aggregator_active_check_failed", symbol=symbol)
                return False  # Fail safe: don't remove if check errored

        del self._builders[symbol]
        log.debug("candle_aggregator_symbol_unregistered", symbol=symbol)
        return True

    # ── Tick routing ──────────────────────────────────────────────────────────

    def on_tick(
        self,
        symbol: str,
        ltp: float,
        cum_vol: int,
        exchange_ts: "import datetime; datetime.datetime",
    ) -> "CandleBuilder | None":
        """
        Forward a tick to the appropriate CandleBuilder.

        Returns the builder if a completed candle is ready (same API as
        CandleBuilder.on_tick), or None if the symbol is not registered or
        no candle completed.

        Edge cases:
          - Token arrives for unregistered symbol (index tick, F&O instrument not
            subscribed by any strategy yet) → log debug, return None.
          - Builder raises an exception → caught, logged, returns None.
            A builder crash must never propagate up to the coordinator.
        """
        builder = self._builders.get(symbol)
        if builder is None:
            log.debug("candle_aggregator_unknown_symbol_tick", symbol=symbol)
            return None

        try:
            return builder.on_tick(ltp, cum_vol, exchange_ts)
        except Exception:
            log.exception("candle_builder_on_tick_failed", symbol=symbol)
            return None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def reset_all_baselines(self) -> None:
        """
        Reset cumulative volume baselines for all registered builders.

        Must be called on every WebSocket reconnect (Bug 4 fix — prevents
        phantom volume spikes from pre-open volume replay after reconnect).

        This is the centralised version of what used to be individual
        `builder.reset_cumulative_baseline()` calls scattered in Coordinator.
        """
        count = 0
        for builder in self._builders.values():
            try:
                builder.reset_cumulative_baseline()
                count += 1
            except Exception:
                log.exception("candle_builder_reset_failed", symbol=builder.symbol)
        log.info("candle_aggregator_baselines_reset", count=count)

    def reset_session(self) -> None:
        """
        Reset all builders for a fresh trading session (called at 09:15).

        Does NOT discard the SMA history — the 500-period deque is preserved
        across session boundaries (it spans multiple days by design).
        Clears only the intraday candle state (current open candle, VWAP, ATR).
        CandleBuilder.reset() is the correct method (equivalent to reset_session).
        """
        count = 0
        for builder in self._builders.values():
            try:
                builder.reset()  # CandleBuilder's session reset (preserves SMA history)
                count += 1
            except Exception:
                log.exception("candle_builder_session_reset_failed", symbol=builder.symbol)
        log.info("candle_aggregator_session_reset", count=count)

    # ── Queries ───────────────────────────────────────────────────────────────

    def get_builder(self, symbol: str) -> CandleBuilder | None:
        """Return the CandleBuilder for *symbol*, or None if not registered."""
        return self._builders.get(symbol)

    @property
    def active_symbols(self) -> list[str]:
        """Return a snapshot of all currently registered symbols."""
        return list(self._builders.keys())

    def __len__(self) -> int:
        return len(self._builders)

    def __contains__(self, symbol: str) -> bool:
        return symbol in self._builders


# Module-level singleton — populated by Coordinator via register_symbol()
candle_aggregator = CandleAggregator()
