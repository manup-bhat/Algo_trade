"""
engine/strategy/abandoned_setup_tracker.py — Re-export shim.

Canonical home: engine/strategies/ivbs/abandoned_setup_tracker.py
This shim preserves all existing import paths with zero breakage.
The module-level singleton `abandoned_setup_tracker` lives in the canonical location.
"""
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
