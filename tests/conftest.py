"""
tests/conftest.py — Shared fixtures for IVBS engine tests.

Phase 4: all tests run in PAPER_TRADE=true mode.
The settings lru_cache is cleared and reset to paper mode for every test
via the autouse `paper_trade_mode` fixture.
"""

from __future__ import annotations

import datetime
import os
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest
import pytz

# ── Set env BEFORE any engine imports so lru_cache picks it up correctly ──────
os.environ["PAPER_TRADE"] = "true"
os.environ.setdefault("KITE_API_KEY", "test_key")
os.environ.setdefault("KITE_API_SECRET", "test_secret")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

IST_TZ = pytz.timezone("Asia/Kolkata")

# ── pytest-asyncio: auto mode for all async tests ────────────────────────────
# (works with pytest-asyncio ≥ 0.21; configured in pyproject.toml)


# ── Core autouse: force paper_trade=True on every test ───────────────────────

@pytest.fixture(autouse=True)
def paper_trade_mode(monkeypatch):
    """
    Ensure settings.is_paper_trade is True for every test.
    Patches both the field and the lru_cache'd property.
    """
    from app.core.config import get_settings, settings
    monkeypatch.setattr(settings, "PAPER_TRADE", True)
    yield


@pytest.fixture(autouse=True)
def reset_circuit_breaker():
    """Reset circuit_breaker in-memory flag before each test."""
    from engine.risk.circuit_breaker import circuit_breaker as _cb
    _cb._tripped = False
    yield
    _cb._tripped = False


# ── Time helpers ──────────────────────────────────────────────────────────────

def make_ist(hour: int, minute: int, second: int = 0) -> datetime.datetime:
    """Create timezone-aware IST datetime for today."""
    now = datetime.datetime.now(IST_TZ)
    return now.replace(hour=hour, minute=minute, second=second, microsecond=0)


@pytest.fixture
def ist_tz():
    return IST_TZ


@pytest.fixture
def ist_timestamp():
    """Factory fixture: returns make_ist() helper."""
    return make_ist


# ── Redis fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
async def fake_redis():
    """In-memory Redis — no real Redis needed."""
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield redis
    await redis.aclose()


@pytest.fixture
async def redis_store(fake_redis):
    """RedisStore backed by FakeRedis."""
    from engine.store.redis_store import RedisStore
    store = RedisStore(fake_redis)
    # Default baseline state for all tests
    await store.set_capital(500_000.0)
    await store.set_daily_pnl(0.0)
    await store.set_circuit_breaker(False)
    await store.set_blocked_margin(0.0)
    return store


# ── Kite client mock ──────────────────────────────────────────────────────────

@pytest.fixture
def mock_kite():
    """
    AsyncMock(spec=AsyncKiteClient) — type-safe mock.
    Raises AttributeError on any method not present on the real class.
    """
    from engine.kite.client import AsyncKiteClient
    mock = AsyncMock(spec=AsyncKiteClient)

    mock.profile.return_value = {"user_id": "TEST123", "user_name": "Test User"}
    mock.margins.return_value = {
        "equity": {"net": 500_000.0, "available": {"live_balance": 500_000.0}}
    }
    mock.get_net_equity.return_value = 500_000.0
    mock.get_available_balance.return_value = 500_000.0
    mock.order_margins.return_value = [{"initial": {"total": 10_000.0}}]
    mock.positions.return_value = {"day": [], "net": []}
    mock.orders.return_value = []
    mock.trades.return_value = []
    mock.instruments.return_value = []
    mock.place_order.return_value = "ORDER_TEST_001"
    mock.modify_order.return_value = "ORDER_TEST_001"
    mock.cancel_order.return_value = "ORDER_TEST_001"
    return mock


# ── DB writer mock ────────────────────────────────────────────────────────────

@pytest.fixture
def mock_db():
    """AsyncMock DbWriter — all write methods stubbed."""
    db = AsyncMock()
    db.write_signal = AsyncMock(return_value=1)
    db.open_trade = AsyncMock(return_value=1)
    db.close_trade = AsyncMock()
    db.update_signal_progression = AsyncMock()
    db.write_order_event = AsyncMock()
    db.write_daily_pnl = AsyncMock()
    return db
