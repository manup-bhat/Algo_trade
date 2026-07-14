"""
engine/strategy/second_spike_detector.py — DEPRECATED RE-EXPORT SHIM.

Canonical home: engine/strategies/ivbs/second_spike_detector.py
This shim preserves all existing import paths with zero breakage.
DO NOT add logic here.
"""
# DEPRECATED SHIM — import from engine.strategies.ivbs.second_spike_detector directly
from engine.strategies.ivbs.second_spike_detector import (  # noqa: F401
    PriorSpikeRecord,
    SecondSpikeEntry,
    SecondSpikeDetector,
)

__all__ = ["PriorSpikeRecord", "SecondSpikeEntry", "SecondSpikeDetector"]
