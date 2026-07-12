from __future__ import annotations

import datetime
from unittest.mock import patch

import pytest
import pytz

from engine.kite.instruments import InstrumentInfo
from engine.market.candle_builder import Candle
from engine.strategy.coordinator import Coordinator

IST_TZ = pytz.timezone("Asia/Kolkata")


def _make_candle(symbol: str = "TEST") -> Candle:
    ts = datetime.datetime.now(IST_TZ).replace(second=0, microsecond=0)
    return Candle(
        symbol=symbol,
        timestamp=ts,
        open=100.0,
        high=102.0,
        low=99.5,
        close=101.0,
        volume=100000,
        turnover=101.0 * 100000,
    )


@pytest.mark.asyncio
async def test_new_entries_gate_blocks_scanner_evaluation(redis_store, mock_db):
    coord = Coordinator(redis_store, mock_db)
    universe = {
        "TEST": InstrumentInfo(
            instrument_token=123,
            symbol="TEST",
            tick_size=0.05,
            lot_size=1,
            series="EQ",
            last_price=100.0,
        )
    }
    coord.initialize_builders(universe, sma_period=500)
    coord.set_new_entries_enabled(False)

    with patch("engine.strategies.ivbs.strategy.scanner.evaluate") as mock_eval:
        await coord._on_candle_complete("TEST", _make_candle("TEST"))

    mock_eval.assert_not_called()


@pytest.mark.asyncio
async def test_new_entries_gate_enabled_allows_scanner(redis_store, mock_db):
    coord = Coordinator(redis_store, mock_db)
    universe = {
        "TEST": InstrumentInfo(
            instrument_token=123,
            symbol="TEST",
            tick_size=0.05,
            lot_size=1,
            series="EQ",
            last_price=100.0,
        )
    }
    coord.initialize_builders(universe, sma_period=500)
    coord.set_new_entries_enabled(True)

    with patch("engine.strategies.ivbs.strategy.mkt_calendar.is_market_open", return_value=True), \
         patch("engine.strategies.ivbs.strategy.scanner.evaluate", return_value=None) as mock_eval:
        await coord._on_candle_complete("TEST", _make_candle("TEST"))

    assert mock_eval.call_count == 1
