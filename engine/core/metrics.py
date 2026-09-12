"""
engine/core/metrics.py — Application observability metrics.

Phase 5 Implementation: Redis-backed metrics accumulator for API latencies,
tick processing times, and counter increments (errors, orders, etc).
These are exposed via GET /api/v1/dashboard/metrics for the UI or
Prometheus scraping.
"""

from __future__ import annotations

import time
import json
from typing import Any
import statistics
from collections import defaultdict

class MetricsRegistry:
    """
    Redis-backed metrics accumulator.
    """

    def __init__(self) -> None:
        self.redis = None
        self.start_time = time.time()
        # In-memory buffer for latencies to avoid hammering Redis on every tick
        self._local_latencies: dict[str, list[float]] = defaultdict(list)
        self._last_flush = time.time()

    def set_redis(self, redis_client: Any) -> None:
        self.redis = redis_client

    async def increment(self, name: str, value: int = 1) -> None:
        """Increment a counter in Redis."""
        if self.redis:
            await self.redis.hincrby("metrics:counters", name, value)

    def observe_latency(self, name: str, value_ms: float) -> None:
        """Record a latency measurement in memory, flushed periodically."""
        self._local_latencies[name].append(value_ms)

    async def flush_latencies(self) -> None:
        """Flush latencies to Redis (called periodically by runner)."""
        if not self.redis or not self._local_latencies:
            return
        
        pipe = self.redis.pipeline()
        for name, latencies in self._local_latencies.items():
            if not latencies:
                continue
            # Keep bounded in Redis (e.g., last 1000)
            key = f"metrics:latency:{name}"
            # Push new values
            for val in latencies:
                pipe.rpush(key, str(val))
            # Trim list to 1000 items
            pipe.ltrim(key, -1000, -1)
            
        await pipe.execute()
        self._local_latencies.clear()
        self._last_flush = time.time()

    async def summary(self) -> dict[str, Any]:
        """Return a snapshot of all metrics from Redis."""
        if not self.redis:
            return {}

        # Get counters
        raw_counters = await self.redis.hgetall("metrics:counters")
        counters = {
            k.decode() if isinstance(k, bytes) else k: int(v)
            for k, v in raw_counters.items()
        }

        # Get latencies
        keys = await self.redis.keys("metrics:latency:*")
        latency_summary = {}
        for key in keys:
            name = key.decode().split(":")[-1] if isinstance(key, bytes) else key.split(":")[-1]
            raw_vals = await self.redis.lrange(key, 0, -1)
            lst = [float(v) for v in raw_vals]
            if not lst:
                continue
            latency_summary[name] = {
                "avg": round(statistics.mean(lst), 2),
                "p95": round(statistics.quantiles(lst, n=20)[18], 2) if len(lst) >= 20 else round(max(lst), 2),
                "max": round(max(lst), 2),
                "count": len(lst),
            }

        return {
            "uptime_seconds": int(time.time() - self.start_time),
            "counters": counters,
            "latencies_ms": latency_summary,
        }

# Global singleton
metrics_registry = MetricsRegistry()
