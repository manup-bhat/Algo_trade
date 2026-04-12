import os
from kiteconnect import KiteTicker
from dotenv import load_dotenv

from app.candle import update_tick
from app.store import candle_store, signals
from app.scanner import check_signal

load_dotenv()

API_KEY = os.getenv("KITE_API_KEY")
ACCESS_TOKEN = os.getenv("KITE_ACCESS_TOKEN")

kws = KiteTicker(API_KEY, ACCESS_TOKEN)

# Replace with real NSE instrument tokens
TOKENS = [738561, 5633]

def on_ticks(ws, ticks):
    for tick in ticks:
        symbol = str(tick['instrument_token'])
        price = tick['last_price']
        volume = tick['volume']

        candle = update_tick(symbol, price, volume)

        if candle:
            candle_store[symbol].append(candle)

            signal = check_signal(symbol, candle_store[symbol])

            if signal:
                print("🔥 SIGNAL:", signal)
                signals.append(signal)

def on_connect(ws, response):
    print("Connected to Kite")
    ws.subscribe(TOKENS)
    ws.set_mode(ws.MODE_FULL, TOKENS)

kws.on_ticks = on_ticks
kws.on_connect = on_connect

def start_kite():
    kws.connect(threaded=True)