import asyncio
import json
import sys

sys.path.insert(0, ".")
from app.store.redis_client import get_redis
from engine.store.redis_store import RedisStore


async def main():
    r = get_redis()
    rs = RedisStore(r)

    print("=== PING ===")
    ok = await rs.ping()
    print(f"Redis reachable: {ok}")

    print()
    print("=== ENGINE STATUS ===")
    status = await rs.get_engine_status()
    print(json.dumps(status, indent=2, default=str))

    print()
    print("=== CAPITAL ===")
    cap = await rs.get_capital()
    print(f"Capital: {cap}")

    print()
    print("=== SESSION TOKEN ===")
    tok = await rs.load_token()
    if tok:
        print(f"Token exists: user={tok.get('user_name')}, id={tok.get('user_id')}")
    else:
        print("NO TOKEN IN REDIS")

    print()
    print("=== LIVE TICKS (livetick:*) ===")
    keys = await r.keys("livetick:*")
    print(f"livetick keys: {len(keys)}")
    if keys:
        vals = await r.mget(keys[:5])
        for k, v in zip(keys[:5], vals):
            print(f"  {k}: {v}")

    print()
    print("=== LTP KEYS (ltp:*) ===")
    ltp_keys = await r.keys("ltp:*")
    print(f"ltp keys: {len(ltp_keys)}")
    if ltp_keys:
        vals = await r.mget(ltp_keys[:5])
        for k, v in zip(ltp_keys[:5], vals):
            print(f"  {k}: {v}")

    print()
    print("=== ALL REDIS KEYS ===")
    allkeys = await r.keys("*")
    print(f"Total keys: {len(allkeys)}")
    for k in sorted(str(x) for x in allkeys)[:30]:
        print(f"  {k}")

    await r.aclose()


asyncio.run(main())
