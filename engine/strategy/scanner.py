"""
engine/strategy/scanner.py — DEPRECATED RE-EXPORT SHIM.

Canonical home: engine/strategies/ivbs/scanner.py
This shim preserves backward-compatible import paths (coordinator, tests, backtest).
All logic and module-level state live in the canonical location.

DO NOT add logic here. Update the canonical file and re-export here if needed.
"""
# DEPRECATED SHIM — import from engine.strategies.ivbs.scanner directly
from engine.strategies.ivbs.scanner import (  # noqa: F401
    ImpactCandle,
    evaluate,
    update_market_gate,
)


__all__ = ["ImpactCandle", "evaluate", "update_market_gate"]
