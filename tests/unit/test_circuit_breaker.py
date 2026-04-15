"""
tests/unit/test_circuit_breaker.py — Unit tests for CircuitBreaker.

Tests:
  - Trip at exactly 3% daily loss limit
  - Pass at 2.999% (below limit)
  - In-memory fast path bypasses Redis after first trip
  - reset() clears in-memory + Redis flag
  - Manual trip via trip() method
"""

from __future__ import annotations

import os

import fakeredis.aioredis
import pytest

os.environ.setdefault("KITE_API_KEY", "test")
os.environ.setdefault("KITE_API_SECRET", "test")


@pytest.fixture
async def redis_store():
    from engine.store.redis_store import RedisStore
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    store = RedisStore(r)
    yield store
    await r.aclose()


@pytest.fixture(autouse=True)
def reset_cb_singleton():
    """Circuit breaker is a singleton; reset in-memory flag between tests."""
    from engine.risk.circuit_breaker import circuit_breaker as _cb
    _cb._tripped = False
    yield
    _cb._tripped = False


@pytest.fixture
async def cb(redis_store):
    """Fresh circuit breaker with explicitly reset in-memory flag."""
    from engine.risk.circuit_breaker import CircuitBreaker
    breaker = CircuitBreaker()  # Fresh instance — not the singleton
    await redis_store.set_circuit_breaker(False)
    await redis_store.set_daily_pnl(0.0)
    await redis_store.set_capital(100_000.0)
    return breaker


class TestCircuitBreakerTrip:
    """Spec §13.2: Trip at DAILY_LOSS_LIMIT_PCT (default 3%) of capital."""

    async def test_pass_below_limit(self, cb, redis_store):
        """2.999% loss on ₹1L capital = ₹-2999 → should pass."""
        await redis_store.set_daily_pnl(-2999.0)
        ok, reason = await cb.check(redis_store)
        assert ok, f"Expected pass but got: {reason}"
        assert reason == ""

    async def test_trip_at_exact_limit(self, cb, redis_store):
        """Exactly 3% loss on ₹1L = ₹-3000 → must trip."""
        await redis_store.set_daily_pnl(-3000.0)
        ok, reason = await cb.check(redis_store)
        assert not ok
        assert "daily_loss_limit_breached" in reason

    async def test_trip_above_limit(self, cb, redis_store):
        """4% loss = ₹-4000 → must trip."""
        await redis_store.set_daily_pnl(-4000.0)
        ok, reason = await cb.check(redis_store)
        assert not ok

    async def test_zero_loss_passes(self, cb, redis_store):
        """Zero P&L (no trades today) → should pass."""
        await redis_store.set_daily_pnl(0.0)
        ok, _ = await cb.check(redis_store)
        assert ok

    async def test_positive_pnl_passes(self, cb, redis_store):
        """Profitable day → definitely passes."""
        await redis_store.set_daily_pnl(5000.0)
        ok, _ = await cb.check(redis_store)
        assert ok


class TestCircuitBreakerInMemoryFastPath:
    """Once tripped in-memory, check() must NOT query Redis again."""

    async def test_in_memory_fast_path(self, cb, redis_store):
        """
        Trip breaker via trip(), then reset Redis flag.
        check() should still return False from in-memory flag.
        """
        # Trip explicitly
        await cb.trip(redis_store, "manual_trip")
        assert cb._tripped is True

        # Reset Redis flag (but keep in-memory)
        await redis_store.set_circuit_breaker(False)
        await redis_store.set_daily_pnl(0.0)

        # In-memory flag should prevent trading
        ok, reason = await cb.check(redis_store)
        assert not ok
        assert "already_tripped" in reason


class TestCircuitBreakerReset:
    """Spec §13.2: Reset at 9:00 AM."""

    async def test_reset_clears_in_memory_and_redis(self, cb, redis_store):
        """After reset, check should pass (P&L = 0)."""
        await cb.trip(redis_store, "test_trip")
        assert cb._tripped is True

        await cb.reset(redis_store)

        assert cb._tripped is False
        # Redis flag should also be False
        is_tripped = await redis_store.is_circuit_breaker_tripped()
        assert not is_tripped

        # Check should now pass
        ok, _ = await cb.check(redis_store)
        assert ok

    async def test_reset_from_redis_flag(self, cb, redis_store):
        """Breaker tripped via Redis (cross-process). After reset, check passes."""
        await redis_store.set_circuit_breaker(True)

        ok, reason = await cb.check(redis_store)
        assert not ok
        assert "tripped_in_redis" in reason

        await cb.reset(redis_store)
        ok, _ = await cb.check(redis_store)
        assert ok


class TestCircuitBreakerZeroCapital:
    """If capital is 0 (not yet fetched), breaker should not trip."""

    async def test_zero_capital_passes(self, redis_store):
        from engine.risk.circuit_breaker import CircuitBreaker
        cb = CircuitBreaker()
        await redis_store.set_circuit_breaker(False)
        await redis_store.set_capital(0.0)
        await redis_store.set_daily_pnl(-5000.0)  # Big loss but no capital context

        ok, _ = await cb.check(redis_store)
        # capital=0 → loss_limit check skipped → should pass
        assert ok
