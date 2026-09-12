from __future__ import annotations

import pytest

from app.api import dashboard_router


@pytest.mark.asyncio
async def test_emergency_stop_sets_emergency_command(redis_store):
    dashboard_router.set_dependencies(redis_store, None)

    resp = await dashboard_router.emergency_stop()
    control = await redis_store.get_engine_control()

    assert control == "EMERGENCY_STOP"
    assert resp["status"] == "EMERGENCY_STOP"


@pytest.mark.asyncio
async def test_stop_sets_graceful_stop_command(redis_store):
    dashboard_router.set_dependencies(redis_store, None)

    resp = await dashboard_router.stop_engine()
    control = await redis_store.get_engine_control()

    assert control == "STOP"
    assert resp["status"] == "STOP"


@pytest.mark.asyncio
async def test_positions_reads_nested_state_and_position(redis_store):
    dashboard_router.set_dependencies(redis_store, None)

    await redis_store.set_strategy_state(
        "TEST",
        {
            "symbol": "TEST",
            "state": "MANAGING",
            "position": {
                "entry_price": 100.0,
                "quantity": 10,
                "current_sl": 95.0,
                "target_1r2": 110.0,
                "target_1r4": 120.0,
                "cost_trailed": False,
                "profit_locked": False,
            },
        },
    )
    await redis_store.set_position(
        "TEST",
        {
            "entry_price": 100.0,
            "quantity": 10,
            "current_sl": 95.0,
            "target_1r2": 110.0,
            "target_1r4": 120.0,
            "unrealized_pnl": 55.0,
        },
    )

    data = await dashboard_router.get_positions()

    assert data["count"] == 1
    pos = data["positions"][0]
    assert pos["symbol"] == "TEST"
    assert pos["entry_price"] == 100.0
    assert pos["quantity"] == 10
    assert pos["unrealized_pnl"] == 55.0


@pytest.mark.asyncio
async def test_radar_reads_current_state_shape(redis_store):
    dashboard_router.set_dependencies(redis_store, None)

    await redis_store.set_strategy_state(
        "ABC",
        {
            "symbol": "ABC",
            "state": "MONITORING",
            "impact_candle_time": "2026-04-15T09:31:00+05:30",
            "impact_close": 502.5,
            "spike_multiple": 24.2,
            "consolidation": {
                "high": 510.0,
                "candle_count": 3,
            },
        },
    )
    await redis_store.set_last_ltp("ABC", 508.2)

    radar = await dashboard_router._get_radar_data()

    assert len(radar) == 1
    row = radar[0]
    assert row["symbol"] == "ABC"
    assert row["state"] == "MONITORING"
    assert row["impact_close"] == 502.5
    assert row["spike_multiple"] == 24.2
    assert row["breakout_level"] == 510.0
    assert row["current_price"] == 508.2


@pytest.mark.asyncio
async def test_market_uses_eod_snapshot_when_market_closed(redis_store, monkeypatch):
    dashboard_router.set_dependencies(redis_store, None)

    await redis_store.set_live_tick("ABC", ltp=508.2, day_open=500.0, volume=123456)
    await redis_store.persist_eod_market_snapshot()
    await redis_store._r.delete("livetick:ABC")

    monkeypatch.setattr(dashboard_router, "_is_market_open_now", lambda: False)

    data = await dashboard_router.get_market()

    assert data["source"] == "eod_snapshot"
    assert data["count"] == 1
    assert data["ticks"][0]["symbol"] == "ABC"


@pytest.mark.asyncio
async def test_market_uses_live_ticks_when_market_open(redis_store, monkeypatch):
    dashboard_router.set_dependencies(redis_store, None)

    await redis_store.set_live_tick("XYZ", ltp=100.5, day_open=99.0, volume=7890)
    monkeypatch.setattr(dashboard_router, "_is_market_open_now", lambda: True)

    data = await dashboard_router.get_market()

    assert data["source"] == "live_ticks"
    assert data["count"] == 1
    assert data["ticks"][0]["symbol"] == "XYZ"


# ── strategy selector / filter ────────────────────────────────────────────────
def test_norm_strategy_filter():
    assert dashboard_router._norm_strategy(None) is None
    assert dashboard_router._norm_strategy("") is None
    assert dashboard_router._norm_strategy("all") is None
    assert dashboard_router._norm_strategy("ALL") is None
    assert dashboard_router._norm_strategy(" IVBS ") == "ivbs"
    assert dashboard_router._norm_strategy("options_momentum") == "options_momentum"


@pytest.mark.asyncio
async def test_get_strategies_falls_back_to_ivbs(redis_store):
    dashboard_router.set_dependencies(redis_store, None)
    data = await dashboard_router.get_strategies()
    # strategies is now a list of enriched dicts (strategy_id, name, asset_class, ...)
    strategy_ids = [
        s["strategy_id"] if isinstance(s, dict) else s
        for s in data["strategies"]
    ]
    assert "ivbs" in strategy_ids
    assert data["count"] >= 1


@pytest.mark.asyncio
async def test_get_strategies_reads_published_ids(redis_store):
    dashboard_router.set_dependencies(redis_store, None)
    await redis_store.set_active_strategies(["ivbs", "options_momentum"])
    data = await dashboard_router.get_strategies()
    # active_ids echoes what was published to Redis
    assert set(data["active_ids"]) == {"ivbs", "options_momentum"}
    # strategies list contains enriched dicts from disk
    strategy_ids = [
        s["strategy_id"] if isinstance(s, dict) else s
        for s in data["strategies"]
    ]
    assert "ivbs" in strategy_ids
    assert data["count"] >= 1


# ── CSV export ────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_export_csv_unknown_kind_raises_404(redis_store):
    from fastapi import HTTPException
    dashboard_router.set_dependencies(redis_store, None)
    with pytest.raises(HTTPException) as exc:
        await dashboard_router.export_csv("bogus")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_export_csv_trades_returns_csv_stream(redis_store):
    dashboard_router.set_dependencies(redis_store, None)
    resp = await dashboard_router.export_csv("trades")
    assert resp.media_type == "text/csv"
    assert "attachment" in resp.headers["content-disposition"]
    assert resp.headers["content-disposition"].endswith('.csv"')


@pytest.mark.asyncio
async def test_positions_filtered_by_strategy_id(redis_store):
    dashboard_router.set_dependencies(redis_store, None)

    await redis_store.set_strategy_state(
        "INFY",
        {
            "symbol": "INFY",
            "strategy_id": "ivbs",
            "state": "MANAGING",
            "position": {"entry_price": 1500.0, "quantity": 10},
        },
    )
    await redis_store.set_strategy_state(
        "NIFTY23SEP21000CE",
        {
            "symbol": "NIFTY23SEP21000CE",
            "strategy_id": "options_momentum",
            "state": "MANAGING",
            "position": {"entry_price": 120.0, "quantity": 50},
        },
    )

    # Filter for ivbs only
    res_ivbs = await dashboard_router.get_positions(strategy_id="ivbs")
    assert res_ivbs["count"] == 1
    assert res_ivbs["positions"][0]["symbol"] == "INFY"

    # Filter for options_momentum
    res_opt = await dashboard_router.get_positions(strategy_id="options_momentum")
    assert res_opt["count"] == 1
    assert res_opt["positions"][0]["symbol"] == "NIFTY23SEP21000CE"

    # Unfiltered (None) returns both
    res_all = await dashboard_router.get_positions()
    assert res_all["count"] == 2


@pytest.mark.asyncio
async def test_analytics_daily_pnl_and_win_rate_endpoints():
    res_pnl = await dashboard_router.get_analytics_daily_pnl(strategy_id="ivbs")
    assert "daily_pnl" in res_pnl
    assert isinstance(res_pnl["daily_pnl"], list)

    res_win = await dashboard_router.get_analytics_win_rate(strategy_id="ivbs")
    assert isinstance(res_win, dict)

