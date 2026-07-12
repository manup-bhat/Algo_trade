"""
engine/backtest/data_loader.py — load historical 1-min candles and replay them
through the REAL IVBS strategy via the backtest engine.

This turns the win-rate *hypothesis* (spec §1.5) into a *measurement*: feed a
historical NSE 1-minute series and get back win rate / profit factor / expectancy
/ max drawdown from the actual strategy code (same StrategyRouter + IVBSStrategy
that runs live), with a deterministic SimBroker.

CSV format (header, case-insensitive): timestamp,open,high,low,close,volume[,symbol]
  timestamp: 'YYYY-MM-DD HH:MM' / ISO-8601 (naive is localized to IST).

Usage (offline):
    from engine.backtest.data_loader import load_candles_csv, run_ivbs_backtest
    candles = load_candles_csv("data/RELIANCE_2024-01-02.csv", symbol="RELIANCE")
    summary = asyncio.run(run_ivbs_backtest(candles, warmup_volumes=prev_day_volumes))
    print(summary)   # num_trades, win_rate, profit_factor, expectancy, max_drawdown, ...
"""

from __future__ import annotations

import csv
import datetime
from pathlib import Path
from typing import Any

import pytz

from engine.market.candle_builder import Candle

IST = pytz.timezone("Asia/Kolkata")

_TS_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M")
_REQUIRED_COLS = ("timestamp", "open", "high", "low", "close", "volume")


def _parse_ts(raw: str) -> datetime.datetime:
    raw = raw.strip()
    dt: datetime.datetime | None = None
    try:
        dt = datetime.datetime.fromisoformat(raw)
    except ValueError:
        for fmt in _TS_FORMATS:
            try:
                dt = datetime.datetime.strptime(raw, fmt)
                break
            except ValueError:
                continue
    if dt is None:
        raise ValueError(f"Unrecognized timestamp: {raw!r}")
    if dt.tzinfo is None:
        dt = IST.localize(dt)
    return dt.replace(second=0, microsecond=0)


def load_candles_csv(path: str | Path, symbol: str | None = None) -> list[Candle]:
    """Load 1-minute candles from a CSV file into Candle objects (turnover derived)."""
    rows_out: list[Candle] = []
    with open(Path(path), newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        cols = {c.lower().strip(): c for c in (reader.fieldnames or [])}
        missing = [c for c in _REQUIRED_COLS if c not in cols]
        if missing:
            raise ValueError(f"CSV missing required columns: {missing}")
        for row in reader:
            sym = symbol or (row.get(cols["symbol"]) if "symbol" in cols else None) or "SYM"
            close = float(row[cols["close"]])
            volume = int(float(row[cols["volume"]]))
            rows_out.append(
                Candle(
                    symbol=str(sym),
                    timestamp=_parse_ts(row[cols["timestamp"]]),
                    open=float(row[cols["open"]]),
                    high=float(row[cols["high"]]),
                    low=float(row[cols["low"]]),
                    close=close,
                    volume=volume,
                    turnover=round(close * volume, 2),
                )
            )
    return rows_out


async def run_ivbs_backtest(
    candles: list[Candle],
    warmup_volumes: list[int] | None = None,
    starting_capital: float = 500_000.0,
    token: int = 0,
) -> dict[str, Any]:
    """Replay ``candles`` through the real IVBSStrategy and return the portfolio summary.

    Enables ``settings.BACKTEST_MODE`` for the duration so the pre-trade wall-clock
    market-open/entry-cutoff gates are bypassed (the candle-time entry cutoff is
    still enforced inside ``on_candle``). Restores the flag afterwards.
    """
    from app.core.config import settings
    from engine.backtest.engine import BacktestEngine
    from engine.strategies.ivbs.strategy import IVBSStrategy

    def build(redis: Any, db: Any) -> list[Any]:
        return [IVBSStrategy("ivbs", redis, db)]

    prev_backtest = settings.BACKTEST_MODE
    settings.BACKTEST_MODE = True
    try:
        bt = BacktestEngine(build, starting_capital=starting_capital)
        await bt.set_capital(starting_capital)
        return await bt.run(candles, warmup_volumes=warmup_volumes, token=token)
    finally:
        settings.BACKTEST_MODE = prev_backtest


async def fetch_candles_kite(
    kite: Any,
    instrument_token: int,
    from_date: Any,
    to_date: Any,
    symbol: str = "SYM",
    interval: str = "minute",
) -> list[Candle]:
    """Fetch historical candles from Kite (AsyncKiteClient) into Candle objects.

    LIVE-ONLY: needs an authenticated Kite session. Kite caps minute-interval
    requests at ~60 days, so chunk longer ranges. kite.historical_data(...) yields
    dicts with date/open/high/low/close/volume keys.
    """
    raw = await kite.historical_data(instrument_token, from_date, to_date, interval)
    out: list[Candle] = []
    for r in raw or []:
        ts = r["date"]
        if isinstance(ts, str):
            ts = _parse_ts(ts)
        elif getattr(ts, "tzinfo", None) is None:
            ts = IST.localize(ts)
        close = float(r["close"])
        vol = int(r["volume"])
        out.append(
            Candle(
                symbol=symbol,
                timestamp=ts.replace(second=0, microsecond=0),
                open=float(r["open"]),
                high=float(r["high"]),
                low=float(r["low"]),
                close=close,
                volume=vol,
                turnover=round(close * vol, 2),
            )
        )
    return out
