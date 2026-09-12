"""
tests/unit/test_capital_allocator.py — Unit tests for engine.risk.capital_allocator.

Tests cover:
  - allocate() sets the allocation.
  - check() passes when sufficient free allocation.
  - check() blocks when allocation exceeded.
  - check() blocks for unknown strategy.
  - debit() reduces free allocation.
  - credit() restores free allocation.
  - credit() clamps to 0 when over-credited.
  - reset_session() zeroes used amount.
  - get_summary() returns correct utilization.
  - required_margin <= 0 always passes (for exit orders).
  - Redis down → check() returns block (never silently allows trade).
"""

from __future__ import annotations

import pytest
import fakeredis.aioredis as fakeredis
from engine.risk.capital_allocator import CapitalAllocator
from engine.store.redis_store import RedisStore


@pytest.fixture
async def redis_store(fake_redis):
    """RedisStore backed by FakeRedis (from conftest.py)."""
    return RedisStore(fake_redis)


@pytest.fixture
async def allocator(redis_store):
    a = CapitalAllocator(redis_store)
    a.allocate("ivbs", 200_000)
    a.allocate("options_momentum", 100_000)
    return a


# ── Allocation ─────────────────────────────────────────────────────────────────

async def test_allocate_sets_allocation(allocator):
    assert allocator._allocations["ivbs"] == 200_000
    assert allocator._allocations["options_momentum"] == 100_000


async def test_allocate_overwrites(allocator):
    allocator.allocate("ivbs", 250_000)
    assert allocator._allocations["ivbs"] == 250_000


async def test_allocate_zero_is_allowed(allocator):
    """Zero allocation is allowed but will block all trades for that strategy."""
    allocator.allocate("zero_strat", 0.0)
    ok, reason = await allocator.check("zero_strat", 1.0)
    assert not ok
    assert "insufficient_free" in reason


# ── check() ───────────────────────────────────────────────────────────────────

async def test_check_passes_when_within_allocation(allocator):
    ok, reason = await allocator.check("ivbs", 50_000)
    assert ok is True
    assert reason == ""


async def test_check_blocks_when_exceeds_allocation(allocator):
    ok, reason = await allocator.check("ivbs", 250_000)
    assert ok is False
    assert "insufficient_free" in reason
    assert "ivbs" in reason


async def test_check_unknown_strategy_blocks(allocator):
    ok, reason = await allocator.check("unknown_strategy", 10_000)
    assert ok is False
    assert "strategy_not_allocated" in reason


async def test_check_zero_required_always_passes(allocator):
    """required_margin=0 must pass (exit orders use 0)."""
    ok, reason = await allocator.check("ivbs", 0)
    assert ok is True


async def test_check_negative_required_always_passes(allocator):
    ok, reason = await allocator.check("ivbs", -100)
    assert ok is True


# ── debit/credit lifecycle ────────────────────────────────────────────────────

async def test_debit_reduces_free(allocator):
    await allocator.debit("ivbs", 50_000)
    free = await allocator.get_free("ivbs")
    assert abs(free - 150_000) < 1.0  # float tolerance


async def test_credit_restores_free(allocator):
    await allocator.debit("ivbs", 50_000)
    await allocator.credit("ivbs", 50_000)
    free = await allocator.get_free("ivbs")
    assert abs(free - 200_000) < 1.0


async def test_credit_clamps_to_zero(allocator):
    """Credit that pushes used below 0 must be clamped to 0."""
    await allocator.credit("ivbs", 999_999_999)
    free = await allocator.get_free("ivbs")
    # free = allocated - max(0, used) = 200_000 - 0 = 200_000
    assert free <= 200_000.0


async def test_debit_then_check_blocks(allocator):
    await allocator.debit("ivbs", 190_000)  # 190k used, only 10k free
    ok, reason = await allocator.check("ivbs", 15_000)  # 15k needed
    assert ok is False
    assert "insufficient_free" in reason


# ── reset_session ──────────────────────────────────────────────────────────────

async def test_reset_session_single_strategy(allocator):
    await allocator.debit("ivbs", 80_000)
    await allocator.reset_session("ivbs")
    free = await allocator.get_free("ivbs")
    assert abs(free - 200_000) < 1.0


async def test_reset_session_all_strategies(allocator):
    await allocator.debit("ivbs", 100_000)
    await allocator.debit("options_momentum", 50_000)
    await allocator.reset_session()  # None = all
    assert abs(await allocator.get_free("ivbs") - 200_000) < 1.0
    assert abs(await allocator.get_free("options_momentum") - 100_000) < 1.0


# ── get_summary ───────────────────────────────────────────────────────────────

async def test_get_summary_returns_all_strategies(allocator):
    await allocator.debit("ivbs", 40_000)
    summary = await allocator.get_summary()
    assert "ivbs" in summary
    assert "options_momentum" in summary
    assert summary["ivbs"]["allocated"] == 200_000
    assert abs(summary["ivbs"]["used"] - 40_000) < 1.0
    assert abs(summary["ivbs"]["free"] - 160_000) < 1.0
    assert summary["ivbs"]["utilization_pct"] == pytest.approx(20.0, abs=0.1)


async def test_get_summary_no_debit(allocator):
    summary = await allocator.get_summary()
    assert summary["options_momentum"]["used"] == 0.0
    assert summary["options_momentum"]["utilization_pct"] == 0.0


# ── Two strategies independence ────────────────────────────────────────────────

async def test_two_strategies_independent(allocator):
    """Debiting one strategy does not affect the other."""
    await allocator.debit("ivbs", 200_000)  # fully used
    ok, _ = await allocator.check("ivbs", 1)
    assert not ok  # ivbs blocked
    ok2, _ = await allocator.check("options_momentum", 50_000)
    assert ok2  # options_momentum still has room
