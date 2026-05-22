#!/usr/bin/env python
"""Quick check of Redis data for watchlist."""
import asyncio
from app.store.redis_client import get_redis
from engine.store.redis_store import RedisStore

async def main():
    redis_client = get_redis()
    rs = RedisStore(redis_client)
    
    # Check if Redis is running
    try:
        ping = await rs.ping()
        print(f"Redis Connection: {'✓ Connected' if ping else '✗ Not connected'}")
    except Exception as e:
        print(f"Redis Error: {e}")
        return
    
    # Check live ticks
    ticks = await rs.get_all_live_ticks()
    print(f"Live ticks in Redis: {len(ticks)}")
    if ticks:
        symbols = list(ticks.keys())[:5]
        print(f"  Sample symbols with ticks: {symbols}")
    
    # Check strategy states
    states = await rs.get_all_strategy_states()
    print(f"Strategy states: {len(states) if states else 0}")
    
    # Check engine status
    status = await rs.get_engine_status()
    if status:
        print(f"Engine status: {status.get('status', 'unknown')}")
    else:
        print("Engine status: No status in Redis (engine not running)")

asyncio.run(main())
