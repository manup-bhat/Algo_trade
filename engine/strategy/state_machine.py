"""
engine/strategy/state_machine.py — Re-export shim.

Canonical home: engine/strategies/ivbs/state_machine.py
This shim preserves all existing import paths with zero breakage.
"""
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
