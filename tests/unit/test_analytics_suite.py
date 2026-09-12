"""
tests/unit/test_analytics_suite.py — Unit tests for rich analytics computation and export endpoints.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient, ASGITransport

from app.api.dashboard_router import _compute_rich_analytics, _rows_to_csv, _EXPORT_TABLES
from app.main import app


def test_export_tables_mapping():
    """Verify all required tables are in _EXPORT_TABLES."""
    expected = {"trades", "orders", "journal", "signals", "snapshots"}
    assert expected.issubset(set(_EXPORT_TABLES.keys()))


def test_rich_analytics_empty():
    """Verify empty trade list returns clean zeroed structure without errors."""
    d = _compute_rich_analytics([], range_code="1M", mode="ALL")
    assert d["num_trades"] == 0
    assert d["win_rate_pct"] == 0.0
    assert d["net_pnl"] == 0.0
    assert d["gross_pnl"] == 0.0
    assert d["total_charges"] == 0.0
    assert d["profit_factor"] is None
    assert d["equity_curve"] == []
    assert d["drawdown_curve"] == []
    assert d["daily_pnl"] == []
    assert len(d["day_of_week"]) == 5
    assert len(d["hourly"]) == 7


def test_rich_analytics_all_wins():
    """Verify win streaks and None profit factor on 0 losses."""
    trades = [
        {
            "id": 1, "symbol": "INFY", "strategy_id": "ivbs",
            "entry_time": "2026-09-01T09:30:00", "exit_time": "2026-09-01T10:00:00",
            "risk_amount": 500.0, "net_pnl": 1500.0, "gross_pnl": 1550.0,
            "charges": 50.0, "status": "CLOSED_TARGET", "trade_mode": "PAPER"
        },
        {
            "id": 2, "symbol": "TCS", "strategy_id": "ivbs",
            "entry_time": "2026-09-02T10:15:00", "exit_time": "2026-09-02T11:00:00",
            "risk_amount": 500.0, "net_pnl": 1000.0, "gross_pnl": 1040.0,
            "charges": 40.0, "status": "CLOSED_TARGET", "trade_mode": "PAPER"
        }
    ]
    d = _compute_rich_analytics(trades, range_code="1W", mode="PAPER")
    assert d["num_trades"] == 2
    assert d["wins"] == 2
    assert d["losses"] == 0
    assert d["win_rate_pct"] == 100.0
    assert d["profit_factor"] is None
    assert d["consecutive_wins_max"] == 2
    assert d["consecutive_losses_max"] == 0
    assert d["net_pnl"] == 2500.0
    assert d["total_charges"] == 90.0
    assert len(d["equity_curve"]) == 2
    assert d["equity_curve"][-1]["cum_net_pnl"] == 2500.0


def test_rich_analytics_drawdown_calculation():
    """Verify drawdown calculation on peak-to-trough series."""
    trades = [
        {"id": 1, "net_pnl": 1000.0, "risk_amount": 200.0, "exit_time": "2026-09-01T10:00:00"},
        {"id": 2, "net_pnl": -400.0, "risk_amount": 200.0, "exit_time": "2026-09-01T11:00:00"},
        {"id": 3, "net_pnl": -300.0, "risk_amount": 200.0, "exit_time": "2026-09-02T10:00:00"},
        {"id": 4, "net_pnl": 800.0, "risk_amount": 200.0, "exit_time": "2026-09-02T14:00:00"},
    ]
    d = _compute_rich_analytics(trades)
    # Peak is 1000. Low point is 1000 - 400 - 300 = 300. Max DD = 700.
    assert d["max_drawdown"] == 700.0
    # Max DD pct = 700 / 1000 = 70%
    assert d["max_drawdown_pct"] == 70.0
    assert d["net_pnl"] == 1100.0


def test_rich_analytics_temporal_breakdowns():
    """Verify grouping by day of week and hourly buckets."""
    trades = [
        # Monday (2026-08-31) 09:30
        {"id": 1, "entry_time": "2026-08-31T09:30:00", "exit_time": "2026-08-31T10:00:00", "net_pnl": 500.0},
        # Wednesday (2026-09-02) 14:15
        {"id": 2, "entry_time": "2026-09-02T14:15:00", "exit_time": "2026-09-02T14:45:00", "net_pnl": -200.0},
    ]
    d = _compute_rich_analytics(trades)
    dow_by_name = {x["day"]: x for x in d["day_of_week"]}
    assert dow_by_name["Monday"]["trades"] == 1
    assert dow_by_name["Monday"]["pnl"] == 500.0
    assert dow_by_name["Wednesday"]["trades"] == 1
    assert dow_by_name["Wednesday"]["pnl"] == -200.0
    assert dow_by_name["Tuesday"]["trades"] == 0

    hr_by_time = {x["hour"]: x for x in d["hourly"]}
    assert hr_by_time["09:00"]["trades"] == 1
    assert hr_by_time["14:00"]["trades"] == 1
    assert hr_by_time["10:00"]["trades"] == 0


@pytest.mark.asyncio
async def test_analytics_api_endpoint():
    """Test /api/v1/analytics endpoint across multiple range parameters."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        for rng in ["1D", "1W", "2W", "1M", "3M", "ALL"]:
            res = await ac.get(f"/api/v1/analytics?range={rng}&mode=ALL")
            assert res.status_code == 200
            data = res.json()
            assert "net_pnl" in data
            assert "win_rate_pct" in data
            assert "equity_curve" in data
            assert "daily_pnl" in data
            assert data["range"] == rng


@pytest.mark.asyncio
async def test_export_csv_endpoints():
    """Test /api/v1/export/{kind}.csv for all supported kinds and with date filters."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        for kind in ["trades", "orders", "journal", "signals", "snapshots"]:
            # Basic request
            res = await ac.get(f"/api/v1/export/{kind}.csv")
            assert res.status_code == 200
            assert "text/csv" in res.headers["content-type"]

            # Filtered request with start_date and end_date
            res_filtered = await ac.get(f"/api/v1/export/{kind}.csv?start_date=2026-09-01&end_date=2026-09-07")
            assert res_filtered.status_code == 200
            assert "text/csv" in res_filtered.headers["content-type"]
