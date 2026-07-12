"""
engine/backtest/metrics.py — performance metrics from a trade P&L series.

Pure functions, no I/O. Inputs are per-trade net P&L (₹). All metrics are computed
from realized trades; drawdown uses the cumulative-P&L equity path.
"""

from __future__ import annotations

import statistics
from typing import Any


def _max_drawdown(pnls: list[float]) -> float:
    """Max peak-to-trough drop of the cumulative-P&L curve (₹, >= 0)."""
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pnls:
        equity += p
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return round(max_dd, 2)


def _sharpe(series: list[float]) -> float:
    """Sharpe-like ratio: mean / population-stdev of the per-trade series.

    Not annualized — a unitless quality ratio of the trade distribution.
    """
    if len(series) < 2:
        return 0.0
    mean = statistics.mean(series)
    sd = statistics.pstdev(series)
    if sd == 0:
        return 0.0
    return round(mean / sd, 3)


def _empty() -> dict[str, Any]:
    return {
        "num_trades": 0,
        "wins": 0,
        "losses": 0,
        "breakeven": 0,
        "win_rate": 0.0,
        "gross_profit": 0.0,
        "gross_loss": 0.0,
        "net_pnl": 0.0,
        "profit_factor": None,
        "avg_win": 0.0,
        "avg_loss": 0.0,
        "expectancy": 0.0,
        "largest_win": 0.0,
        "largest_loss": 0.0,
        "max_drawdown": 0.0,
        "sharpe": 0.0,
    }


def compute_metrics(pnls: list[float]) -> dict[str, Any]:
    """Compute performance metrics from a list of per-trade net P&L values."""
    n = len(pnls)
    if n == 0:
        return _empty()

    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    breakeven = [p for p in pnls if p == 0]

    gross_profit = round(sum(wins), 2)
    gross_loss = round(-sum(losses), 2)  # positive magnitude
    net_pnl = round(sum(pnls), 2)

    if gross_loss > 0:
        profit_factor: float | None = round(gross_profit / gross_loss, 3)
    elif gross_profit > 0:
        profit_factor = None  # undefined: no losing trades
    else:
        profit_factor = 0.0

    return {
        "num_trades": n,
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": len(breakeven),
        "win_rate": round(len(wins) / n, 4),
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "net_pnl": net_pnl,
        "profit_factor": profit_factor,
        "avg_win": round(statistics.mean(wins), 2) if wins else 0.0,
        "avg_loss": round(statistics.mean(losses), 2) if losses else 0.0,
        "expectancy": round(net_pnl / n, 2),
        "largest_win": round(max(pnls), 2),
        "largest_loss": round(min(pnls), 2),
        "max_drawdown": _max_drawdown(pnls),
        "sharpe": _sharpe(pnls),
    }
