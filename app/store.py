from collections import defaultdict, deque

# last 500 candles per stock
candle_store = defaultdict(lambda: deque(maxlen=500))

# latest signals
signals = []