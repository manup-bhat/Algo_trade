"""
engine/strategies/ivbs/ivbs_config.py — Per-strategy config singleton for IVBS.

Loads engine/strategies/ivbs/config.yaml once at import time and exposes all
strategy-specific values as typed attributes. This is the SINGLE SOURCE OF TRUTH
for all IVBS parameter reads — scanner.py, state_machine.py,
second_spike_detector.py, and abandoned_setup_tracker.py all import from here.

Design:
  - Module-level singleton `cfg` is loaded at import time (cheap: ~1ms YAML read).
  - Falls back to hardcoded defaults if config.yaml is missing (test safety).
  - No circular imports: this module only reads a YAML file, no engine dependencies.
  - Attribute names mirror the old settings.* names for minimal diffs in callers.

Migration note: this completes the mechanical follow-up documented in config.yaml
(making config.yaml authoritative; removing ~45 settings.* reads from IVBS modules).
"""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"


def _load() -> dict[str, Any]:
    """Load config.yaml. Returns {} on any failure (missing file, bad YAML)."""
    if not _CONFIG_PATH.is_file():
        log.warning("ivbs_config_yaml_missing", path=str(_CONFIG_PATH))
        return {}
    try:
        import yaml
        with _CONFIG_PATH.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        log.warning("ivbs_config_yaml_load_failed", error=str(exc))
        return {}


def _get(data: dict[str, Any], *path: str, default: Any) -> Any:
    """Navigate a nested dict with a dotted key path, returning default if missing."""
    node: Any = data
    for key in path:
        if not isinstance(node, dict):
            return default
        node = node.get(key, default)
    return node


class IVBSConfig:
    """
    Typed view over engine/strategies/ivbs/config.yaml.

    All attributes match the config.yaml structure.
    Grouped to match the YAML sections for easy cross-reference.
    """

    def __init__(self, raw: dict[str, Any]) -> None:
        # ── Scanner ─────────────────────────────────────────────────────────
        sc = raw.get("scanner", {})
        self.VOLUME_SPIKE_MULTIPLE: float        = float(sc.get("volume_spike_multiple", 15.0))
        self.VOLUME_SMA_PERIOD: int              = int(sc.get("volume_sma_period", 500))
        self.MIN_TURNOVER_CRORE: float           = float(sc.get("min_turnover_crore", 8.0))
        self.MIN_PRICE: float                    = float(sc.get("min_price", 50.0))
        self.MAX_PRICE: float                    = float(sc.get("max_price", 5000.0))
        self.SCANNER_START_MINUTE: int           = int(sc.get("scanner_start_minute", 30))
        self.SCAN_CUTOFF_HOUR: int               = int(sc.get("scan_cutoff_hour", 14))
        self.MIN_DRYUP_CANDLES: int              = int(sc.get("min_dryup_candles", 2))

        # ── Re-ignition ──────────────────────────────────────────────────────
        ri = raw.get("reignition", {})
        self.REIGNITION_VOLUME_MULTIPLE: float   = float(ri.get("volume_multiple", 2.0))
        self.REIGNITION_LOOKBACK_CANDLES: int    = int(ri.get("lookback_candles", 3))
        self.REIGNITION_USE_AVG_VOLUME: bool     = bool(ri.get("use_avg_volume", True))
        self.REIGNITION_MIN_PCT_OF_IMPACT: float = float(ri.get("min_pct_of_impact", 0.08))

        # ── A-shape abandonment ──────────────────────────────────────────────
        ash = raw.get("ashape", {})
        self.ASHAPE_RED_CANDLE_PCT: float        = float(ash.get("red_candle_pct", 0.5))
        self.ASHAPE_VOLUME_MULTIPLE: float       = float(ash.get("volume_multiple", 1.5))
        self.ASHAPE_MIN_CANDLE_COUNT: int        = int(ash.get("min_candle_count", 2))
        self.ASHAPE_IMPACT_VOLUME_PCT: float     = float(ash.get("impact_volume_pct", 0.70))

        # ── Second spike ─────────────────────────────────────────────────────
        ss = raw.get("second_spike", {})
        self.SECOND_SPIKE_MIN_RATIO: float               = float(ss.get("min_ratio", 0.50))
        self.SECOND_SPIKE_MAX_RATIO: float               = float(ss.get("max_ratio", 1.00))
        self.SECOND_SPIKE_MIN_GAP_MINUTES: int           = int(ss.get("min_gap_minutes", 15))
        self.SECOND_SPIKE_EXTENDED_GAP_MINUTES: int      = int(ss.get("extended_gap_minutes", 30))
        self.SECOND_SPIKE_VOLUME_FLOOR: float            = float(ss.get("volume_floor", 10.0))
        self.SECOND_SPIKE_PRICE_ABOVE_HIGH_THRESHOLD: float = float(ss.get("price_above_high_threshold", 0.80))
        self.SECOND_SPIKE_PRICE_ABOVE_HIGH_PCT: float    = float(ss.get("price_above_high_pct", 0.005))

        # ── Re-entry after abandonment ───────────────────────────────────────
        re = raw.get("re_entry", {})
        self.RE_ENTRY_ENABLED: bool              = bool(re.get("enabled", True))
        self.RE_ENTRY_MIN_GAP_MINUTES: int       = int(re.get("min_gap_minutes", 15))
        self.RE_ENTRY_VOLUME_MULTIPLE: float     = float(re.get("volume_multiple", 5.0))
        self.RE_ENTRY_MAX_PER_SYMBOL: int        = int(re.get("max_per_symbol", 2))

        # ── Timing / entry ───────────────────────────────────────────────────
        tm = raw.get("timing", {})
        self.DRYUP_MAX_MINUTES: int                = int(tm.get("dryup_max_minutes", 25))
        self.ENTRY_BUFFER_PCT: float               = float(tm.get("entry_buffer_pct", 0.001))
        self.ENTRY_WIDEN_AFTER_SECONDS: int        = int(tm.get("entry_widen_after_seconds", 5))
        self.ENTRY_ABANDON_PCT: float              = float(tm.get("entry_abandon_pct", 0.015))
        self.ORDER_FILL_TIMEOUT_SECONDS: int       = int(tm.get("order_fill_timeout_seconds", 30))
        self.APPROVAL_TIMEOUT_SECONDS: int         = int(tm.get("approval_timeout_seconds", 60))
        self.ABANDON_PRICE_BUFFER_PCT: float       = float(tm.get("abandon_price_buffer_pct", 0.003))
        self.DYNAMIC_TRAILING_ENABLED: bool        = bool(tm.get("dynamic_trailing_enabled", False))
        self.ATR_PERIOD: int                       = int(tm.get("atr_period", 14))
        self.ATR_TRAIL_MULTIPLIER: float           = float(tm.get("atr_trail_multiplier", 2.5))
        self.VWAP_ENTRY_FILTER_ENABLED: bool       = bool(tm.get("vwap_entry_filter_enabled", False))
        self.BACKTEST_MODE: bool                   = bool(tm.get("backtest_mode", False))

        # MAX_ENTRY_TIME: stored as "HH:MM" string in YAML
        _max_entry_raw: str = str(tm.get("max_entry_time", "13:30"))
        self.MAX_ENTRY_TIME: str = _max_entry_raw

        # ── Market gate ──────────────────────────────────────────────────────
        mg = raw.get("market_gate", {})
        self.NIFTY_GATE_ENABLED: bool            = bool(mg.get("nifty_gate_enabled", True))
        self.NIFTY_EMA_PERIOD: int               = int(mg.get("nifty_ema_period", 20))
        self.NIFTY_INSTRUMENT_TOKEN: int         = int(mg.get("nifty_instrument_token", 256265))
        self.VIX_INSTRUMENT_TOKEN: int           = int(mg.get("vix_instrument_token", 264969))
        self.HIGH_VIX_THRESHOLD: float           = float(mg.get("high_vix_threshold", 18.0))
        self.HIGH_VIX_TURNOVER_CRORE: float      = float(mg.get("high_vix_turnover_crore", 12.0))

    @property
    def max_entry_time(self) -> datetime.time:
        """Parsed datetime.time for MAX_ENTRY_TIME (mirrors settings.max_entry_time API)."""
        return datetime.time.fromisoformat(self.MAX_ENTRY_TIME)


# ── Module-level singleton ────────────────────────────────────────────────────
# Loaded once at import time. All IVBS modules import this directly:
#   from engine.strategies.ivbs.ivbs_config import cfg
cfg = IVBSConfig(_load())
