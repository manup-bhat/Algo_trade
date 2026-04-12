def check_signal(symbol, candles):
    if len(candles) < 20:  # keep small for testing
        return None

    last = candles[-1]

    turnover = last["close"] * last["volume"]

    avg_volume = sum(c["volume"] for c in candles) / len(candles)

    if turnover >= 8_00_00_000 and last["volume"] > avg_volume * 5:
        return {
            "symbol": symbol,
            "price": last["close"],
            "turnover": turnover,
            "type": "HIGH_ACTIVITY"
        }

    return None