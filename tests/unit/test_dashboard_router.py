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
