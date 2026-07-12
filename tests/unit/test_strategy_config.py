"""
tests/unit/test_strategy_config.py — per-strategy config loader + strategy_id schema.

Covers Phase 3 (multi-strategy data model):
  - engine.core.strategy_config.load_strategy_config
  - IVBSStrategy exposes its loaded config
  - strategy_id columns exist on all event tables + strategies table registered
"""

from __future__ import annotations

# Import models so they register with Base.metadata before introspection.
import app.models.db.daily_pnl  # noqa: F401
import app.models.db.order_event  # noqa: F401
import app.models.db.signal  # noqa: F401
import app.models.db.strategy  # noqa: F401
import app.models.db.trade  # noqa: F401
from app.models.db.base import Base
from engine.core.strategy_config import load_strategy_config, strategy_config_path


class TestStrategyConfigLoader:
    def test_loads_ivbs_config(self):
        cfg = load_strategy_config("ivbs")
        assert isinstance(cfg, dict) and cfg, "IVBS config should be a non-empty dict"
        assert cfg["id"] == "ivbs"
        assert cfg["asset_class"] == "EQUITY"
        # Nested sections present
        assert cfg["scanner"]["volume_spike_multiple"] == 15.0
        assert cfg["timing"]["dryup_max_minutes"] == 25  # Updated: 20→25 per NSE mid-cap research

    def test_missing_config_returns_empty_dict(self):
        assert load_strategy_config("does_not_exist_xyz") == {}

    def test_config_path_points_into_strategy_package(self):
        p = strategy_config_path("ivbs")
        assert p.name == "config.yaml"
        assert p.parent.name == "ivbs"

    def test_ivbs_strategy_instance_has_config(self):
        from engine.strategies.ivbs.strategy import IVBSStrategy

        strat = IVBSStrategy("ivbs", None, None)  # type: ignore[arg-type]
        assert strat.config.get("id") == "ivbs"


class TestStrategyIdSchema:
    def test_strategy_id_column_on_event_tables(self):
        md = Base.metadata
        for table_name in ("signals", "trades", "order_events", "daily_pnl"):
            assert table_name in md.tables, f"{table_name} not registered"
            assert "strategy_id" in md.tables[table_name].columns, (
                f"{table_name} missing strategy_id column"
            )

    def test_strategies_table_registered(self):
        assert "strategies" in Base.metadata.tables
        cols = Base.metadata.tables["strategies"].columns
        for expected in ("id", "name", "asset_class", "enabled", "config"):
            assert expected in cols, f"strategies missing {expected}"
