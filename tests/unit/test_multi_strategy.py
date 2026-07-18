"""
tests/unit/test_multi_strategy.py — Unit and database integration tests for multi-strategy features.
"""

from __future__ import annotations

import datetime
from pathlib import Path
import pytest
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException

from app.api import dashboard_router
from app.models.db.daily_pnl import DailyPnl
from app.store.database import init_db, get_db


# ── Strategies metadata & configs GET/POST ──────────────────────────────────

@pytest.fixture
def mock_strategy_config_dir(tmp_path):
    """
    Creates a temporary strategy config directory and config.yaml files
    to prevent mutating the project's actual strategy config files during testing.
    """
    ivbs_dir = tmp_path / "ivbs"
    ivbs_dir.mkdir()
    ivbs_yaml = ivbs_dir / "config.yaml"
    ivbs_yaml.write_text("""
id: ivbs
name: Institutional Volume Breakout Strategy
description: Test description
asset_class: EQUITY
enabled: true
scanner:
  volume_spike_multiple: 15.0
  volume_sma_period: 500
""", encoding="utf-8")

    opt_dir = tmp_path / "options_momentum"
    opt_dir.mkdir()
    opt_yaml = opt_dir / "config.yaml"
    opt_yaml.write_text("""
id: options_momentum
name: Index Options Momentum
description: Options description
asset_class: OPTION
enabled: false
signal:
  lookback_candles: 5
""", encoding="utf-8")

    # Monkeypatch the config loading path in dashboard_router to point to our temp folder
    def mock_path(strategy_id: str) -> Path:
        return tmp_path / strategy_id / "config.yaml"

    return mock_path


@pytest.mark.asyncio
async def test_get_strategies_enriched_metadata(redis_store, mock_strategy_config_dir, monkeypatch):
    dashboard_router.set_dependencies(redis_store, None)
    monkeypatch.setattr(dashboard_router, "_strategy_config_path", mock_strategy_config_dir)
    
    # Overwrite the resolver directory lookup inside _load_all_strategy_configs
    # pointing to our temporary base path instead of the production path
    def mock_load_configs():
        configs = []
        import yaml
        for name in ["ivbs", "options_momentum"]:
            p = mock_strategy_config_dir(name)
            if p.is_file():
                raw = yaml.safe_load(p.read_text(encoding="utf-8"))
                configs.append({
                    "strategy_id": name,
                    "name": raw.get("name", name),
                    "description": raw.get("description", ""),
                    "asset_class": raw.get("asset_class", "EQUITY"),
                    "enabled": bool(raw.get("enabled", True)),
                    "config": raw,
                })
        return configs
        
    monkeypatch.setattr(dashboard_router, "_load_all_strategy_configs", mock_load_configs)

    data = await dashboard_router.get_strategies()
    assert data["count"] == 2
    
    ivbs = next(s for s in data["strategies"] if s["strategy_id"] == "ivbs")
    assert ivbs["name"] == "Institutional Volume Breakout Strategy"
    assert ivbs["asset_class"] == "EQUITY"
    assert ivbs["enabled"] is True

    opt = next(s for s in data["strategies"] if s["strategy_id"] == "options_momentum")
    assert opt["name"] == "Index Options Momentum"
    assert opt["asset_class"] == "OPTION"
    assert opt["enabled"] is False


@pytest.mark.asyncio
async def test_get_strategy_config_details(redis_store, mock_strategy_config_dir, monkeypatch):
    dashboard_router.set_dependencies(redis_store, None)
    monkeypatch.setattr(dashboard_router, "_strategy_config_path", mock_strategy_config_dir)

    # Success case
    data = await dashboard_router.get_strategy_config("ivbs")
    assert data["strategy_id"] == "ivbs"
    assert data["asset_class"] == "EQUITY"
    assert data["config"]["scanner"]["volume_spike_multiple"] == 15.0
    
    # Flattened schema check
    spike_field = next(f for f in data["schema"] if f["key"] == "scanner.volume_spike_multiple")
    assert spike_field["value"] == 15.0
    assert spike_field["kind"] == "float"

    # Nonexistent strategy ID error case (404)
    with pytest.raises(HTTPException) as exc:
        await dashboard_router.get_strategy_config("nonexistent")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_update_strategy_config_writes_and_reinitializes(redis_store, mock_strategy_config_dir, monkeypatch):
    dashboard_router.set_dependencies(redis_store, None)
    monkeypatch.setattr(dashboard_router, "_strategy_config_path", mock_strategy_config_dir)

    payload = dashboard_router.StrategyConfigUpdate(
        updates={
            "scanner.volume_spike_multiple": 18.5,
            "scanner.volume_sma_period": 600,
            "enabled": False,
        },
        reload_engine=True
    )

    resp = await dashboard_router.update_strategy_config("ivbs", payload)
    assert resp["status"] == "success"
    assert "scanner.volume_spike_multiple" in resp["applied"]
    assert "scanner.volume_sma_period" in resp["applied"]
    assert "enabled" in resp["applied"]

    # Verify changes were written to file
    import yaml
    written_yaml = yaml.safe_load(mock_strategy_config_dir("ivbs").read_text(encoding="utf-8"))
    assert written_yaml["scanner"]["volume_spike_multiple"] == 18.5
    assert written_yaml["scanner"]["volume_sma_period"] == 600
    assert written_yaml["enabled"] is False

    # Verify Redis reinitialization trigger was set
    trigger = await redis_store.consume_reinit_trigger()
    assert trigger is True


# ── Settings & CSV export strategy filters ──────────────────────────────────

@pytest.mark.asyncio
async def test_settings_includes_strategy_configs(redis_store, mock_strategy_config_dir, monkeypatch):
    dashboard_router.set_dependencies(redis_store, None)
    monkeypatch.setattr(dashboard_router, "_strategy_config_path", mock_strategy_config_dir)
    
    def mock_load_configs():
        import yaml
        return [{
            "strategy_id": "ivbs",
            "name": "IVBS",
            "enabled": True,
            "config": yaml.safe_load(mock_strategy_config_dir("ivbs").read_text(encoding="utf-8")),
        }]
    monkeypatch.setattr(dashboard_router, "_load_all_strategy_configs", mock_load_configs)

    data = await dashboard_router.get_settings()
    assert "strategy_configs" in data
    assert len(data["strategy_configs"]) == 1
    assert data["strategy_configs"][0]["strategy_id"] == "ivbs"
    assert len(data["strategy_configs"][0]["schema"]) > 0


@pytest.mark.asyncio
async def test_export_csv_with_strategy_filter(redis_store):
    dashboard_router.set_dependencies(redis_store, None)
    
    # Verify export filename incorporates strategy name when requested
    resp_all = await dashboard_router.export_csv("trades", strategy_id=None)
    assert "trading_trades" in resp_all.headers["content-disposition"]
    
    resp_ivbs = await dashboard_router.export_csv("trades", strategy_id="ivbs")
    assert "trading_ivbs_trades" in resp_ivbs.headers["content-disposition"]


# ── Database composite unique constraint ─────────────────────────────────────

@pytest.mark.asyncio
async def test_daily_pnl_composite_unique_constraint():
    # Initialize in-memory SQLite tables
    await init_db()

    # Clear any old data
    async with get_db() as session:
        # Success: Insert different strategy rows for the same calendar date
        row1 = DailyPnl(
            trade_date=datetime.date(2026, 7, 18),
            total_capital=100000.0,
            signals_fired=5,
            setups_abandoned=3,
            trades_taken=2,
            winning_trades=1,
            losing_trades=1,
            breakeven_trades=0,
            gross_pnl=500.0,
            total_charges=50.0,
            net_pnl=450.0,
            strategy_id="ivbs"
        )
        row2 = DailyPnl(
            trade_date=datetime.date(2026, 7, 18),
            total_capital=200000.0,
            signals_fired=10,
            setups_abandoned=6,
            trades_taken=4,
            winning_trades=2,
            losing_trades=2,
            breakeven_trades=0,
            gross_pnl=1200.0,
            total_charges=120.0,
            net_pnl=1080.0,
            strategy_id="options_momentum"
        )
        session.add(row1)
        session.add(row2)
        # Should persist cleanly without violation
        await session.flush()

    # IntegrityError: Insert a duplicate row for the same date AND strategy
    with pytest.raises(IntegrityError):
        async with get_db() as session:
            row3 = DailyPnl(
                trade_date=datetime.date(2026, 7, 18),
                total_capital=150000.0,
                signals_fired=3,
                setups_abandoned=1,
                trades_taken=2,
                winning_trades=1,
                losing_trades=1,
                breakeven_trades=0,
                gross_pnl=100.0,
                total_charges=10.0,
                net_pnl=90.0,
                strategy_id="ivbs"  # Duplicate of row1 strategy on same date
            )
            session.add(row3)
            await session.flush()
