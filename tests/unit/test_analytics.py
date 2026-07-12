"""Tests for the dashboard strategy-analytics aggregation helper."""

from __future__ import annotations

import pytest

from app.api.dashboard_router import _compute_trade_analytics, _rows_to_csv


def test_empty_rows():
    d = _compute_trade_analytics([])
    assert d["num_trades"] == 0
    assert d["win_rate_pct"] == 0.0
    assert d["net_pnl"] == 0.0
    assert d["avg_r_multiple"] == 0.0
    assert d["trades_by_mode"] == {}


def test_mixed_trades_metrics():
    rows = [
        {"net_pnl": 200.0, "risk_amount": 50.0, "trade_mode": "PAPER", "charges": 10.0},
        {"net_pnl": -50.0, "risk_amount": 50.0, "trade_mode": "PAPER", "charges": 8.0},
        {"net_pnl": 100.0, "risk_amount": 25.0, "trade_mode": "LIVE", "charges": 9.0},
    ]
    d = _compute_trade_analytics(rows)
    assert d["num_trades"] == 3
    assert d["wins"] == 2
    assert d["losses"] == 1
    assert d["net_pnl"] == 250.0
    assert d["win_rate_pct"] == round(2 / 3 * 100, 1)
    assert d["total_charges"] == 27.0
    assert d["trades_by_mode"] == {"PAPER": 2, "LIVE": 1}
    # profit_factor = 300 / 50 = 6.0
    assert d["profit_factor"] == 6.0
    # R-multiples: 200/50=4, -50/50=-1, 100/25=4 → mean = 7/3
    assert d["avg_r_multiple"] == round((4 + -1 + 4) / 3, 3)


def test_all_wins_profit_factor_none():
    rows = [
        {"net_pnl": 100.0, "risk_amount": 20.0, "trade_mode": "PAPER", "charges": 5.0},
        {"net_pnl": 60.0, "risk_amount": 20.0, "trade_mode": "PAPER", "charges": 5.0},
    ]
    d = _compute_trade_analytics(rows)
    assert d["losses"] == 0
    assert d["profit_factor"] is None  # undefined with no losing trades


def test_handles_missing_risk_amount():
    rows = [
        {"net_pnl": 100.0, "risk_amount": None, "trade_mode": "PAPER", "charges": 0.0},
        {"net_pnl": -20.0, "risk_amount": 0.0, "trade_mode": "PAPER", "charges": 0.0},
    ]
    d = _compute_trade_analytics(rows)
    # No usable risk_amount → avg_r_multiple defaults to 0.0 (no crash)
    assert d["avg_r_multiple"] == 0.0
    assert d["num_trades"] == 2


# ── CSV export serializer ──────────────────────────────────────
def test_rows_to_csv_header_and_rows():
    rows = [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]
    out = _rows_to_csv(rows).strip().splitlines()
    assert out[0] == "a,b"
    assert out[1] == "1,x"
    assert out[2] == "2,y"


def test_rows_to_csv_empty_is_blank():
    assert _rows_to_csv([]) == ""


# ── Active-strategies publish/read round-trip ─────────────────────────
@pytest.mark.asyncio
async def test_active_strategies_roundtrip(redis_store):
    assert await redis_store.get_active_strategies() == []
    await redis_store.set_active_strategies(["ivbs", "options_momentum"])
    assert await redis_store.get_active_strategies() == ["ivbs", "options_momentum"]
