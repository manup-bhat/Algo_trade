"""
engine/kite/ticker.py — AsyncKiteTicker: KiteTicker thread → asyncio bridge.

KiteTicker connects in a background thread and fires callbacks on that thread.
This class bridges all callbacks to the asyncio event loop using
asyncio.run_coroutine_threadsafe(), which is the correct and thread-safe API.

CRITICAL: _dispatch() is the only method called from the KiteTicker thread.
All other methods run on the asyncio event loop.

WebSocket mode: MODE_QUOTE for all instruments.
Delivers: instrument_token, last_price, volume_traded, exchange_timestamp,
          last_trade_time, ohlc (day OHLC).
MODE_FULL (market depth) is not used — unnecessary bandwidth.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from engine.strategy.coordinator import Coordinator

log = structlog.get_logger(__name__)

# KiteTicker subscription modes
MODE_LTP = "ltp"
MODE_QUOTE = "quote"
MODE_FULL = "full"


class AsyncKiteTicker:
    """
    Thread-to-asyncio bridge for KiteTicker WebSocket.

    Architecture:
        KiteTicker runs connect(threaded=True) — this spawns an internal thread.
        All callbacks (_on_ticks, _on_connect, etc.) fire on that thread.
        We use asyncio.run_coroutine_threadsafe(coro, loop) to safely dispatch
        coroutines from the KiteTicker thread to the main asyncio event loop.

    Key invariant:
        self._loop is captured at __init__ time from the already-running event loop.
        Never create a new event loop — use the one the engine is running on.
    """

    def __init__(
        self,
        api_key: str,
        access_token: str,
        loop: asyncio.AbstractEventLoop,
        coordinator: "Coordinator",
    ) -> None:
        self._api_key = api_key
        self._access_token = access_token
        self._loop = loop
        self._coordinator = coordinator

        self._ticker: Any = None  # KiteTicker instance (created in start())
        self._subscribed_tokens: list[int] = []
        self._reconnect_attempts: int = 0

    def _dispatch(self, coro: Any) -> asyncio.Future:  # type: ignore[type-arg]
        """
        Thread-safe dispatch of a coroutine to the asyncio event loop.
        Called from KiteTicker's background thread.
        Returns a concurrent.futures.Future (not asyncio.Future) wrapping the coroutine.
        """
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    # ── Public control API (called from asyncio event loop) ───────────────

    def start(self) -> None:
        """
        Initialize and connect KiteTicker.
        Called once from runner.py after event loop is running.
        """
        try:
            from kiteconnect import KiteTicker  # type: ignore[import-untyped]
        except ImportError:
            log.critical("kiteconnect_not_installed", hint="pip install kiteconnect")
            raise

        self._ticker = KiteTicker(self._api_key, self._access_token)

        # Register callbacks — these fire on KiteTicker's internal thread
        self._ticker.on_ticks = self._on_ticks
        self._ticker.on_order_update = self._on_order_update
        self._ticker.on_connect = self._on_connect
        self._ticker.on_close = self._on_close
        self._ticker.on_reconnect = self._on_reconnect
        self._ticker.on_noreconnect = self._on_noreconnect
        self._ticker.on_error = self._on_error

        log.info("kite_ticker_connecting")
        # threaded=True spawns a background thread; connect() returns immediately
        self._ticker.connect(threaded=True)

    def stop(self) -> None:
        """Gracefully disconnect WebSocket."""
        if self._ticker is not None:
            log.info("kite_ticker_stopping")
            self._ticker.stop()

    def subscribe(self, tokens: list[int]) -> None:
        """Subscribe to instrument tokens on the WebSocket."""
        if self._ticker is None:
            log.warning("subscribe_called_before_ticker_started")
            return
        self._subscribed_tokens = tokens
        self._ticker.subscribe(tokens)
        log.info("kite_ticker_subscribed", token_count=len(tokens))

    def set_mode(self, mode: str, tokens: list[int]) -> None:
        """Set subscription mode (quote/full/ltp) for given tokens."""
        if self._ticker is None:
            return
        self._ticker.set_mode(mode, tokens)
        log.debug("kite_ticker_mode_set", mode=mode, count=len(tokens))

    def unsubscribe(self, tokens: list[int]) -> None:
        if self._ticker is None:
            return
        self._ticker.unsubscribe(tokens)
        log.info("kite_ticker_unsubscribed", count=len(tokens))

    def add_tokens(self, tokens: list[int]) -> None:
        """Incrementally subscribe to new tokens (QUOTE mode) for a hot watchlist add.

        Unlike ``subscribe`` (which replaces the tracked token set), this appends
        to ``_subscribed_tokens`` so an in-session watchlist edit does not drop
        existing subscriptions.
        """
        current = list(getattr(self, "_subscribed_tokens", []) or [])
        new = [t for t in tokens if t not in current]
        if not new:
            return
        self._subscribed_tokens = current + new
        if self._ticker is not None:
            self._ticker.subscribe(new)
            self._ticker.set_mode(MODE_QUOTE, new)
        log.info("kite_ticker_tokens_added", added=len(new))

    def remove_tokens(self, tokens: list[int]) -> None:
        """Incrementally unsubscribe tokens for a hot watchlist removal."""
        drop = set(tokens)
        if not drop:
            return
        current = list(getattr(self, "_subscribed_tokens", []) or [])
        self._subscribed_tokens = [t for t in current if t not in drop]
        if self._ticker is not None:
            self._ticker.unsubscribe(list(drop))
        log.info("kite_ticker_tokens_removed", removed=len(drop))

    # ── KiteTicker callbacks (all run on background thread) ───────────────
    # Rule: NEVER do async work here. Always use _dispatch().

    def _on_ticks(self, ws: Any, ticks: list[dict]) -> None:
        """
        Hot path: called for every tick batch from the exchange.
        Dispatches to coordinator.process_ticks() on the asyncio event loop.
        """
        if not ticks:
            return
        self._dispatch(self._coordinator.process_ticks(ticks))

    def _on_order_update(self, ws: Any, message: dict) -> None:
        """
        Order postback (fill notification) from Kite.
        Dispatches to order_tracker.on_postback() on the event loop.
        """
        log.debug("order_update_received", order_id=message.get("order_id"))
        # order_tracker is wired in Phase 3; for now dispatch to coordinator
        self._dispatch(self._coordinator.on_order_postback(message))

    def _on_connect(self, ws: Any, response: dict) -> None:
        """
        Called on initial connect AND on every successful reconnect.
        Must: resubscribe all tokens, reset cumulative baselines (Bug 4 fix),
        and reset the reconnect attempt counter.
        """
        self._reconnect_attempts = 0
        log.info("kite_ws_connected", response=str(response)[:200])

        # Re-subscribe (Kite WS doesn't persist subscriptions across reconnects)
        if self._subscribed_tokens:
            from app.core.config import settings as _settings
            index_tokens = [
                _settings.NIFTY_INSTRUMENT_TOKEN,
                _settings.VIX_INSTRUMENT_TOKEN,
            ]
            # Subscribe ALL tokens first
            self._ticker.subscribe(self._subscribed_tokens)
            # Universe stocks: QUOTE mode (OHLCV + LTP)
            universe_tokens = [t for t in self._subscribed_tokens if t not in index_tokens]
            if universe_tokens:
                self._ticker.set_mode(MODE_QUOTE, universe_tokens)
            # Index tokens: LTP mode only (cheaper; we only need the price)
            live_index = [t for t in self._subscribed_tokens if t in index_tokens]
            if live_index:
                self._ticker.set_mode(MODE_LTP, live_index)

        # Bug 4 fix: reset all CandleBuilder baselines after reconnect
        self._dispatch(self._coordinator.on_websocket_connected())

    def _on_close(self, ws: Any, code: int, reason: str) -> None:
        log.warning("kite_ws_closed", code=code, reason=reason)

    def _on_reconnect(self, ws: Any, attempt: int) -> None:
        self._reconnect_attempts = attempt
        log.warning("kite_ws_reconnecting", attempt=attempt)
        # Notify coordinator that a reconnect is in progress
        self._dispatch(self._coordinator.on_websocket_reconnect())

    def _on_noreconnect(self, ws: Any) -> None:
        """
        Called when all reconnect attempts are exhausted.
        This is a CRITICAL failure — all positions must be protected.
        """
        log.critical(
            "kite_ws_fatal_disconnect",
            attempts=self._reconnect_attempts,
            action="emergency_close_all_positions",
        )
        self._dispatch(self._coordinator.on_fatal_disconnect())

    def _on_error(self, ws: Any, code: int, reason: str) -> None:
        log.error("kite_ws_error", code=code, reason=reason)
