"""
tests/unit/test_registry.py — Unit tests for engine.core.registry.Registry.

Tests cover:
  - Register and retrieve.
  - Duplicate registration raises ValueError.
  - Missing key raises KeyError.
  - get_or_none returns None for missing keys.
  - list_keys returns sorted snapshot.
  - unregister removes key; double-unregister is safe.
  - has() queries.
  - Empty registry size.
  - Invalid key types raise TypeError.
"""

from __future__ import annotations

import pytest
from engine.core.registry import Registry


class FakeProvider:
    def __init__(self, name: str) -> None:
        self.name = name


def make_registry() -> Registry:
    return Registry("test")


# ── Basic register/get ─────────────────────────────────────────────────────────

def test_register_and_get():
    reg = make_registry()
    p = FakeProvider("a")
    reg.register("a", p)
    assert reg.get("a") is p


def test_get_or_none_hit():
    reg = make_registry()
    p = FakeProvider("b")
    reg.register("b", p)
    assert reg.get_or_none("b") is p


def test_get_or_none_miss():
    reg = make_registry()
    assert reg.get_or_none("nonexistent") is None


def test_get_missing_raises_key_error():
    reg = make_registry()
    with pytest.raises(KeyError, match="nonexistent"):
        reg.get("nonexistent")


def test_get_key_error_message_lists_available():
    reg = make_registry()
    reg.register("existing", FakeProvider("existing"))
    with pytest.raises(KeyError, match="existing"):
        reg.get("missing_key")


# ── Duplicate / collision ─────────────────────────────────────────────────────

def test_duplicate_registration_raises():
    reg = make_registry()
    reg.register("dup", FakeProvider("1"))
    with pytest.raises(ValueError, match="already registered"):
        reg.register("dup", FakeProvider("2"))


def test_original_survives_duplicate_attempt():
    reg = make_registry()
    p1 = FakeProvider("orig")
    reg.register("key", p1)
    try:
        reg.register("key", FakeProvider("new"))
    except ValueError:
        pass
    # Original must still be there
    assert reg.get("key") is p1


# ── Invalid keys ──────────────────────────────────────────────────────────────

def test_empty_string_key_raises():
    reg = make_registry()
    with pytest.raises(TypeError):
        reg.register("", FakeProvider("x"))


def test_non_string_key_raises():
    reg = make_registry()
    with pytest.raises(TypeError):
        reg.register(123, FakeProvider("x"))  # type: ignore[arg-type]


# ── list_keys ─────────────────────────────────────────────────────────────────

def test_list_keys_empty():
    reg = make_registry()
    assert reg.list_keys() == []


def test_list_keys_sorted():
    reg = make_registry()
    reg.register("z_key", FakeProvider("z"))
    reg.register("a_key", FakeProvider("a"))
    reg.register("m_key", FakeProvider("m"))
    assert reg.list_keys() == ["a_key", "m_key", "z_key"]


def test_list_keys_snapshot():
    reg = make_registry()
    reg.register("k", FakeProvider("k"))
    keys1 = reg.list_keys()
    reg.register("k2", FakeProvider("k2"))
    keys2 = reg.list_keys()
    # First snapshot should not have been mutated
    assert "k2" not in keys1
    assert "k2" in keys2


# ── has / len ─────────────────────────────────────────────────────────────────

def test_has_returns_true():
    reg = make_registry()
    reg.register("x", FakeProvider("x"))
    assert reg.has("x")


def test_has_returns_false():
    reg = make_registry()
    assert not reg.has("missing")


def test_len_empty():
    reg = make_registry()
    assert len(reg) == 0


def test_len_after_register():
    reg = make_registry()
    reg.register("a", FakeProvider("a"))
    reg.register("b", FakeProvider("b"))
    assert len(reg) == 2


# ── unregister ────────────────────────────────────────────────────────────────

def test_unregister_removes():
    reg = make_registry()
    reg.register("r", FakeProvider("r"))
    assert reg.has("r")
    reg.unregister("r")
    assert not reg.has("r")


def test_double_unregister_safe():
    """Unregistering an already-missing key should not raise."""
    reg = make_registry()
    reg.unregister("never_existed")   # should log warning, not raise
    reg.register("t", FakeProvider("t"))
    reg.unregister("t")
    reg.unregister("t")              # double-unregister should also be safe


def test_unregister_then_reregister():
    reg = make_registry()
    p1 = FakeProvider("1")
    p2 = FakeProvider("2")
    reg.register("slot", p1)
    reg.unregister("slot")
    reg.register("slot", p2)  # must not raise — slot is free
    assert reg.get("slot") is p2


# ── Repr ──────────────────────────────────────────────────────────────────────

def test_repr():
    reg = make_registry()
    reg.register("foo", FakeProvider("foo"))
    r = repr(reg)
    assert "foo" in r
    assert "test" in r
