"""
tests/unit/test_options_momentum.py — Options Momentum strategy paper lifecycle (Phase 4).

Proves the plugin architecture supports a different asset class end-to-end in paper
mode: load chain → N-bar breakout on the underlying → buy ATM CE → manage to target.
"""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest
import pytz

from app.models.db.trade import TradeStatus
from engine.market.candle_builder import Candle
from engine.store.redis_store import RedisStore
from engine.strategies.options_momentum.strategy import OptionsMomentumStrategy

IST = pytz.timezone("Asia/Kolkata")


def _expiry_str() -> str:
    return (datetime.date.today() + datetime.timedelta(days=7)).isoformat()


def _nfo_dump() -> list[dict]:
    exp = _expiry_str()
    rows: list[dict] = []
    tok = 1000
    for strike in (23900, 24000, 24100):
        for it in ("CE", "PE"):
            tok += 1
            rows.append({
                "instrument_token": tok,
                "tradingsymbol": f"NIFTY{strike}{it}",
                "name": "NIFTY",
                "last_price": 0.0,
                "expiry": exp,
                "strike": strike,
                "tick_size": 0.05,
                "lot_size": 75,
                "instrument_type": it,
                "segment": "NFO-OPT",
                "exchange": "NFO",
            })
    return rows


def _c(h: int, m: int, o: float, high: float, low: float, c: float) -> Candle:
    ts = IST.localize(datetime.datetime.combine(datetime.date.today(), datetime.time(h, m)))
    return Candle(symbol="NIFTY 50", timestamp=ts, open=o, high=high, low=low, close=c,
                  volume=1000, turnover=c * 1000)


def _ts(h: int, m: int) -> datetime.datetime:
    return IST.localize(datetime.datetime.combine(datetime.date.today(), datetime.time(h, m)))


@pytest.fixture
def redis_store():
    return RedisStore(fakeredis.aioredis.FakeRedis(decode_responses=True))


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.open_trade.return_value = 7
    db.close_trade.return_value = None
    return db


@pytest.fixture
def strat(redis_store, mock_db):
    return OptionsMomentumStrategy("options_momentum", redis_store, mock_db)


async def _feed_warmup(strat):
    # 5 flat candles build the breakout window without triggering a signal.
    for i in range(5):
        await strat.on_candle("NIFTY 50", _c(10, i, 24000, 24010, 23990, 24000), None, 0)


class TestOptionsMomentum:
    def test_config_is_loaded(self, strat):
        assert strat.config.get("id") == "options_momentum"
        assert strat.underlying == "NIFTY"
        assert strat.lookback == 5

    @pytest.mark.asyncio
    async def test_full_paper_cycle_ce_to_target(self, strat, redis_store, mock_db):
        await redis_store.set_capital(500000.0)
        strat.load_option_chain(_nfo_dump())
        await strat.on_market_open()
        await _feed_warmup(strat)
        assert not strat._positions

        # ATM CE premium available before the breakout candle
        await redis_store.set_last_ltp("NIFTY24000CE", 120.0)

        # Breakout up: close 24025 > prior high 24010, green candle → buy ATM CE
        await strat.on_candle("NIFTY 50", _c(10, 5, 24005, 24030, 24000, 24025), None, 0)

        assert "NIFTY24000CE" in strat._positions
        pos = strat._positions["NIFTY24000CE"]
        assert pos.quantity == 75  # 1 lot
        assert pos.option_type.value == "CE"
        assert mock_db.open_trade.await_count == 1
        assert strat.is_symbol_active("NIFTY24000CE")

        # Tick to target → position closes as CLOSED_TARGET
        await strat.on_tick("NIFTY24000CE", pos.target, _ts(10, 10))
        assert "NIFTY24000CE" not in strat._positions
        assert mock_db.close_trade.await_count == 1
        assert mock_db.close_trade.await_args.kwargs["status"] == TradeStatus.CLOSED_TARGET

    @pytest.mark.asyncio
    async def test_stop_loss_exit(self, strat, redis_store, mock_db):
        await redis_store.set_capital(500000.0)
        strat.load_option_chain(_nfo_dump())
        await strat.on_market_open()
        await _feed_warmup(strat)
        await redis_store.set_last_ltp("NIFTY24000CE", 120.0)
        await strat.on_candle("NIFTY 50", _c(10, 5, 24005, 24030, 24000, 24025), None, 0)
        pos = strat._positions["NIFTY24000CE"]
        await strat.on_tick("NIFTY24000CE", pos.stop_loss, _ts(10, 10))
        assert "NIFTY24000CE" not in strat._positions
        assert mock_db.close_trade.await_args.kwargs["status"] == TradeStatus.CLOSED_STOPLOSS

    @pytest.mark.asyncio
    async def test_no_entry_without_breakout(self, strat, redis_store):
        await redis_store.set_capital(500000.0)
        strat.load_option_chain(_nfo_dump())
        await strat.on_market_open()
        await redis_store.set_last_ltp("NIFTY24000CE", 120.0)
        # 6 flat candles — never breaks the window
        for i in range(6):
            await strat.on_candle("NIFTY 50", _c(10, i, 24000, 24010, 23990, 24000), None, 0)
        assert not strat._positions

    @pytest.mark.asyncio
    async def test_no_entry_after_cutoff(self, strat, redis_store):
        await redis_store.set_capital(500000.0)
        strat.load_option_chain(_nfo_dump())
        await strat.on_market_open()
        await _feed_warmup(strat)
        await redis_store.set_last_ltp("NIFTY24000CE", 120.0)
        # Breakout candle after the 14:30 cutoff
        await strat.on_candle("NIFTY 50", _c(15, 0, 24005, 24030, 24000, 24025), None, 0)
        assert not strat._positions

    @pytest.mark.asyncio
    async def test_squareoff_closes_open_position(self, strat, redis_store, mock_db):
        await redis_store.set_capital(500000.0)
        strat.load_option_chain(_nfo_dump())
        await strat.on_market_open()
        await _feed_warmup(strat)
        await redis_store.set_last_ltp("NIFTY24000CE", 120.0)
        await strat.on_candle("NIFTY 50", _c(10, 5, 24005, 24030, 24000, 24025), None, 0)
        assert strat._positions
        await strat.on_squareoff()
        assert not strat._positions
        assert mock_db.close_trade.await_args.kwargs["status"] == TradeStatus.CLOSED_TIME

    def test_get_stats_shape(self, strat):
        stats = strat.get_stats()
        assert stats["asset_class"] == "OPTION"
        assert stats["underlying"] == "NIFTY"
        assert "open_positions" in stats
