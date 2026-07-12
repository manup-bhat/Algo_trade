"""Tests for the re-entry (abandoned setup) tracker — previously UNTESTED.

Covers engine/strategy/abandoned_setup_tracker.py: which abandonment reasons are
eligible for re-entry, and every re-entry gate (gap, structure-break, volume floor,
level reclaim, green candle, cutoff, per-symbol cap).
"""

from __future__ import annotations

import asyncio
import datetime

import pytest
import pytz

from engine.strategy.abandoned_setup_tracker import (
    REENTRY_ALLOWED_REASONS,
    AbandonedSetupTracker,
)

IST = pytz.timezone("Asia/Kolkata")


def ist(hour: int, minute: int) -> datetime.datetime:
    return datetime.datetime.now(IST).replace(hour=hour, minute=minute, second=0, microsecond=0)


def _record(tracker: AbandonedSetupTracker, reason: str = "timeout") -> None:
    tracker.record(
        symbol="ACME",
        abandon_time=ist(10, 0),
        impact_close=100.0,
        impact_low=98.0,
        impact_high=101.0,
        impact_volume=500_000,
        reason=reason,
    )


# ── record() eligibility ─────────────────────────────────────────────────────

def test_allowed_reasons_are_recorded():
    t = AbandonedSetupTracker()
    _record(t, "timeout")
    assert t.has_record("ACME")


def test_structure_break_reason_not_recorded():
    t = AbandonedSetupTracker()
    _record(t, "price_broke_impact_low")
    assert not t.has_record("ACME")


def test_reentry_allowed_reason_set_excludes_structure_break():
    assert "price_broke_impact_low" not in REENTRY_ALLOWED_REASONS
    assert "timeout" in REENTRY_ALLOWED_REASONS


# ── evaluate() rejection gates (all return False before any DB task) ─────────

def test_evaluate_no_record_returns_false():
    t = AbandonedSetupTracker()
    assert t.evaluate("NOPE", 100, 101, 99, 100, 999999, ist(11, 0), 10_000) is False


def test_evaluate_gap_too_small():
    t = AbandonedSetupTracker()
    _record(t)  # abandoned 10:00
    # 10:05 → only 5 min < RE_ENTRY_MIN_GAP_MINUTES(15)
    assert t.evaluate("ACME", 100.5, 103, 99.5, 102, 60_000, ist(10, 5), 10_000) is False


def test_evaluate_price_below_impact_low_clears_record():
    t = AbandonedSetupTracker()
    _record(t)
    # candle_low 97 < impact_low 98 → structure broken → False + cleared
    assert t.evaluate("ACME", 100.5, 103, 97.0, 102, 60_000, ist(10, 30), 10_000) is False
    assert not t.has_record("ACME")


def test_evaluate_volume_below_threshold():
    t = AbandonedSetupTracker()
    _record(t)
    # threshold = 5 x 10_000 = 50_000; 40_000 < 50_000
    assert t.evaluate("ACME", 100.5, 103, 99.5, 102, 40_000, ist(10, 30), 10_000) is False


def test_evaluate_close_not_reclaiming_impact_close():
    t = AbandonedSetupTracker()
    _record(t)
    # close 99.5 <= impact_close 100 → not reclaimed
    assert t.evaluate("ACME", 99.0, 100, 99.0, 99.5, 60_000, ist(10, 30), 10_000) is False


def test_evaluate_not_green():
    t = AbandonedSetupTracker()
    _record(t)
    # close 101 <= open 102 → red candle
    assert t.evaluate("ACME", 102.0, 103, 100.5, 101.0, 60_000, ist(10, 30), 10_000) is False


def test_evaluate_after_cutoff():
    t = AbandonedSetupTracker()
    _record(t)
    # 13:45 >= MAX_ENTRY_TIME(13:30)
    assert t.evaluate("ACME", 100.5, 103, 99.5, 102, 60_000, ist(13, 45), 10_000) is False


def test_evaluate_none_sma_returns_false():
    t = AbandonedSetupTracker()
    _record(t)
    assert t.evaluate("ACME", 100.5, 103, 99.5, 102, 60_000, ist(10, 30), None) is False


# ── evaluate() success + cap (fires a fire-and-forget snapshot task) ─────────

@pytest.mark.asyncio
async def test_evaluate_success_increments_and_respects_cap(monkeypatch):
    # Stub out the fire-and-forget DB snapshot so no real DB work happens.
    class _FakeDbWriter:
        async def write_signal_snapshot(self, **kwargs):
            return None

    monkeypatch.setattr("engine.store.db_writer.DbWriter", _FakeDbWriter)

    t = AbandonedSetupTracker()
    _record(t)
    rec = t.get_impact_data("ACME")

    # All gates pass: gap ok, low>=impact_low, vol>=50k, close>100, green, before cutoff
    ok1 = t.evaluate("ACME", 100.5, 103, 99.5, 102.0, 60_000, ist(10, 30), 10_000)
    await asyncio.sleep(0)  # let the snapshot task run
    assert ok1 is True
    assert rec.reentry_count == 1

    ok2 = t.evaluate("ACME", 100.5, 103, 99.5, 102.0, 60_000, ist(10, 45), 10_000)
    await asyncio.sleep(0)
    assert ok2 is True
    assert rec.reentry_count == 2

    # Third attempt is blocked by RE_ENTRY_MAX_PER_SYMBOL (2)
    ok3 = t.evaluate("ACME", 100.5, 103, 99.5, 102.0, 60_000, ist(11, 0), 10_000)
    assert ok3 is False
    assert rec.reentry_count == 2


# ── housekeeping ─────────────────────────────────────────────────────────────

def test_update_low_tracks_minimum():
    t = AbandonedSetupTracker()
    _record(t)
    t.update_low("ACME", 97.5)
    t.update_low("ACME", 99.0)
    assert t.get_impact_data("ACME").inter_session_low == 97.5


def test_clear_and_clear_all():
    t = AbandonedSetupTracker()
    _record(t)
    assert t.active_count() == 1
    t.clear("ACME")
    assert t.active_count() == 0
    _record(t)
    t.clear_all()
    assert t.active_count() == 0
