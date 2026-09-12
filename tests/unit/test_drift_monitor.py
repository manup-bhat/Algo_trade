import pytest
from engine.analytics.drift_monitor import DriftMonitor

class MockAnalyticsService:
    def __init__(self, stats):
        self.stats = stats
        
    async def get_win_rate(self, strategy_id: str, lookback_days: int = 30):
        return self.stats

@pytest.mark.asyncio
async def test_drift_monitor_no_trades():
    analytics = MockAnalyticsService({"total_trades": 5, "win_rate_pct": 50.0})
    monitor = DriftMonitor(analytics)
    
    result = await monitor.check_drift("ivbs", baseline_win_rate=50.0)
    assert result["status"] == "ok"
    assert result["reason"] == "not_enough_trades"

@pytest.mark.asyncio
async def test_drift_monitor_ok():
    analytics = MockAnalyticsService({"total_trades": 20, "win_rate_pct": 45.0})
    monitor = DriftMonitor(analytics)
    
    result = await monitor.check_drift("ivbs", baseline_win_rate=50.0)
    assert result["status"] == "ok"
    assert result["win_rate"] == 45.0
    assert result["threshold"] == 40.0

@pytest.mark.asyncio
async def test_drift_monitor_drifted():
    analytics = MockAnalyticsService({"total_trades": 20, "win_rate_pct": 35.0})
    monitor = DriftMonitor(analytics)
    
    result = await monitor.check_drift("ivbs", baseline_win_rate=50.0)
    assert result["status"] == "drifted"
    assert result["reason"] == "win_rate_below_baseline"
    assert result["win_rate"] == 35.0
    assert result["threshold"] == 40.0

@pytest.mark.asyncio
async def test_drift_monitor_min_win_rate():
    analytics = MockAnalyticsService({"total_trades": 20, "win_rate_pct": 45.0})
    monitor = DriftMonitor(analytics)
    
    result = await monitor.check_drift("ivbs", baseline_win_rate=50.0, min_win_rate=48.0)
    assert result["status"] == "drifted"
    assert result["win_rate"] == 45.0
    assert result["threshold"] == 48.0
