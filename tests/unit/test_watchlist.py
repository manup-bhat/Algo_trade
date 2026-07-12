"""Phase 7 — editable, hot-reloadable watchlist.

Covers:
  * validate_symbols / normalize_symbol  (engine/market/watchlist.py)
  * WatchlistManager file persistence + delta reporting
  * RedisStore pending-watchlist IPC round-trip (getdel semantics)
  * Coordinator.apply_watchlist live builder reconciliation
  * dashboard add-symbols endpoint firing the hot-reload signal
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.market.watchlist import (
    MAX_WATCHLIST_SIZE,
    WatchlistManager,
    normalize_symbol,
    validate_symbols,
)


# ── validate_symbols / normalize_symbol ─────────────────────────────────────

def test_normalize_symbol_strips_decoration():
    assert normalize_symbol("  nse:tatamotors  ") == "TATAMOTORS"
    assert normalize_symbol("infy.ns") == "INFY"


def test_validate_symbols_normalizes_and_dedupes():
    valid, rejected = validate_symbols(["reliance", "RELIANCE", " infy ", ""])
    assert valid == ["RELIANCE", "INFY"]
    assert rejected == []


def test_validate_symbols_rejects_unknown_when_known_given():
    known = {"RELIANCE", "INFY"}
    valid, rejected = validate_symbols(["RELIANCE", "FAKE", "infy"], known=known)
    assert valid == ["RELIANCE", "INFY"]
    assert rejected == ["FAKE"]


# ── WatchlistManager ─────────────────────────────────────────────────────────

def test_watchlist_manager_set_get_and_delta(tmp_path):
    path = tmp_path / "universe.txt"
    wm = WatchlistManager(path=path)

    first = wm.set(["AAA", "BBB", "CCC"])
    assert first["symbols"] == ["AAA", "BBB", "CCC"]
    assert first["added"] == ["AAA", "BBB", "CCC"]
    assert first["removed"] == []
    assert wm.get() == ["AAA", "BBB", "CCC"]

    second = wm.set(["BBB", "CCC", "DDD"])
    assert second["added"] == ["DDD"]
    assert second["removed"] == ["AAA"]
    assert wm.get() == ["BBB", "CCC", "DDD"]


def test_watchlist_manager_empty_raises(tmp_path):
    wm = WatchlistManager(path=tmp_path / "universe.txt")
    with pytest.raises(ValueError, match="watchlist_empty"):
        wm.set([])


def test_watchlist_manager_too_large_raises(tmp_path):
    wm = WatchlistManager(path=tmp_path / "universe.txt")
    with pytest.raises(ValueError, match="watchlist_too_large"):
        wm.set([f"SYM{i}" for i in range(MAX_WATCHLIST_SIZE + 1)])


# ── RedisStore pending-watchlist IPC ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_redis_pending_watchlist_roundtrip(redis_store):
    assert await redis_store.consume_pending_watchlist() is None

    await redis_store.set_pending_watchlist(["AAA", "BBB"])
    got = await redis_store.consume_pending_watchlist()
    assert got == ["AAA", "BBB"]

    # getdel semantics: a second consume returns None (signal is one-shot)
    assert await redis_store.consume_pending_watchlist() is None


# ── Coordinator.apply_watchlist ──────────────────────────────────────────────

def _resolver(mapping):
    """Return a resolve(symbol) callable backed by ``mapping`` (symbol -> token)."""
    def _resolve(symbol):
        token = mapping.get(symbol)
        if token is None:
            return None
        return SimpleNamespace(instrument_token=token)
    return _resolve


@pytest.mark.asyncio
async def test_coordinator_apply_watchlist_add_and_remove(redis_store):
    from engine.strategy.coordinator import Coordinator

    coord = Coordinator(redis_store, None)
    resolve = _resolver({"AAA": 101, "BBB": 102, "CCC": 103})

    added, removed = coord.apply_watchlist(["AAA", "BBB"], resolve)
    assert sorted(added) == [101, 102]
    assert removed == []
    assert set(coord.candle_builders) == {"AAA", "BBB"}
    assert coord.symbol_to_token == {"AAA": 101, "BBB": 102}
    assert coord.token_to_symbol == {101: "AAA", 102: "BBB"}

    # Drop BBB, add CCC in a single reconcile.
    added2, removed2 = coord.apply_watchlist(["AAA", "CCC"], resolve)
    assert added2 == [103]
    assert removed2 == [102]
    assert set(coord.candle_builders) == {"AAA", "CCC"}
    assert 102 not in coord.token_to_symbol


@pytest.mark.asyncio
async def test_coordinator_apply_watchlist_skips_unknown(redis_store):
    from engine.strategy.coordinator import Coordinator

    coord = Coordinator(redis_store, None)
    resolve = _resolver({"AAA": 101})  # BBB is unknown

    added, removed = coord.apply_watchlist(["AAA", "BBB"], resolve)
    assert added == [101]
    assert set(coord.candle_builders) == {"AAA"}  # BBB skipped (unresolved)


@pytest.mark.asyncio
async def test_coordinator_apply_watchlist_protects_active_symbol(redis_store, monkeypatch):
    from engine.strategy.coordinator import Coordinator

    coord = Coordinator(redis_store, None)
    resolve = _resolver({"AAA": 101, "BBB": 102})
    coord.apply_watchlist(["AAA", "BBB"], resolve)

    # BBB has a live position/setup — it must NOT be removed by an edit.
    monkeypatch.setattr(
        coord.strategy_router,
        "any_strategy_has_active_symbol",
        lambda sym: sym == "BBB",
    )

    added, removed = coord.apply_watchlist(["AAA"], resolve)
    assert added == []
    assert removed == []  # BBB protected
    assert set(coord.candle_builders) == {"AAA", "BBB"}


# ── Dashboard endpoint → hot-reload signal ───────────────────────────────────

@pytest.mark.asyncio
async def test_add_universe_symbols_signals_hot_reload(redis_store, monkeypatch, tmp_path):
    from app.api import dashboard_router
    from app.api.dashboard_router import UniverseSymbolsPayload
    from app.core.config import settings

    uni = tmp_path / "universe.txt"
    uni.write_text("AAA\nBBB\n", encoding="utf-8")
    monkeypatch.setattr(settings, "UNIVERSE_FILE", str(uni))

    dashboard_router.set_dependencies(redis_store, None)

    async def _fake_instr_cache():
        return [{"symbol": "CCC", "instrument_token": 111, "tick_size": 0.05}]

    async def _noop_broadcast(_payload):
        return None

    monkeypatch.setattr(dashboard_router, "_load_instrument_search_cache", _fake_instr_cache)
    monkeypatch.setattr(dashboard_router, "_get_cached_universe", lambda: ["AAA", "BBB"])
    monkeypatch.setattr(dashboard_router, "broadcast", _noop_broadcast)

    result = await dashboard_router.add_universe_symbols(UniverseSymbolsPayload(symbols=["CCC"]))
    assert "CCC" in result["added"]

    # The engine (separate process) must receive the FULL new universe to reconcile.
    pending = await redis_store.consume_pending_watchlist()
    assert pending == ["AAA", "BBB", "CCC"]
