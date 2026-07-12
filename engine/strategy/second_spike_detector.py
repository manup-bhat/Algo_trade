"""
engine/strategy/second_spike_detector.py — Re-export shim.

Canonical home: engine/strategies/ivbs/second_spike_detector.py
This shim preserves all existing import paths with zero breakage.
"""
from engine.strategies.ivbs.second_spike_detector import (  # noqa: F401
    PriorSpikeRecord,
    SecondSpikeEntry,
    SecondSpikeDetector,
)

__all__ = ["PriorSpikeRecord", "SecondSpikeEntry", "SecondSpikeDetector"]
