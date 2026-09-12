"""
tests/unit/test_capability_registry.py — Unit tests for capability_registry.

Covers:
    - CapabilityProvider Protocol structural check
    - Registry register/get/list_keys
    - compute_capabilities() fan-out: missing key, provider error, empty keys
    - MarketContext construction
"""

from __future__ import annotations

import pytest

from engine.core.capability_registry import (
    MarketContext,
    CapabilityProvider,
    capability_registry as _global_registry,
    compute_capabilities,
)
from engine.core.registry import Registry


# ── Helpers ───────────────────────────────────────────────────────────────────

class DummyProvider:
    key = "dummy"

    async def compute(self, ctx: MarketContext):
        return {"symbol": ctx.symbol, "value": 42}


class BrokenProvider:
    key = "broken"

    async def compute(self, ctx: MarketContext):
        raise RuntimeError("intentional failure")


# ── Registry unit tests ───────────────────────────────────────────────────────

class TestCapabilityRegistry:
    def test_register_and_get(self):
        reg: Registry = Registry()
        p = DummyProvider()
        reg.register("dummy", p)
        assert reg.get_or_none("dummy") is p

    def test_get_missing_returns_none(self):
        reg: Registry = Registry()
        assert reg.get_or_none("nonexistent") is None

    def test_list_keys(self):
        reg: Registry = Registry()
        reg.register("a", DummyProvider())
        reg.register("b", DummyProvider())
        assert set(reg.list_keys()) >= {"a", "b"}

    def test_duplicate_key_raises(self):
        reg: Registry = Registry()
        reg.register("dup", DummyProvider())
        with pytest.raises((ValueError, KeyError)):
            reg.register("dup", DummyProvider())


class TestMarketContext:
    def test_defaults(self):
        ctx = MarketContext(symbol="RELIANCE")
        assert ctx.symbol == "RELIANCE"
        assert ctx.spot_price == 0.0
        assert ctx.underlying == ""
        assert ctx.extra == {}

    def test_custom_fields(self):
        ctx = MarketContext(
            symbol="NIFTY23SEP21000CE",
            underlying="NIFTY",
            spot_price=19_500.0,
            extra={"strike": 21000.0},
        )
        assert ctx.underlying == "NIFTY"
        assert ctx.extra["strike"] == 21000.0


# ── compute_capabilities() tests ──────────────────────────────────────────────

class TestComputeCapabilities:
    @pytest.fixture
    def local_registry(self, monkeypatch):
        reg = Registry()
        reg.register("dummy", DummyProvider())
        reg.register("broken", BrokenProvider())
        # monkeypatch the module-level registry
        monkeypatch.setattr(
            "engine.core.capability_registry.capability_registry",
            reg,
        )
        return reg

    @pytest.mark.asyncio
    async def test_empty_keys(self, local_registry):
        ctx = MarketContext(symbol="RELIANCE")
        result = await compute_capabilities([], ctx)
        assert result == {}

    @pytest.mark.asyncio
    async def test_happy_path(self, local_registry):
        ctx = MarketContext(symbol="RELIANCE")
        result = await compute_capabilities(["dummy"], ctx)
        assert "dummy" in result
        assert result["dummy"]["value"] == 42

    @pytest.mark.asyncio
    async def test_missing_key_skipped(self, local_registry):
        ctx = MarketContext(symbol="RELIANCE")
        result = await compute_capabilities(["not_registered"], ctx)
        assert "not_registered" not in result
        assert result == {}

    @pytest.mark.asyncio
    async def test_broken_provider_excluded(self, local_registry):
        ctx = MarketContext(symbol="RELIANCE")
        result = await compute_capabilities(["broken"], ctx)
        # broken provider raises → excluded from result
        assert "broken" not in result

    @pytest.mark.asyncio
    async def test_mixed_keys(self, local_registry):
        ctx = MarketContext(symbol="RELIANCE")
        result = await compute_capabilities(["dummy", "missing", "broken"], ctx)
        assert "dummy" in result
        assert "missing" not in result
        assert "broken" not in result

    @pytest.mark.asyncio
    async def test_none_value_included(self, monkeypatch):
        """Providers returning None are included (None is a valid output)."""

        class NoneProvider:
            key = "none_val"
            async def compute(self, ctx):
                return None

        reg = Registry()
        reg.register("none_val", NoneProvider())
        monkeypatch.setattr("engine.core.capability_registry.capability_registry", reg)

        ctx = MarketContext(symbol="X")
        result = await compute_capabilities(["none_val"], ctx)
        assert "none_val" in result
        assert result["none_val"] is None
