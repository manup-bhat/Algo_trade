"""
tests/conftest.py — Shared fixtures: FakeRedis, mock KiteConnect, test DB.
"""

from __future__ import annotations

import asyncio
import datetime
import os

import fakeredis.aioredis
import pytest
import pytz

# Use test .env so we don't need real credentials
os.environ.setdefault("KITE_API_KEY", "test_key")
os.environ.setdefault("KITE_API_SECRET", "test_secret")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

IST_TZ = pytz.timezone("Asia/Kolkata")


@pytest.fixture
def ist_tz():
    return IST_TZ


def make_ist(hour: int, minute: int, second: int = 0) -> datetime.datetime:
    """Helper: create a timezone-aware IST datetime for today."""
    now = datetime.datetime.now(IST_TZ)
    return now.replace(hour=hour, minute=minute, second=second, microsecond=0)


@pytest.fixture
def ist_timestamp():
    """Factory fixture: returns make_ist() helper function."""
    return make_ist


@pytest.fixture
async def fake_redis():
    """In-memory Redis for tests — no real Redis required."""
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield redis
    await redis.aclose()


@pytest.fixture
def mock_kite(mocker):
    """Mock KiteConnect instance with common methods stubbed."""
    mock = mocker.MagicMock()
    mock.profile.return_value = {"user_id": "TEST123", "user_name": "Test User"}
    mock.margins.return_value = {
        "equity": {"net": 500000.0, "available": {"live_balance": 500000.0}}
    }
    mock.instruments.return_value = []
    return mock
