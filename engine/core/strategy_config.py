"""
engine/core/strategy_config.py — per-strategy YAML config loader.

Each strategy owns `engine/strategies/<strategy_id>/config.yaml`. This loader reads
that file into a plain dict. It is deliberately dependency-light and fail-soft:
a missing file, missing PyYAML, or a parse error all return {} so the strategy can
fall back to its own defaults (or, for IVBS today, to app.core.config settings).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger(__name__)

# engine/core/strategy_config.py → parents[1] == engine/
_STRATEGIES_DIR = Path(__file__).resolve().parents[1] / "strategies"


def strategy_config_path(strategy_id: str) -> Path:
    """Absolute path to a strategy's config.yaml (may not exist)."""
    return _STRATEGIES_DIR / strategy_id / "config.yaml"


def load_strategy_config(strategy_id: str) -> dict[str, Any]:
    """Load engine/strategies/<strategy_id>/config.yaml. Returns {} on any failure."""
    path = strategy_config_path(strategy_id)
    if not path.is_file():
        return {}
    try:
        import yaml  # optional dependency, imported lazily
    except ImportError:
        log.warning("pyyaml_missing_strategy_config_skipped", strategy_id=strategy_id)
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except Exception as exc:  # malformed YAML / IO error
        log.warning("strategy_config_load_failed", strategy_id=strategy_id, error=str(exc))
        return {}
    if data is None:
        return {}
    if not isinstance(data, dict):
        log.warning("strategy_config_not_a_mapping", strategy_id=strategy_id, path=str(path))
        return {}
    return data
