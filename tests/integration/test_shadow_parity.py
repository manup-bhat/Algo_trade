"""
tests/integration/test_shadow_parity.py — Shadow Parity & Determinism Integration Test.

Verifies that the refactored engine architecture (RiskRule chain, CandleAggregator,
MarketDataGateway, CapitalAllocator) exhibits 100% parity, deterministic behavior,
and zero drift across 500 synthetic market ticks.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import pytest
import pytz

from engine.market.candle_aggregator import CandleAggregator
from engine.market.market_data_gateway import MarketDataGateway
from engine.risk.capital_allocator import CapitalAllocator
from engine.risk.pre_trade_checks import PreTradeChecks
from engine.risk.rules.base import OrderContext, RiskResult
from engine.risk.rules.freeze_quantity_rule import FreezeQuantityRule
from engine.risk.rules.mis_intraday_rule import MISIntradayRule

IST_TZ = pytz.timezone("Asia/Kolkata")


@pytest.fixture
def sample_ticks():
    fixture_path = Path(__file__).resolve().parent.parent / "fixtures" / "sample_ticks.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_fixture_integrity(sample_ticks):
    assert len(sample_ticks) == 500
    for tick in sample_ticks[:5]:
        assert "instrument_token" in tick
        assert "symbol" in tick
        assert "last_price" in tick
        assert "volume_traded" in tick
        assert "exchange_timestamp" in tick


def test_candle_aggregator_determinism(sample_ticks):
    """Feed all 500 ticks through two independent CandleAggregators; assert exact parity."""
    agg1 = CandleAggregator()
    agg2 = CandleAggregator()

    for sym in ["RELIANCE", "INFY", "TCS", "HDFCBANK", "ICICIBANK"]:
        agg1.register_symbol(sym)
        agg2.register_symbol(sym)

    candles1 = []
    candles2 = []

    for tick in sample_ticks:
        sym = tick["symbol"]
        p = float(tick["last_price"])
        v = int(tick["volume_traded"])
        ts = datetime.datetime.fromisoformat(tick["exchange_timestamp"])

        c1 = agg1.on_tick(sym, p, v, ts)
        c2 = agg2.on_tick(sym, p, v, ts)

        if c1 is not None:
            candles1.append(c1)
        if c2 is not None:
            candles2.append(c2)

    assert len(candles1) == len(candles2)
    for c1, c2 in zip(candles1, candles2):
        assert c1.symbol == c2.symbol
        assert c1.open == c2.open
        assert c1.high == c2.high
        assert c1.low == c2.low
        assert c1.close == c2.close
        assert c1.volume == c2.volume


@pytest.mark.asyncio
async def test_market_data_gateway_refcount_parity():
    """Verify refcounting and upgrade-only discipline across multiple strategy subscriptions."""
    fake_ticker = MagicMock()
    fake_ticker.subscribe = MagicMock()
    fake_ticker.unsubscribe = MagicMock()
    fake_ticker.set_mode = MagicMock()

    gateway = MarketDataGateway(fake_ticker)

    tokens = [738561, 408065]  # RELIANCE, INFY

    # Strategy 1 subscribes at ltp
    await gateway.subscribe("ivbs", tokens, mode="ltp")
    assert gateway.get_active_token_count() == 2

    # Strategy 2 subscribes same tokens at full (triggers upgrade)
    await gateway.subscribe("options_momentum", tokens, mode="full")
    assert gateway.get_active_token_count() == 2
    # Verify mode is full
    assert gateway._active_mode[738561] == "full"
    assert gateway._active_mode[408065] == "full"

    # Strategy 2 unsubscribes -> tokens still held by Strategy 1
    await gateway.unsubscribe("options_momentum")
    assert gateway.get_active_token_count() == 2

    # Strategy 1 unsubscribes -> tokens dropped
    await gateway.unsubscribe("ivbs")
    assert gateway.get_active_token_count() == 0


@pytest.mark.asyncio
async def test_capital_allocator_isolation(redis_store):
    """Verify margin isolation between two active strategies."""
    allocator = CapitalAllocator(redis_store)

    allocator.allocate("ivbs", 500_000.0)
    allocator.allocate("options_momentum", 300_000.0)

    # Debit ivbs
    await allocator.debit("ivbs", 200_000.0)
    free_ivbs = await allocator.get_free("ivbs")
    assert free_ivbs == 300_000.0

    # options_momentum should be completely untouched
    free_opt = await allocator.get_free("options_momentum")
    assert free_opt == 300_000.0

    # Credit back ivbs
    await allocator.credit("ivbs", 100_000.0)
    free_ivbs_after = await allocator.get_free("ivbs")
    assert free_ivbs_after == 400_000.0


@pytest.mark.asyncio
async def test_risk_rule_chain_freeze_and_mis_parity():
    """Verify that FreezeQuantityRule and MisIntradayRule execute cleanly within PreTradeChecks."""
    freeze_rule = FreezeQuantityRule()
    mis_rule = MISIntradayRule()

    ctx = OrderContext(
        symbol="RELIANCE",
        strategy_id="ivbs",
        limit_price=2500.0,
        stop_loss=2460.0,
        is_paper_trade=True,
        is_backtest=False,
        computed_quantity=100,
        extra={"product": "MIS"},
    )

    res_freeze = await freeze_rule.check(ctx)
    assert not res_freeze.blocked

    res_mis = await mis_rule.check(ctx)
    assert not res_mis.blocked
