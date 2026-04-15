import asyncio
import sys
import json
import httpx
sys.path.insert(0, ".")

from app.store.redis_client import get_redis
from engine.store.redis_store import RedisStore


async def main():
    r = get_redis()
    rs = RedisStore(r)

    status = await rs.get_engine_status()
    capital = await rs.get_capital()
    ticks = await r.keys("livetick:*")

    print(f"Engine status: {json.dumps(status)}")
    print(f"Capital: {capital}")
    print(f"Symbols with live ticks: {len(ticks)}")

    scanner_res = httpx.get("http://127.0.0.1:8000/api/v1/scanner", timeout=5)
    print(f"\nScanner endpoint: HTTP {scanner_res.status_code}")
    scanner_data = scanner_res.json()
    print(f"  hits today: {scanner_data['count']}")

    market_res = httpx.get("http://127.0.0.1:8000/api/v1/market", timeout=5)
    market_data = market_res.json()
    print(f"\nMarket endpoint: HTTP {market_res.status_code}")
    print(f"  ticks returned: {market_data['count']}")
    if market_data["ticks"]:
        t = market_data["ticks"][0]
        print(f"  sample: {t['symbol']} LTP={t['ltp']} chg={t['pct_chg']}%")

    await r.aclose()


asyncio.run(main())
