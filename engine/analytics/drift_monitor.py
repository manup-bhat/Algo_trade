"""
engine/analytics/drift_monitor.py
Monitors live strategy performance against backtest baselines.
"""

from typing import Any
import structlog
from engine.analytics.analytics_service import AnalyticsService

log = structlog.get_logger(__name__)

class DriftMonitor:
    """
    Monitors live strategy performance against backtest baselines.
    Compares live win-rate / slippage against expected thresholds.
    """
    
    def __init__(self, analytics: AnalyticsService):
        self.analytics = analytics

    async def check_drift(
        self, 
        strategy_id: str, 
        baseline_win_rate: float | None = None, 
        min_win_rate: float | None = None,
        lookback_days: int = 30
    ) -> dict[str, Any]:
        """
        Check if the strategy has drifted from its baseline.
        If min_win_rate is provided, uses that as the absolute floor.
        If baseline_win_rate is provided without min_win_rate, uses baseline - 10% as floor.
        """
        stats = await self.analytics.get_win_rate(strategy_id, lookback_days=lookback_days)
        
        # We need at least 10 trades to make a statistically significant drift check
        total_trades = stats.get("total_trades", 0)
        
        if not baseline_win_rate and not min_win_rate:
            return {
                "status": "ok", 
                "reason": "no_baseline_configured",
                "win_rate": stats.get("win_rate_pct"),
                "total_trades": total_trades
            }
            
        if total_trades < 10:
            return {
                "status": "ok", 
                "reason": "not_enough_trades", 
                "win_rate": stats.get("win_rate_pct"), 
                "total_trades": total_trades,
                "min_win_rate_required": min_win_rate or (baseline_win_rate - 10.0)
            }
            
        win_rate = stats.get("win_rate_pct", 0.0)
        
        threshold = min_win_rate if min_win_rate is not None else (baseline_win_rate - 10.0)
        
        if win_rate < threshold:
            log.warning(
                "strategy_drift_detected",
                strategy_id=strategy_id,
                win_rate=win_rate,
                threshold=threshold,
                total_trades=total_trades
            )
            return {
                "status": "drifted", 
                "reason": "win_rate_below_baseline",
                "win_rate": win_rate,
                "threshold": threshold,
                "total_trades": total_trades
            }
            
        return {
            "status": "ok", 
            "win_rate": win_rate, 
            "threshold": threshold,
            "total_trades": total_trades
        }
