"""
engine/analytics/analytics_service.py — CQRS read side: per-strategy analytics.

Provides all dashboard metric queries in one place, replacing inline SQL
scattered across dashboard_router.py.  All methods accept strategy_id=None
to return an unfiltered account-wide aggregate.

Design (CQRS read-side):
  - All queries are read-only SELECT statements.
  - Returns plain dicts / lists (JSON-serializable) — no ORM objects.
  - Async: uses SQLAlchemy async engine (same as the rest of app).
  - No business logic — pure data retrieval and aggregation.

Usage (from dashboard_router.py):
    daily = await analytics_service.get_daily_pnl(strategy_id="ivbs")
    rate  = await analytics_service.get_win_rate(strategy_id=None, lookback_days=30)
    blotter = await analytics_service.get_order_blotter(strategy_id="ivbs", limit=50)
"""

from __future__ import annotations

import datetime
from typing import Any

import structlog
from sqlalchemy import select, text, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)


class AnalyticsService:
    """
    CQRS read side for the trading engine.

    All methods:
      - Return JSON-serializable dicts/lists (no SQLAlchemy model objects).
      - Accept strategy_id=None for account-wide queries.
      - Catch exceptions internally and return empty results (never raise to
        dashboard routers — a broken analytics query should never bring down
        the dashboard).
    """

    def __init__(self, session_factory: Any) -> None:
        """
        Args:
            session_factory: Callable that returns an AsyncSession context manager.
                             Typically `app.store.database.get_async_session`.
        """
        self._session_factory = session_factory

    # ── Daily P&L ─────────────────────────────────────────────────────────────

    async def get_daily_pnl(
        self,
        strategy_id: str | None = None,
        date: datetime.date | None = None,
        lookback_days: int = 30,
    ) -> list[dict[str, Any]]:
        """
        Return daily P&L rows sorted by trade_date DESC.

        Args:
            strategy_id:  Filter by strategy. None = all strategies.
            date:         If provided, return only this specific date.
            lookback_days: Number of days to look back (ignored if date provided).

        Returns:
            List of dicts with keys matching the daily_pnl table columns.
        """
        try:
            async with self._session_factory() as session:
                session: AsyncSession
                q = text("""
                    SELECT
                        strategy_id, trade_date, total_capital,
                        signals_fired, trades_taken, winning_trades,
                        losing_trades, breakeven_trades, setups_abandoned,
                        gross_pnl, total_charges, net_pnl, max_drawdown
                    FROM daily_pnl
                    WHERE 1=1
                      AND (:strategy_id IS NULL OR strategy_id = :strategy_id)
                      AND (:date IS NULL OR trade_date = :date)
                      AND (:date IS NOT NULL OR trade_date >= date('now', :offset))
                    ORDER BY trade_date DESC
                    LIMIT 500
                """)
                result = await session.execute(q, {
                    "strategy_id": strategy_id,
                    "date": str(date) if date else None,
                    "offset": f"-{lookback_days} days",
                })
                rows = result.fetchall()
                return [dict(r._mapping) for r in rows]
        except Exception as exc:
            log.error("analytics_get_daily_pnl_failed", error=str(exc))
            return []

    # ── Win Rate ──────────────────────────────────────────────────────────────

    async def get_win_rate(
        self,
        strategy_id: str | None = None,
        lookback_days: int = 30,
    ) -> dict[str, Any]:
        """
        Return win rate stats over the last *lookback_days*.

        Returns:
            Dict with keys: total_trades, winning_trades, losing_trades,
            win_rate_pct, avg_win_pnl, avg_loss_pnl, profit_factor.
        """
        try:
            async with self._session_factory() as session:
                q = text("""
                    SELECT
                        SUM(trades_taken)   AS total_trades,
                        SUM(winning_trades) AS winning_trades,
                        SUM(losing_trades)  AS losing_trades,
                        SUM(gross_pnl)      AS gross_pnl,
                        SUM(net_pnl)        AS net_pnl
                    FROM daily_pnl
                    WHERE 1=1
                      AND (:strategy_id IS NULL OR strategy_id = :strategy_id)
                      AND trade_date >= date('now', :offset)
                """)
                result = await session.execute(q, {
                    "strategy_id": strategy_id,
                    "offset": f"-{lookback_days} days",
                })
                row = result.fetchone()
                if not row:
                    return {}
                m = dict(row._mapping)
                total = m.get("total_trades") or 0
                wins  = m.get("winning_trades") or 0
                losses = m.get("losing_trades") or 0
                return {
                    "total_trades": total,
                    "winning_trades": wins,
                    "losing_trades": losses,
                    "win_rate_pct": round(wins / total * 100, 1) if total else 0.0,
                    "gross_pnl": round(m.get("gross_pnl") or 0, 2),
                    "net_pnl": round(m.get("net_pnl") or 0, 2),
                    "lookback_days": lookback_days,
                    "strategy_id": strategy_id,
                }
        except Exception as exc:
            log.error("analytics_get_win_rate_failed", error=str(exc))
            return {}

    # ── Drawdown ──────────────────────────────────────────────────────────────

    async def get_drawdown(
        self,
        strategy_id: str | None = None,
        lookback_days: int = 30,
    ) -> dict[str, Any]:
        """
        Return max drawdown and equity curve summary.

        Returns:
            Dict with: max_drawdown_pct, max_drawdown_inr, worst_day, best_day.
        """
        try:
            async with self._session_factory() as session:
                q = text("""
                    SELECT
                        MIN(net_pnl)       AS max_drawdown_inr,
                        trade_date         AS worst_day,
                        MAX(net_pnl)       AS best_day_pnl
                    FROM daily_pnl
                    WHERE 1=1
                      AND (:strategy_id IS NULL OR strategy_id = :strategy_id)
                      AND trade_date >= date('now', :offset)
                """)
                result = await session.execute(q, {
                    "strategy_id": strategy_id,
                    "offset": f"-{lookback_days} days",
                })
                row = result.fetchone()
                if not row:
                    return {}
                m = dict(row._mapping)
                return {
                    "max_drawdown_inr": round(m.get("max_drawdown_inr") or 0, 2),
                    "best_day_pnl": round(m.get("best_day_pnl") or 0, 2),
                    "strategy_id": strategy_id,
                    "lookback_days": lookback_days,
                }
        except Exception as exc:
            log.error("analytics_get_drawdown_failed", error=str(exc))
            return {}

    # ── Open Positions ────────────────────────────────────────────────────────

    async def get_open_positions(
        self,
        strategy_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Return currently open positions from the trades table (state = MANAGING).

        Args:
            strategy_id: Filter by strategy. None = all strategies.

        Returns:
            List of position dicts: symbol, strategy_id, entry_price, quantity, etc.
        """
        try:
            async with self._session_factory() as session:
                q = text("""
                    SELECT
                        t.symbol, t.strategy_id, t.entry_price,
                        t.quantity, t.stop_loss, t.target,
                        t.entry_time, t.trade_mode
                    FROM trades t
                    WHERE t.exit_time IS NULL
                      AND (:strategy_id IS NULL OR t.strategy_id = :strategy_id)
                    ORDER BY t.entry_time DESC
                """)
                result = await session.execute(q, {"strategy_id": strategy_id})
                rows = result.fetchall()
                return [dict(r._mapping) for r in rows]
        except Exception as exc:
            log.error("analytics_get_open_positions_failed", error=str(exc))
            return []

    # ── Order Blotter ─────────────────────────────────────────────────────────

    async def get_order_blotter(
        self,
        strategy_id: str | None = None,
        limit: int = 100,
        order_group_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Return recent order events for the blotter.

        Args:
            strategy_id:    Filter by strategy. None = all.
            limit:          Max rows to return (capped at 500).
            order_group_id: Filter by order group (multi-leg orders).

        Returns:
            List of order event dicts sorted by timestamp DESC.
        """
        limit = min(limit, 500)
        try:
            async with self._session_factory() as session:
                q = text("""
                    SELECT
                        oe.id, oe.order_id, oe.symbol, oe.strategy_id,
                        oe.order_type, oe.transaction_type, oe.status,
                        oe.price, oe.quantity, oe.filled_quantity,
                        oe.average_price, oe.tag, oe.order_group_id,
                        oe.timestamp
                    FROM order_events oe
                    WHERE 1=1
                      AND (:strategy_id IS NULL OR oe.strategy_id = :strategy_id)
                      AND (:group_id IS NULL OR oe.order_group_id = :group_id)
                    ORDER BY oe.timestamp DESC
                    LIMIT :limit
                """)
                result = await session.execute(q, {
                    "strategy_id": strategy_id,
                    "group_id": order_group_id,
                    "limit": limit,
                })
                rows = result.fetchall()
                return [dict(r._mapping) for r in rows]
        except Exception as exc:
            log.error("analytics_get_order_blotter_failed", error=str(exc))
            return []

    # ── Slippage Summary ──────────────────────────────────────────────────────

    async def get_slippage_summary(
        self,
        strategy_id: str | None = None,
        lookback_days: int = 30,
    ) -> dict[str, Any]:
        """
        Return average entry slippage (limit price vs average fill price).

        Returns:
            Dict with: avg_slippage_pct, median_slippage_pct, worst_slippage_pct.
        """
        try:
            async with self._session_factory() as session:
                q = text("""
                    SELECT
                        AVG((t.entry_price - t.average_fill_price) / t.entry_price * 100)
                            AS avg_slippage_pct,
                        MIN((t.entry_price - t.average_fill_price) / t.entry_price * 100)
                            AS worst_slippage_pct
                    FROM trades t
                    WHERE t.average_fill_price > 0
                      AND t.entry_time >= date('now', :offset)
                      AND (:strategy_id IS NULL OR t.strategy_id = :strategy_id)
                """)
                result = await session.execute(q, {
                    "strategy_id": strategy_id,
                    "offset": f"-{lookback_days} days",
                })
                row = result.fetchone()
                if not row:
                    return {}
                m = dict(row._mapping)
                return {
                    "avg_slippage_pct": round(m.get("avg_slippage_pct") or 0, 3),
                    "worst_slippage_pct": round(m.get("worst_slippage_pct") or 0, 3),
                    "strategy_id": strategy_id,
                    "lookback_days": lookback_days,
                }
        except Exception as exc:
            log.error("analytics_get_slippage_failed", error=str(exc))
            return {}
