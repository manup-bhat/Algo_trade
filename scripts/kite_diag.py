import asyncio
import json
import sys

sys.path.insert(0, ".")
from app.core.config import settings
from engine.kite.auth import load_token_from_file, validate_token
from datetime import datetime
import pytz

IST = pytz.timezone("Asia/Kolkata")

data = load_token_from_file(settings.KITE_TOKEN_PATH)
if not data:
    print("ERROR: No .kite_token file")
    sys.exit(1)

gen_str = data.get("generated_at", "2000-01-01")
try:
    gen = datetime.fromisoformat(gen_str)
except Exception:
    gen = datetime.now(IST)

now = datetime.now(IST)
print(f"Token generated: {gen_str}")
print(f"Is today: {gen.date() == now.date()}")
print(f"User: {data.get('user_name')} ({data.get('user_id')})")
token = data.get("access_token", "")
print(f"Token preview: {token[:8]}...")

from kiteconnect import KiteConnect
kite = KiteConnect(api_key=settings.KITE_API_KEY)
print()
print("Testing validate_token...")
ok = validate_token(kite, token)
print(f"Token valid: {ok}")

if ok:
    print()
    print("Testing margins...")
    try:
        m = kite.margins("equity")
        print(f"Margins raw: {json.dumps(m, indent=2, default=str)}")
    except Exception as e:
        print(f"Margins error: {e}")

    print()
    print("Testing profile...")
    try:
        p = kite.profile()
        print(f"Profile: {p.get('user_name')} / {p.get('user_id')}")
    except Exception as e:
        print(f"Profile error: {e}")
