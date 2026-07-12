"""Tests for the historical backtest data loader + real IVBS replay."""

from __future__ import annotations

import datetime

import pytest
import pytz

from engine.market.candle_builder import Candle
from engine.backtest.data_loader import load_candles_csv, run_ivbs_backtest

IST = pytz.timezone("Asia/Kolkata")


def _candle(minute: int, o: float, h: float, l: float, c: float, vol: int) -> Candle:
    ts = datetime.datetime.now(IST).replace(hour=10, minute=minute, second=0, microsecond=0)
    return Candle(
        symbol="TESTX", timestamp=ts, open=o, high=h, low=l, close=c,
        volume=vol, turnover=round(c * vol, 2),
    )


# ── CSV loader ────────────────────────────────────────────────────────────────

def test_load_candles_csv(tmp_path):
    path = tmp_path / "c.csv"
    path.write_text(
        "timestamp,open,high,low,close,volume\n"
        "2024-01-02 10:00,100,101,99,100.5,5000\n"
        "2024-01-02 10:01,100.5,102,100,101,6000\n",
        encoding="utf-8",
    )
    candles = load_candles_csv(path, symbol="ACME")
    assert len(candles) == 2
    assert candles[0].symbol == "ACME"
    assert candles[0].open == 100 and candles[0].close == 100.5
    assert candles[0].turnover == round(100.5 * 5000, 2)
    assert candles[1].volume == 6000
    # naive timestamps localized to IST
    assert candles[0].timestamp.tzinfo is not None


def test_load_candles_csv_missing_columns(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("timestamp,open,close\n2024-01-02 10:00,100,101\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing required columns"):
        load_candles_csv(path)


# ── Real IVBS replay through the backtest engine ───────────────────────────────

@pytest.mark.asyncio
async def test_run_ivbs_backtest_produces_a_trade(monkeypatch):
    # Make scanning independent of the real trading calendar (mirror test_coordinator).
    from engine.strategies.ivbs import strategy as ivbs_strategy

    monkeypatch.setattr(ivbs_strategy.mkt_calendar, "is_market_open", lambda *a, **k: True)

    # scan → dry-up → dry-up → re-ignition → run-up to 1:4 target
    candles = [
        _candle(0, 200.0, 201.0, 196.0, 200.5, 500_000),   # impact (spike ≫15x, turnover ≫8Cr)
        _candle(1, 200.5, 200.8, 200.0, 200.3, 5_000),     # dry-up 1
        _candle(2, 200.3, 200.6, 200.0, 200.4, 4_000),     # dry-up 2
        _candle(3, 200.4, 204.0, 200.3, 203.0, 60_000),    # re-ignition (break > 201, green)
        _candle(4, 203.0, 232.0, 203.0, 231.0, 30_000),    # run-up → hits 1:4 target intrabar
        _candle(5, 231.0, 231.0, 230.0, 231.0, 1_000),     # flush
    ]
    warmup = [1000] * 500  # SMA = 1000 → impact spike ≈ 500x

    summary = await run_ivbs_backtest(candles, warmup_volumes=warmup, token=111)

    assert summary["num_trades"] == 1
    assert summary["net_pnl"] > 0
    assert summary["wins"] == 1
    # BACKTEST_MODE must be restored to its default (False) after the run
    from app.core.config import settings
    assert settings.BACKTEST_MODE is False
