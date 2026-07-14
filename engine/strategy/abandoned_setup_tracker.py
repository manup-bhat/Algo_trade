"""
engine/strategy/abandoned_setup_tracker.py — DEPRECATED RE-EXPORT SHIM.

Canonical home: engine/strategies/ivbs/abandoned_setup_tracker.py
This shim preserves all existing import paths with zero breakage.
DO NOT add logic here.
"""
# DEPRECATED SHIM — import from engine.strategies.ivbs.abandoned_setup_tracker directly
from engine.strategies.ivbs.abandoned_setup_tracker import (  # noqa: F401
    REENTRY_ALLOWED_REASONS,
    AbandonedRecord,
    AbandonedSetupTracker,
    abandoned_setup_tracker,
)

__all__ = [
    "REENTRY_ALLOWED_REASONS",
    "AbandonedRecord",
    "AbandonedSetupTracker",
    "abandoned_setup_tracker",
]
