"""
app/store/redis_client.py — Async Redis connection pool.

All Redis access should go through engine/store/redis_store.py.
This module provides the raw client for dependency injection.
"""

from __future__ import annotations

import redis.asyncio as aioredis

from app.core.config import settings

# Module-level connection pool — created once, shared across all coroutines
_pool: aioredis.ConnectionPool | None = None


def get_pool() -> aioredis.ConnectionPool:
    """Return (and lazily create) the global Redis connection pool."""
    global _pool
    if _pool is None:
        _pool = aioredis.ConnectionPool.from_url(
            settings.REDIS_URL,
            max_connections=20,
            decode_responses=True,
        )
    return _pool


def get_redis() -> aioredis.Redis:
    """Return a Redis client using the shared connection pool."""
    return aioredis.Redis(connection_pool=get_pool())


async def close_pool() -> None:
    """Gracefully close the connection pool (call on app shutdown)."""
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None
