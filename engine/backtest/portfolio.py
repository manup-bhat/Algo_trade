"""
engine/backtest/portfolio.py — trade ledger + equity curve for a backtest run.

Records completed trades (with net P&L already net of costs, as produced by the
strategy's own close logic) and produces a metrics summary + equity curve.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any

from engine.backtest.metrics import compute_metrics


@dataclass(slots=True)
class BacktestTrade:
    symbol: str
    strategy_id: str
    entry_time: datetime.datetime | None
    entry_price: float
    quantity: int
    exit_time: datetime.datetime | None
    exit_price: float
    gross_pnl: float
    net_pnl: float
    status: str


class BacktestPortfolio:
    """Accumulates completed trades and computes performance metrics."""

    def __init__(self, starting_capital: float = 500000.0) -> None:
        self.starting_capital = starting_capital
        self.equity = starting_capital
        self.trades: list[BacktestTrade] = []
        self.equity_curve: list[float] = [starting_capital]

    def record_trade(self, trade: BacktestTrade) -> None:
        self.trades.append(trade)
        self.equity = round(self.equity + trade.net_pnl, 2)
        self.equity_curve.append(self.equity)

    def summary(self) -> dict[str, Any]:
        pnls = [t.net_pnl for t in self.trades]
        metrics = compute_metrics(pnls)
        metrics.update({
            "starting_capital": self.starting_capital,
            "ending_capital": self.equity,
            "return_pct": (
                round((self.equity - self.starting_capital) / self.starting_capital * 100, 3)
                if self.starting_capital else 0.0
            ),
            "equity_curve": list(self.equity_curve),
        })
        return metrics
