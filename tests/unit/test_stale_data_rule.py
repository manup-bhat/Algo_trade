import asyncio
import datetime
import json
import pytest
from unittest.mock import MagicMock
from engine.risk.rules.stale_data_rule import StaleDataRule
from engine.risk.rules.base import OrderContext

@pytest.mark.asyncio
async def test_stale_data_rule_passes_fresh():
    rule = StaleDataRule()
    
    mock_redis = MagicMock()
    # 5 seconds ago
    fresh_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=5)
    tick = {"last_trade_time": fresh_time.isoformat()}
    
    # We must mock the async _r.hget
    async def mock_hget(name, key):
        return json.dumps(tick)
    
    mock_redis._r.hget = mock_hget
    
    ctx = OrderContext(
        symbol="RELIANCE", strategy_id="test", limit_price=100.0, stop_loss=90.0,
        redis_store=mock_redis, kite=None, candle_builder=None, 
        is_paper_trade=True, is_backtest=False, extra={}
    )
    
    result = await rule.check(ctx)
    assert not result.blocked
    assert result.reason == ""

@pytest.mark.asyncio
async def test_stale_data_rule_blocks_stale():
    rule = StaleDataRule()
    
    mock_redis = MagicMock()
    # 2 minutes ago
    stale_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=2)
    tick = {"last_trade_time": stale_time.isoformat()}
    
    async def mock_hget(name, key):
        return json.dumps(tick)
    
    mock_redis._r.hget = mock_hget
    
    ctx = OrderContext(
        symbol="RELIANCE", strategy_id="test", limit_price=100.0, stop_loss=90.0,
        redis_store=mock_redis, kite=None, candle_builder=None, 
        is_paper_trade=True, is_backtest=False, extra={}
    )
    
    result = await rule.check(ctx)
    assert result.blocked
    assert "stale_data" in result.reason
