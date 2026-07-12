"""
tests/unit/test_backtest.py — backtest engine + portfolio (Phase 6).

Validates the replay engine end-to-end:
  - a minimal strategy that uses the injected SimBroker + CapturingDbWriter
  - the real OptionsMomentumStrategy replayed through the router (parity)
"""

from __future__ import annotations

import datetime
from typing import Any

import pytest
import pytz

from engine.backtest.engine import BacktestEngine
from engine.backtest.portfolio import BacktestPortfolio, BacktestTrade
from engine.core.base_strategy import BaseStrategy
from engine.market.candle_builder import Candle

IST = pytz.timezone("Asia/Kolkata")


def _c(symbol: str, h: int, m: int, o: float, high: float, low: float, c: float,
       vol: int = 1000) -> Candle:
    ts = IST.localize(datetime.datetime.combine(datetime.date.today(), datetime.time(h, m)))
    return Candle(symbol=symbol, timestamp=ts, open=o, high=high, low=low, close=c,
                  volume=vol, turnover=c * vol)


def _ts(h: int, m: int) -> datetime.datetime:
    return IST.localize(datetime.datetime.combine(datetime.date.today(), datetime.time(h, m)))


# ── Portfolio ─────────────────────────────────────────────────────────────────

class TestPortfolio:
    def test_records_trades_and_equity(self):
        p = BacktestPortfolio(100000.0)
        p.record_trade(BacktestTrade("A", "s", None, 100, 10, None, 110, 100, 100, "CLOSED_TARGET"))
        p.record_trade(BacktestTrade("B", "s", None, 50, 10, None, 45, -50, -50, "CLOSED_STOPLOSS"))
        s = p.summary()
        assert s["num_trades"] == 2
        assert s["net_pnl"] == 50
        assert s["ending_capital"] == 100050.0
        assert s["equity_curve"] == [100000.0, 100100.0, 100050.0]


# ── Minimal strategy that exercises the SimBroker + CapturingDbWriter ─────────

class _BuyExitStrategy(BaseStrategy):
    def __init__(self, *a: Any, **k: Any) -> None:
        super().__init__(*a, **k)
        self._pos: dict[str, Any] | None = None
        self._n = 0
        self._trade_id: int | None = None

    async def on_market_open(self) -> None:
        self._pos = None
        self._n = 0

    async def on_candle(self, symbol, candle, builder, instrument_token) -> None:
        self._n += 1
        if self._n == 2 and self._pos is None:
            entry = candle.close
            order_id = await self._order_service.place_entry(symbol, entry, 10, sm=None)
            self._trade_id = await self._db.open_trade(
                signal_id=None, symbol=symbol, instrument_token=instrument_token,
                entry_order_id=order_id, entry_time=candle.timestamp, entry_price=entry,
                quantity=10, initial_stop_loss=entry * 0.98, risk_per_share=entry * 0.02,
                risk_amount=entry * 0.2, target_1r2=entry * 1.02, target_1r3=entry * 1.02,
                target_1r4=entry * 1.02, sl_order_id=None, trade_mode="PAPER",
                strategy_id=self.strategy_id,
            )
            self._pos = {"symbol": symbol, "entry": entry, "qty": 10, "target": entry * 1.02}

    async def on_tick(self, symbol, ltp, exchange_ts) -> None:
        if self._pos and symbol == self._pos["symbol"] and ltp >= self._pos["target"]:
            gross = (ltp - self._pos["entry"]) * self._pos["qty"]
            await self._db.close_trade(
                trade_id=self._trade_id, exit_price=ltp, exit_time=exchange_ts,
                exit_order_id=None, gross_pnl=gross, net_pnl=gross, brokerage=0.0,
                stt=0.0, other_charges=0.0, status="CLOSED_TARGET",
            )
            self._pos = None

    async def on_order_postback(self, message) -> None:
        return None

    async def on_squareoff(self) -> None:
        self._pos = None

    def is_symbol_active(self, symbol) -> bool:
        return self._pos is not None and self._pos["symbol"] == symbol

    def get_stats(self) -> dict[str, Any]:
        return {"candles": self._n}


class TestBacktestEngineMinimalStrategy:
    @pytest.mark.asyncio
    async def test_engine_runs_strategy_and_records_trade(self):
        eng = BacktestEngine(lambda r, d: [_BuyExitStrategy("buyexit", r, d)], starting_capital=100000.0)
        await eng.set_capital(100000.0)
        candles = [
            _c("ACME", 10, 0, 100, 100.5, 99.5, 100),   # candle 1 (no entry)
            _c("ACME", 10, 1, 100, 103.0, 99.0, 100),   # candle 2 → entry @100, intrabar high 103 ≥ target 102 → exit
            _c("ACME", 10, 2, 103, 104.0, 102.0, 103),
        ]
        report = await eng.run(candles)
        assert report["num_trades"] == 1
        assert report["net_pnl"] == pytest.approx(30.0)   # (103-100)*10
        assert report["win_rate"] == 1.0
        assert report["ending_capital"] == pytest.approx(100030.0)


# ── Real OptionsMomentumStrategy replayed through the engine ──────────────────

def _nfo_dump() -> list[dict]:
    exp = (datetime.date.today() + datetime.timedelta(days=7)).isoformat()
    rows: list[dict] = []
    tok = 1000
    for strike in (23900, 24000, 24100):
        for it in ("CE", "PE"):
            tok += 1
            rows.append({
                "instrument_token": tok, "tradingsymbol": f"NIFTY{strike}{it}",
                "name": "NIFTY", "last_price": 0.0, "expiry": exp, "strike": strike,
                "tick_size": 0.05, "lot_size": 75, "instrument_type": it,
                "segment": "NFO-OPT", "exchange": "NFO",
            })
    return rows


class TestBacktestEngineOptionsStrategy:
    @pytest.mark.asyncio
    async def test_options_strategy_backtest_produces_trade(self):
        from engine.strategies.options_momentum.strategy import OptionsMomentumStrategy

        eng = BacktestEngine(
            lambda r, d: [OptionsMomentumStrategy("options_momentum", r, d)],
            starting_capital=500000.0,
        )
        strat = eng.router.get("options_momentum")
        strat.load_option_chain(_nfo_dump())
        await eng.set_capital(500000.0)
        await eng.market_open()

        for i in range(5):
            await eng.feed_candle(_c("NIFTY 50", 10, i, 24000, 24010, 23990, 24000))
        await eng.set_ltp("NIFTY24000CE", 120.0)
        await eng.feed_candle(_c("NIFTY 50", 10, 5, 24005, 24030, 24000, 24025))

        assert "NIFTY24000CE" in strat._positions
        pos = strat._positions["NIFTY24000CE"]
        await eng.feed_tick("NIFTY24000CE", pos.target, _ts(10, 10))

        report = eng.summary()
        assert report["num_trades"] == 1
        assert report["net_pnl"] > 0
        assert report["win_rate"] == 1.0
