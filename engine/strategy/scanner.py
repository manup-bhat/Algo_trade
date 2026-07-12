"""
engine/strategy/scanner.py — Re-export shim.

Canonical home: engine/strategies/ivbs/scanner.py
This shim preserves all existing import paths (coordinator, tests, backtest etc.)
with zero breakage. All logic and module-level state (market gate cache) live in
the canonical location.
"""
# Re-export everything from the canonical location
from engine.strategies.ivbs.scanner import (  # noqa: F401
    ImpactCandle,
    evaluate,
    update_market_gate,
)

__all__ = ["ImpactCandle", "evaluate", "update_market_gate"]
