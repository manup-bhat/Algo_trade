"""
engine/strategy/state_machine.py — DEPRECATED RE-EXPORT SHIM.

Canonical home: engine/strategies/ivbs/state_machine.py
This shim preserves all existing import paths with zero breakage.
DO NOT add logic here.
"""
# DEPRECATED SHIM — import from engine.strategies.ivbs.state_machine directly
from engine.strategies.ivbs.state_machine import (  # noqa: F401
    StrategyState,
    ConsolidationData,
    OpenPosition,
    SymbolStateMachine,
)

__all__ = [
    "StrategyState",
    "ConsolidationData",
    "OpenPosition",
    "SymbolStateMachine",
]
