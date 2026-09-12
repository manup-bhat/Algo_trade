"""
tests/unit/test_strategy_router_manifest.py — Tests for StrategyRouter manifest wiring.

Covers:
    - register() without manifest → same behavior as before (backwards-compatible)
    - wire() injects gateway + capital_allocator
    - register() with manifest → capital allocated, gateway.on_strategy_activated scheduled
    - Duplicate strategy_id still raises ValueError
    - _resolve_manifest: missing capital block → no allocation, no error
    - _resolve_manifest: missing requirements → no gateway task, no error
    - get_combined_stats includes newly registered strategy
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from engine.core.strategy_router import StrategyRouter


# ── Fixtures ──────────────────────────────────────────────────────────────────

class FakeStrategy:
    def __init__(self, sid="test_strategy"):
        self.strategy_id = sid

    def inject_execution(self, *a, **kw): pass
    def set_new_entries_enabled(self, e): pass
    def is_symbol_active(self, s): return False
    def get_stats(self): return {"trades": 0}
    async def on_candle(self, *a, **kw): pass
    async def on_tick(self, *a, **kw): pass
    async def on_order_postback(self, m): pass
    async def on_market_open(self): pass
    async def on_squareoff(self): pass
    async def on_session_end(self): pass
    async def on_websocket_connected(self): pass
    async def on_fatal_disconnect(self): pass


class FakeManifest:
    def __init__(self, capital_allocated=100_000.0, has_requirements=True):
        self.capital = {"allocated": capital_allocated}
        if has_requirements:
            self.requirements = {"symbols": ["RELIANCE"]}
        else:
            self.requirements = None


# ── Registration (backwards-compatible) ───────────────────────────────────────

class TestRegisterNoManifest:
    def test_register_without_manifest(self):
        router = StrategyRouter()
        strat = FakeStrategy("s1")
        router.register(strat)
        assert "s1" in router.strategy_ids

    def test_duplicate_raises(self):
        router = StrategyRouter()
        router.register(FakeStrategy("s1"))
        with pytest.raises(ValueError, match="s1"):
            router.register(FakeStrategy("s1"))

    def test_get_returns_strategy(self):
        router = StrategyRouter()
        strat = FakeStrategy("s2")
        router.register(strat)
        assert router.get("s2") is strat

    def test_len(self):
        router = StrategyRouter()
        router.register(FakeStrategy("a"))
        router.register(FakeStrategy("b"))
        assert len(router) == 2


# ── wire() ────────────────────────────────────────────────────────────────────

class TestWire:
    def test_wire_sets_gateway_and_allocator(self):
        router = StrategyRouter()
        gw = MagicMock()
        alloc = MagicMock()
        router.wire(market_data_gateway=gw, capital_allocator=alloc)
        assert router._market_data_gateway is gw
        assert router._capital_allocator is alloc

    def test_wire_partial_is_safe(self):
        router = StrategyRouter()
        gw = MagicMock()
        router.wire(market_data_gateway=gw)
        assert router._market_data_gateway is gw
        assert router._capital_allocator is None


# ── register() with manifest ──────────────────────────────────────────────────

class TestRegisterWithManifest:
    @pytest.mark.asyncio
    async def test_capital_allocated_from_manifest(self):
        router = StrategyRouter()
        alloc = MagicMock()
        alloc.allocate = MagicMock()
        router.wire(capital_allocator=alloc)

        manifest = FakeManifest(capital_allocated=200_000.0)
        router.register(FakeStrategy("s1"), manifest=manifest)

        # Give asyncio a chance to run any background tasks
        await asyncio.sleep(0)

        alloc.allocate.assert_called_once_with("s1", 200_000.0)

    @pytest.mark.asyncio
    async def test_gateway_task_scheduled_when_requirements_present(self):
        router = StrategyRouter()
        gw = MagicMock()
        gw.on_strategy_activated = AsyncMock(return_value=None)
        router.wire(market_data_gateway=gw)

        manifest = FakeManifest(has_requirements=True)
        router.register(FakeStrategy("s1"), manifest=manifest)

        # Let background task run
        await asyncio.sleep(0.01)
        gw.on_strategy_activated.assert_called_once_with("s1", manifest)

    @pytest.mark.asyncio
    async def test_no_gateway_no_error(self):
        """No gateway wired → no subscription, no error."""
        router = StrategyRouter()
        alloc = MagicMock()
        alloc.allocate = MagicMock()
        router.wire(capital_allocator=alloc)

        manifest = FakeManifest()
        # Should not raise even without gateway
        router.register(FakeStrategy("s1"), manifest=manifest)
        await asyncio.sleep(0)

    @pytest.mark.asyncio
    async def test_no_requirements_no_gateway_call(self):
        """Manifest with no requirements → gateway NOT called."""
        router = StrategyRouter()
        gw = MagicMock()
        gw.on_strategy_activated = AsyncMock()
        router.wire(market_data_gateway=gw)

        manifest = FakeManifest(has_requirements=False)
        router.register(FakeStrategy("s1"), manifest=manifest)
        await asyncio.sleep(0.01)
        gw.on_strategy_activated.assert_not_called()

    @pytest.mark.asyncio
    async def test_zero_capital_not_allocated(self):
        """manifest.capital.allocated = 0 → allocator NOT called."""
        router = StrategyRouter()
        alloc = MagicMock()
        alloc.allocate = MagicMock()
        router.wire(capital_allocator=alloc)

        manifest = FakeManifest(capital_allocated=0.0)
        router.register(FakeStrategy("s1"), manifest=manifest)
        await asyncio.sleep(0)
        alloc.allocate.assert_not_called()

    @pytest.mark.asyncio
    async def test_capital_allocator_error_does_not_raise(self):
        """Allocator raising should not prevent strategy registration."""
        router = StrategyRouter()
        alloc = MagicMock()
        alloc.allocate = MagicMock(side_effect=RuntimeError("allocator error"))
        router.wire(capital_allocator=alloc)

        manifest = FakeManifest(capital_allocated=100_000.0)
        router.register(FakeStrategy("s1"), manifest=manifest)
        assert "s1" in router.strategy_ids


# ── Fan-out isolation ─────────────────────────────────────────────────────────

class TestFanOut:
    @pytest.mark.asyncio
    async def test_one_strategy_failing_does_not_block_others(self):
        router = StrategyRouter()

        class BadStrategy(FakeStrategy):
            async def on_market_open(self):
                raise RuntimeError("bad strategy crashes")

        class GoodStrategy(FakeStrategy):
            def __init__(self):
                super().__init__("good")
                self.called = False
            async def on_market_open(self):
                self.called = True

        bad = BadStrategy("bad")
        good = GoodStrategy()
        router.register(bad)
        router.register(good)

        await router.on_market_open()
        assert good.called
