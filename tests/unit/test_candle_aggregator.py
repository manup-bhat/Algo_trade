"""
tests/unit/test_candle_aggregator.py — Unit tests for CandleAggregator.

Tests cover:
  - register_symbol() creates a CandleBuilder.
  - register_symbol() idempotent: second call returns same builder.
  - Two different symbols → two different builders.
  - unregister_symbol() removes the builder.
  - unregister_symbol() blocked when strategy_router says symbol is active.
  - unregister_symbol() succeeds when no active strategy.
  - on_tick() routes to correct builder.
  - on_tick() unknown symbol → None (no crash).
  - on_tick() builder exception → None (no crash, isolated).
  - reset_all_baselines() calls reset_cumulative_baseline on all builders.
  - reset_session() calls reset() on all builders.
  - active_symbols property returns current list.
  - len() and __contains__.
  - get_builder() returns None for unregistered symbol.
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import pytz
import pytest

from engine.market.candle_aggregator import CandleAggregator
from engine.market.candle_builder import CandleBuilder

IST_TZ = pytz.timezone("Asia/Kolkata")


def make_ts(h: int, m: int, s: int = 0) -> datetime.datetime:
    return IST_TZ.localize(datetime.datetime(2026, 9, 9, h, m, s))


# ── register_symbol ───────────────────────────────────────────────────────────

def test_register_symbol_creates_builder():
    agg = CandleAggregator()
    builder = agg.register_symbol("RELIANCE")
    assert isinstance(builder, CandleBuilder)
    assert builder.symbol == "RELIANCE"


def test_register_symbol_idempotent():
    agg = CandleAggregator()
    b1 = agg.register_symbol("TCS")
    b2 = agg.register_symbol("TCS")
    assert b1 is b2  # Same instance returned


def test_register_two_symbols_different_builders():
    agg = CandleAggregator()
    b1 = agg.register_symbol("INFY")
    b2 = agg.register_symbol("WIPRO")
    assert b1 is not b2
    assert b1.symbol == "INFY"
    assert b2.symbol == "WIPRO"


# ── unregister_symbol ─────────────────────────────────────────────────────────

def test_unregister_symbol_removes():
    agg = CandleAggregator()
    agg.register_symbol("RELIANCE")
    removed = agg.unregister_symbol("RELIANCE")
    assert removed is True
    assert "RELIANCE" not in agg


def test_unregister_symbol_already_gone_is_true():
    agg = CandleAggregator()
    result = agg.unregister_symbol("NONEXISTENT")
    assert result is True  # Idempotent


def test_unregister_blocked_when_strategy_active():
    agg = CandleAggregator()
    agg.register_symbol("HDFC")
    router_mock = MagicMock()
    router_mock.any_strategy_has_active_symbol.return_value = True
    result = agg.unregister_symbol("HDFC", strategy_router=router_mock)
    assert result is False
    assert "HDFC" in agg  # Still registered


def test_unregister_succeeds_when_no_active_strategy():
    agg = CandleAggregator()
    agg.register_symbol("HDFC")
    router_mock = MagicMock()
    router_mock.any_strategy_has_active_symbol.return_value = False
    result = agg.unregister_symbol("HDFC", strategy_router=router_mock)
    assert result is True
    assert "HDFC" not in agg


# ── on_tick ───────────────────────────────────────────────────────────────────

def test_on_tick_unknown_symbol_returns_none():
    agg = CandleAggregator()
    result = agg.on_tick("UNKNOWNSYM", 100.0, 1000, make_ts(9, 16))
    assert result is None


def test_on_tick_routes_to_correct_builder():
    agg = CandleAggregator()
    # Register symbol and warm up baseline (first tick sets baseline)
    agg.register_symbol("INFY")
    # First tick sets baseline, returns None
    result = agg.on_tick("INFY", 1500.0, 10000, make_ts(9, 15, 1))
    assert result is None  # baseline tick, no candle


def test_on_tick_builder_exception_returns_none():
    """A crashing builder must not propagate to coordinator."""
    agg = CandleAggregator()
    agg.register_symbol("BAD")
    # Patch builder.on_tick to raise
    agg._builders["BAD"] = MagicMock()
    agg._builders["BAD"].on_tick.side_effect = RuntimeError("builder crash")

    result = agg.on_tick("BAD", 100.0, 1000, make_ts(9, 16))
    assert result is None  # Exception swallowed


# ── reset_all_baselines ───────────────────────────────────────────────────────

def test_reset_all_baselines_calls_all_builders():
    agg = CandleAggregator()
    agg._builders["A"] = MagicMock(symbol="A")
    agg._builders["B"] = MagicMock(symbol="B")
    agg.reset_all_baselines()
    agg._builders["A"].reset_cumulative_baseline.assert_called_once()
    agg._builders["B"].reset_cumulative_baseline.assert_called_once()


def test_reset_all_baselines_one_crashes_others_still_called():
    """A crashing builder.reset_cumulative_baseline must not stop others."""
    agg = CandleAggregator()
    m_crash = MagicMock(symbol="CRASH")
    m_crash.reset_cumulative_baseline.side_effect = RuntimeError("crash")
    m_ok = MagicMock(symbol="OK")
    agg._builders["CRASH"] = m_crash
    agg._builders["OK"] = m_ok

    agg.reset_all_baselines()  # Must not raise
    m_ok.reset_cumulative_baseline.assert_called_once()


# ── reset_session ─────────────────────────────────────────────────────────────

def test_reset_session_calls_reset_on_all():
    agg = CandleAggregator()
    agg._builders["X"] = MagicMock(symbol="X")
    agg._builders["Y"] = MagicMock(symbol="Y")
    agg.reset_session()
    agg._builders["X"].reset.assert_called_once()
    agg._builders["Y"].reset.assert_called_once()


# ── Queries ───────────────────────────────────────────────────────────────────

def test_active_symbols():
    agg = CandleAggregator()
    agg.register_symbol("A")
    agg.register_symbol("B")
    syms = agg.active_symbols
    assert set(syms) == {"A", "B"}


def test_len():
    agg = CandleAggregator()
    assert len(agg) == 0
    agg.register_symbol("A")
    assert len(agg) == 1
    agg.register_symbol("B")
    assert len(agg) == 2


def test_contains():
    agg = CandleAggregator()
    agg.register_symbol("A")
    assert "A" in agg
    assert "B" not in agg


def test_get_builder_returns_none_for_unregistered():
    agg = CandleAggregator()
    assert agg.get_builder("NOTHERE") is None


def test_get_builder_returns_builder_for_registered():
    agg = CandleAggregator()
    b = agg.register_symbol("RELIANCE")
    assert agg.get_builder("RELIANCE") is b
