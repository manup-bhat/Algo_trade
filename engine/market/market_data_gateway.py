"""
engine/market/market_data_gateway.py — Refcounted WebSocket subscription owner.

THE single owner of AsyncKiteTicker subscriptions. All subscribe/unsubscribe
calls go through this gateway — no other module touches the ticker directly.

Architecture (Part 2 §4.1, Part 3 §5 Phase 1):
  - Refcount map: (instrument_token, mode) → set of subscriber_ids (strategy IDs).
  - Mode upgrade rule: if any subscriber needs 'full', token is subscribed at 'full'
    for all holders.  NEVER downgrade mid-session (only on ref→0 unsubscribe).
  - Token ceiling: hard alert at 2,700 tokens (Zerodha WS cap is 3,000).
  - Reconnect: gateway owns the resubscription state — on WS reconnect, it
    re-subscribes all currently held tokens at their recorded modes.

Mode hierarchy (lowest → highest):
    ltp < quote < full

An existing 'quote' subscription upgraded by a new 'full' subscriber sends a
set_mode(FULL) call; the 'ltp' subscriber doesn't need to know.

Edge cases handled:
  1. Concurrent subscribe calls (two strategies activating simultaneously) —
     asyncio.Lock protects all subscription dict mutations.
  2. Zero-token subscribe call — no-op (no error, no WS call).
  3. Strategy deactivated while still holding a position — token stays subscribed
     if another strategy also holds it; only subscriber_id removed from refcount.
  4. Mode collision (full + ltp) → full wins.
  5. Token ceiling (≥ 2,700) → CRITICAL log + pub:alerts event.
  6. Reconnect — re-subscribes all tokens from internal state (not from ticker's own state).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from engine.kite.ticker import AsyncKiteTicker
    from engine.store.redis_store import RedisStore

log = structlog.get_logger(__name__)

# Zerodha WebSocket hard limit: 3,000 tokens per connection.
# Alert threshold: 2,700 (10% headroom).
_WS_HARD_LIMIT = 3_000
_ALERT_THRESHOLD = 2_700

# Mode hierarchy: higher = heavier (more data)
_MODE_RANK = {"ltp": 0, "quote": 1, "full": 2}
_DEFAULT_MODE = "quote"

# Kite ticker mode constants (matches AsyncKiteTicker.MODE_*)
MODE_LTP   = "ltp"
MODE_QUOTE = "quote"
MODE_FULL  = "full"


class MarketDataGateway:
    """
    Refcounted subscription manager for the Kite WebSocket feed.

    Wraps AsyncKiteTicker and is the ONLY code that calls ticker.subscribe/
    unsubscribe/set_mode.  Strategies declare their data needs (via the manifest
    requirements block) and the gateway figures out what to do on the wire.

    Usage:
        gateway = MarketDataGateway(ticker, redis_store)
        await gateway.subscribe("ivbs", [123, 456, 789], mode="quote")
        await gateway.subscribe("options_momentum", [111, 222], mode="full")
        # Token 123 is now at quote, 111 at full.

        await gateway.unsubscribe("ivbs")  # removes ivbs from all refcounts
        # If 123/456/789 had no other subscribers → unsubscribed from WS.

        # On WS reconnect:
        await gateway.on_reconnect()        # re-subscribes all active tokens
    """

    def __init__(
        self,
        ticker: "AsyncKiteTicker | None" = None,
        redis_store: "RedisStore | None" = None,
    ) -> None:
        self._ticker = ticker
        self._redis = redis_store
        self._lock = asyncio.Lock()

        # token → set of subscriber_ids
        self._subscribers: dict[int, set[str]] = {}
        # token → current active mode (the max mode across all subscribers)
        self._active_mode: dict[int, str] = {}
        # strategy_id → set of tokens it has subscribed (for bulk unsubscribe)
        self._strategy_tokens: dict[str, set[int]] = {}
        # strategy_id → declared mode
        self._strategy_modes: dict[str, str] = {}

    def set_ticker(self, ticker: "AsyncKiteTicker") -> None:
        """Wire ticker after it's created (called from runner.py)."""
        self._ticker = ticker

    def set_redis(self, redis_store: "RedisStore") -> None:
        """Wire redis after it's created (called from runner.py)."""
        self._redis = redis_store

    # ── Public: subscribe/unsubscribe ─────────────────────────────────────────

    async def subscribe(
        self,
        subscriber_id: str,
        tokens: list[int],
        mode: str = _DEFAULT_MODE,
    ) -> None:
        """
        Subscribe *subscriber_id* to *tokens* at *mode*.

        Idempotent: calling again with the same tokens is safe (may trigger a
        mode upgrade if the new mode is heavier).

        Args:
            subscriber_id: Unique ID for the subscriber (strategy_id or other key).
            tokens:        List of instrument tokens to subscribe.
            mode:          "ltp", "quote", or "full".
        """
        if not tokens:
            log.debug("market_data_gateway_empty_token_list", subscriber_id=subscriber_id)
            return

        mode = mode.lower()
        if mode not in _MODE_RANK:
            log.warning(
                "market_data_gateway_unknown_mode",
                mode=mode,
                subscriber_id=subscriber_id,
                fallback=_DEFAULT_MODE,
            )
            mode = _DEFAULT_MODE

        async with self._lock:
            to_subscribe_new: list[int] = []
            to_upgrade: dict[int, str] = {}  # token → new mode

            for token in tokens:
                if token not in self._subscribers:
                    # Brand new token — subscribe at requested mode
                    self._subscribers[token] = set()
                    self._active_mode[token] = mode
                    to_subscribe_new.append(token)
                else:
                    # Already subscribed — check for mode upgrade
                    current_mode = self._active_mode[token]
                    if _MODE_RANK[mode] > _MODE_RANK[current_mode]:
                        # Upgrade needed
                        self._active_mode[token] = mode
                        to_upgrade[token] = mode

                # Add subscriber to refcount
                self._subscribers[token].add(subscriber_id)

            # Record which tokens this strategy owns (for bulk unsubscribe)
            self._strategy_tokens.setdefault(subscriber_id, set()).update(tokens)
            self._strategy_modes[subscriber_id] = mode

            # Check ceiling before sending to WS
            total = len(self._subscribers)
            if total >= _ALERT_THRESHOLD:
                await self._fire_ceiling_alert(total)

            # Apply WS changes (outside critical path — ticker calls go here)
            if to_subscribe_new and self._ticker:
                self._ticker.subscribe(to_subscribe_new)
                self._ticker.set_mode(to_subscribe_new, mode)
                log.info(
                    "market_data_gateway_subscribed",
                    subscriber_id=subscriber_id,
                    count=len(to_subscribe_new),
                    mode=mode,
                )

            if to_upgrade and self._ticker:
                for token, new_mode in to_upgrade.items():
                    self._ticker.set_mode([token], new_mode)
                log.info(
                    "market_data_gateway_mode_upgraded",
                    subscriber_id=subscriber_id,
                    count=len(to_upgrade),
                    new_mode=mode,
                )

    async def unsubscribe(self, subscriber_id: str) -> None:
        """
        Remove *subscriber_id* from all its subscribed tokens.

        Tokens with no remaining subscribers are unsubscribed from the WS.
        Tokens still held by other subscribers keep their current mode
        (never downgraded — mode is recalculated from remaining subscribers).

        Edge case: if subscriber_id was never registered, this is a no-op.
        """
        async with self._lock:
            tokens = self._strategy_tokens.pop(subscriber_id, set())
            self._strategy_modes.pop(subscriber_id, None)

            if not tokens:
                return

            to_unsubscribe: list[int] = []

            for token in tokens:
                subs = self._subscribers.get(token, set())
                subs.discard(subscriber_id)

                if not subs:
                    # No more subscribers for this token — unsubscribe
                    del self._subscribers[token]
                    del self._active_mode[token]
                    to_unsubscribe.append(token)
                else:
                    # Recalculate mode from remaining subscribers
                    # (handles case where the heaviest subscriber just left)
                    new_mode = self._max_mode_for_token(token, subs)
                    old_mode = self._active_mode[token]
                    # Intentionally NOT downgrading mid-session.
                    # Mode downgrades only happen at session end (on_session_end).
                    if _MODE_RANK[new_mode] > _MODE_RANK[old_mode]:
                        self._active_mode[token] = new_mode
                        if self._ticker:
                            self._ticker.set_mode([token], new_mode)

            if to_unsubscribe and self._ticker:
                self._ticker.unsubscribe(to_unsubscribe)
                log.info(
                    "market_data_gateway_unsubscribed",
                    subscriber_id=subscriber_id,
                    count=len(to_unsubscribe),
                )

    # ── Reconnect ─────────────────────────────────────────────────────────────

    async def on_reconnect(self) -> None:
        """
        Re-subscribe all currently held tokens after a WebSocket reconnect.

        Called by AsyncKiteTicker's _on_connect callback (set during gateway init).
        Ownership of reconnect resubscription lives HERE, not in the ticker.

        This prevents the ticker from accumulating stale internal state while
        the gateway knows the true desired subscription set.
        """
        async with self._lock:
            if not self._subscribers:
                return

            # Group tokens by mode for batch subscribe calls
            by_mode: dict[str, list[int]] = {}
            for token, mode in self._active_mode.items():
                by_mode.setdefault(mode, []).append(token)

            for mode, tokens in by_mode.items():
                if self._ticker and tokens:
                    self._ticker.subscribe(tokens)
                    self._ticker.set_mode(tokens, mode)

            total = sum(len(t) for t in by_mode.values())
            log.info(
                "market_data_gateway_reconnect_resubscribed",
                total_tokens=total,
                by_mode={m: len(t) for m, t in by_mode.items()},
            )

    # ── Session end ───────────────────────────────────────────────────────────

    async def on_session_end(self) -> None:
        """
        Clean up all subscriptions at session end (15:25 IST).

        This is the only point where mode downgrades are safe.
        After calling this, the gateway is clean for the next session.
        """
        async with self._lock:
            tokens = list(self._subscribers.keys())
            self._subscribers.clear()
            self._active_mode.clear()
            self._strategy_tokens.clear()
            self._strategy_modes.clear()

            if tokens and self._ticker:
                self._ticker.unsubscribe(tokens)
                log.info("market_data_gateway_session_end_cleanup", count=len(tokens))

    # ── Queries ───────────────────────────────────────────────────────────────

    def get_active_token_count(self) -> int:
        """Return the number of currently subscribed tokens."""
        return len(self._subscribers)

    def get_active_mode(self, token: int) -> str | None:
        """Return the current mode for *token*, or None if not subscribed."""
        return self._active_mode.get(token)

    def is_subscribed(self, token: int) -> bool:
        """Return True if *token* is currently subscribed."""
        return token in self._subscribers

    def get_subscriber_count(self, token: int) -> int:
        """Return the number of active subscribers for *token*."""
        return len(self._subscribers.get(token, set()))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _max_mode_for_token(self, token: int, subscribers: set[str]) -> str:
        """Return the max (heaviest) mode across remaining subscribers for *token*."""
        max_mode = "ltp"
        for sid in subscribers:
            m = self._strategy_modes.get(sid, "ltp")
            if _MODE_RANK[m] > _MODE_RANK[max_mode]:
                max_mode = m
        return max_mode

    async def _fire_ceiling_alert(self, total: int) -> None:
        """Fire a CRITICAL log and Redis pub:alerts event when nearing the WS token ceiling."""
        log.critical(
            "market_data_gateway_token_ceiling_alert",
            active_tokens=total,
            alert_threshold=_ALERT_THRESHOLD,
            hard_limit=_WS_HARD_LIMIT,
            hint="Unsubscribe inactive strategies or split into multiple connections.",
        )
        if self._redis is not None:
            try:
                import json
                await self._redis._r.publish(
                    "pub:alerts",
                    json.dumps({
                        "type": "ws_token_ceiling",
                        "active_tokens": total,
                        "threshold": _ALERT_THRESHOLD,
                        "hard_limit": _WS_HARD_LIMIT,
                    }),
                )
            except Exception as exc:
                log.error("market_data_gateway_alert_publish_failed", error=str(exc))


# Module-level singleton — wired in runner.py after ticker and redis are created
market_data_gateway = MarketDataGateway()
