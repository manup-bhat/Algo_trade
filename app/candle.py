import datetime

current_candles = {}

def update_tick(symbol, price, volume):
    now = datetime.datetime.now().replace(second=0, microsecond=0)

    if symbol not in current_candles:
        current_candles[symbol] = {
            "time": now,
            "open": price,
            "high": price,
            "low": price,
            "close": price,
            "volume": volume
        }
        return None

    candle = current_candles[symbol]

    if candle["time"] == now:
        candle["high"] = max(candle["high"], price)
        candle["low"] = min(candle["low"], price)
        candle["close"] = price
        candle["volume"] += volume
        return None
    else:
        completed = candle.copy()

        current_candles[symbol] = {
            "time": now,
            "open": price,
            "high": price,
            "low": price,
            "close": price,
            "volume": volume
        }

        return completed