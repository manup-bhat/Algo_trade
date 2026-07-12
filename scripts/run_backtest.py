"""
scripts/run_backtest.py — run the REAL IVBS strategy over historical 1-min candles
and print the measured performance (win rate / profit factor / expectancy / max DD).

This turns the spec's win-rate *hypothesis* into a *measurement*.

Run from the repo root:
    .\.venv\Scripts\python.exe scripts\run_backtest.py data\RELIANCE.csv --symbol RELIANCE
    .\.venv\Scripts\python.exe scripts\run_backtest.py data\RELIANCE.csv --warmup data\RELIANCE_prevday.csv

CSV columns (header, case-insensitive): timestamp,open,high,low,close,volume[,symbol]
  timestamp: 'YYYY-MM-DD HH:MM' or ISO-8601 (naive is treated as IST).

The --warmup CSV (optional) pre-loads the 500-period volume SMA from the prior
session(s) so the scanner is warmed on the first bars of the test file.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Ensure the repo root is importable when run as `python scripts/run_backtest.py`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> None:
    parser = argparse.ArgumentParser(description="IVBS historical backtest (CSV → metrics)")
    parser.add_argument("csv", help="Path to the 1-minute candle CSV")
    parser.add_argument("--symbol", default=None, help="Override symbol (else CSV column / 'SYM')")
    parser.add_argument("--capital", type=float, default=500_000.0, help="Starting capital (INR)")
    parser.add_argument("--warmup", default=None, help="Optional CSV whose volumes pre-warm the SMA")
    parser.add_argument("--token", type=int, default=0, help="Instrument token (optional)")
    args = parser.parse_args()

    from engine.backtest.data_loader import load_candles_csv, run_ivbs_backtest

    candles = load_candles_csv(args.csv, symbol=args.symbol)
    if not candles:
        print(f"No candles loaded from {args.csv}", file=sys.stderr)
        sys.exit(1)

    warmup = None
    if args.warmup:
        warmup = [c.volume for c in load_candles_csv(args.warmup, symbol=args.symbol)]

    summary = asyncio.run(
        run_ivbs_backtest(
            candles,
            warmup_volumes=warmup,
            starting_capital=args.capital,
            token=args.token,
        )
    )
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
