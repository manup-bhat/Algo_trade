# Multi-Strategy Engine Refactor

## Background

The current codebase implements a single strategy called **IVBS (Institutional Volume Breakout Strategy)**. The strategy logic is tightly fused with the engine infrastructure:
- `coordinator.py` (1029 lines) both dispatches ticks **and** runs IVBS-specific logic (second spike detector, abandoned setup tracker, re-entry detection)
- `state_machine.py` (1555 lines) tightly couples order management, risk checks, and IVBS-specific state transitions
- `scanner.py` is the IVBS scanner — but it's hard-coded into the coordinator's `_on_candle_complete` path
- Multiple IVBS-only singletons (`second_spike_detector`, `abandoned_setup_tracker`) live directly in the coordinator
- `runner.py` wires everything to a specific `Coordinator` type — no abstraction layer

The goal is to extract a clean **base engine layer** so that future strategies (e.g., VWAP reversion, opening range breakout, EMA crossover, etc.) can be added as independent plugins without touching core infrastructure code.

---

## Design Philosophy

### Guiding Principles
- **Open/Closed Principle**: The engine is open for extension (new strategies), closed for modification
- **Dependency Inversion**: Coordinator depends on `BaseStrategy` abstraction, not concrete implementations
- **Single Responsibility**: Coordinator routes data, strategies implement trading logic
- **Isolated Failure**: A bug in one strategy cannot crash another strategy or the engine
- **Zero Regression**: All existing IVBS behavior is preserved — it becomes Strategy #1

### Architecture Pattern: Strategy Plugin Registry

```
┌─────────────────────────────────────────────────────────────────────┐
│                         engine/runner.py                            │
│                    (lifecycle orchestrator)                          │
└───────────────────────────────┬────────────────────────────────────┘
                                │ creates & wires
┌───────────────────────────────▼────────────────────────────────────┐
│                  engine/core/coordinator.py                         │
│                   (event router — pure dispatcher)                  │
│                                                                     │
│  - routes ticks to candle builders                                  │
│  - on candle complete → fires StrategyRouter                        │
│  - maintains token↔symbol maps, WS lifecycle                        │
└────────────────┬──────────────────────┬───────────────────────────┘
                 │ candle data           │ candle data
┌────────────────▼──────────────────────▼───────────────────────────┐
│               engine/core/strategy_router.py                        │
│              (fans out candles to ALL active strategies)            │
│                                                                     │
│  - holds dict[strategy_id, BaseStrategy]                            │
│  - calls strategy.on_candle(symbol, candle, builder)                │
│  - handles isolated exceptions per strategy                         │
└──────────────┬──────────────────────────────────────────────────────┘
               │ implements
 ┌─────────────▼────────────────────────────────────────────────────┐
 │          engine/core/base_strategy.py                             │
 │              Abstract interface (ABC)                             │
 │                                                                   │
 │  + strategy_id: str                                               │
 │  + on_market_open()                                               │
 │  + on_candle(symbol, candle, builder)                             │
 │  + on_tick(symbol, ltp, ts)                 [MANAGING only]       │
 │  + on_order_postback(message)                                     │
 │  + on_squareoff()                                                 │
 │  + on_session_end()                                               │
 │  + get_stats() → dict                                             │
 └────────────────────────────────────────────────────────────────┘
               │ implements
 ┌─────────────▼────────────────────────────────────────────────────┐
 │    engine/strategies/ivbs/                                        │
 │       (IVBS Plugin — current code refactored in)                  │
 │                                                                   │
 │    ├── __init__.py                                                │
 │    ├── strategy.py        ← IVBSStrategy(BaseStrategy)            │
 │    │       owns: active_sms, second_spike_detector,               │
 │    │             abandoned_setup_tracker                           │
 │    ├── scanner.py         ← moved from engine/strategy/           │
 │    ├── state_machine.py   ← moved from engine/strategy/           │
 │    ├── second_spike_detector.py                                   │
 │    └── abandoned_setup_tracker.py                                 │
 └────────────────────────────────────────────────────────────────┘
```

---

## User Review Required

> [!IMPORTANT]
> **This is a significant structural refactor.** No runtime behavior changes are intended — only file layout and abstraction boundaries change. All IVBS strategy logic stays identical.

> [!WARNING]
> **Migration strategy**: We will do this in 3 phases. Phase 1 is non-breaking (pure additions). Phase 2 moves IVBS into its plugin package. Phase 3 cleans up the old coordinator. At each phase the tests must pass before proceeding.

> [!CAUTION]
> The `runner.py` currently imports directly from `engine.strategy.coordinator`, `engine.strategy.state_machine`, etc. These imports will be updated to point to new locations. The old locations will keep compatibility re-exports (`from engine.strategies.ivbs.scanner import ...`) during migration.

---

## Open Questions

> [!IMPORTANT]
> **Q1: Strategy config isolation** — Each strategy needs its own config params. Should we:
> - **(A)** Keep a single `Settings` class with namespaced attributes (`IVBS_VOLUME_SPIKE_MULTIPLE`, `ORB_BREAKOUT_PCT`)
> - **(B)** Split into `app/core/config.py` (engine infra settings) + per-strategy YAML files in `engine/strategies/ivbs/config.yaml`
>
> Recommendation: **Option B** — cleaner, no monolithic config explosion

> [!IMPORTANT]
> **Q2: Multi-strategy postback routing** — Currently `coordinator.on_order_postback` → `order_tracker.on_postback(message, coordinator, db)`. With multiple strategies, `order_tracker` needs to know which strategy's SM registered the order.
>
> Proposed fix: `order_tracker.register_entry(order_id, symbol, strategy_id)` — route postback to `strategy_router.get_strategy(strategy_id).on_order_postback(message)`.

> [!IMPORTANT]
> **Q3: Cross-strategy position conflict** — If two strategies fire on the same symbol simultaneously, do we:
> - **(A)** Allow it (each strategy has its own SM lifecycle)
> - **(B)** Block it at the GlobalRiskManager level (one active trade per symbol per day)
>
> Recommendation: **Option B** — the existing pre-trade checks + `circuit_breaker` already block concurrent positions for the same symbol. This behavior should be preserved.

---

## Proposed Changes

### Phase 1: Create the Base Layer (Non-Breaking)

#### [NEW] `engine/core/__init__.py`
Empty init — creates the `engine/core` package.

#### [NEW] `engine/core/base_strategy.py`
Abstract base class that every strategy plugin must implement.

```python
from abc import ABC, abstractmethod
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from engine.market.candle_builder import Candle, CandleBuilder
    from engine.store.redis_store import RedisStore
    from engine.store.db_writer import DbWriter
    from engine.orders.order_service import OrderService
    from engine.orders.order_tracker import OrderTracker
    from engine.orders.fill_timeout import FillTimeoutManager
    from engine.kite.client import AsyncKiteClient

class BaseStrategy(ABC):
    """
    Abstract base for all strategy plugins.
    
    The engine calls these methods at the right lifecycle points.
    Strategies must implement all abstract methods and must NOT
    import from each other (no cross-strategy coupling).
    """

    def __init__(
        self,
        strategy_id: str,
        redis_store: "RedisStore",
        db_writer: "DbWriter",
    ) -> None:
        self.strategy_id = strategy_id
        self._redis = redis_store
        self._db = db_writer

    def inject_execution(
        self,
        order_service: "OrderService",
        order_tracker: "OrderTracker",
        fill_timeout_manager: "FillTimeoutManager",
        kite: "AsyncKiteClient | None" = None,
    ) -> None:
        """Wire live execution dependencies. Called after auth succeeds."""
        ...

    @abstractmethod
    async def on_market_open(self) -> None:
        """09:15 AM — reset internal state for new session."""
        ...

    @abstractmethod
    async def on_candle(
        self,
        symbol: str,
        candle: "Candle",
        builder: "CandleBuilder",
        instrument_token: int,
    ) -> None:
        """Called for every completed 1-min candle for every universe symbol."""
        ...

    async def on_tick(
        self,
        symbol: str,
        ltp: float,
        exchange_ts: Any,
    ) -> None:
        """Optional: per-tick hook for MANAGING symbols only."""
        pass

    @abstractmethod
    async def on_order_postback(self, message: dict) -> None:
        """Route KiteTicker order postback to the right SM."""
        ...

    @abstractmethod
    async def on_squareoff(self) -> None:
        """03:20 PM — force close all open positions."""
        ...

    async def on_session_end(self) -> None:
        """03:25 PM — optional cleanup/persistence."""
        pass

    @abstractmethod
    def get_stats(self) -> dict[str, Any]:
        """Return strategy stats for dashboard/logging."""
        ...

    @abstractmethod
    def is_symbol_active(self, symbol: str) -> bool:
        """True if this strategy has an open SM for the symbol."""
        ...
```

#### [NEW] `engine/core/strategy_router.py`
Fan-out router that holds all registered strategies and dispatches events.

Key behaviors:
- `register(strategy)` — add a strategy plugin at startup
- `on_candle(symbol, candle, builder, token)` — calls ALL strategies' `on_candle` in order, with isolated `try/except` per strategy  
- `on_tick(symbol, ltp, ts)` — same isolation pattern
- `on_order_postback(message)` — routes to the strategy that owns this order (via `strategy_id` tag on the order)
- `on_squareoff()`, `on_market_open()`, `on_session_end()` — broadcast to all
- `get_combined_stats()` — merges `get_stats()` from all strategies into a single dict (prefixed by `strategy_id`)
- `any_strategy_has_active_sm(symbol)` — used by coordinator to determine whether to route per-tick updates

---

### Phase 2: Refactor IVBS Into a Plugin Package

#### [NEW] `engine/strategies/__init__.py`
Empty init — creates the strategies plugin directory.

#### [NEW] `engine/strategies/ivbs/__init__.py`
Exports `IVBSStrategy`.

#### [NEW] `engine/strategies/ivbs/strategy.py`
`IVBSStrategy(BaseStrategy)` — replaces the IVBS-specific parts of `coordinator.py`.

Moves from coordinator to this class:
- `active_state_machines: dict[str, SymbolStateMachine]`
- `second_spike_detector: SecondSpikeDetector`
- `abandoned_setup_tracker` reference
- `_on_candle_complete_ivbs()` — IDLE/non-IDLE routing logic, scanner call, second-spike, re-entry
- `_handle_second_spike_entry()`
- `_handle_re_entry()`
- `_create_sm()`
- `on_squareoff()` IVBS logic
- `on_market_open()` IVBS reset logic
- `get_stats()` IVBS counters

#### [MOVE] `engine/strategies/ivbs/scanner.py`
Move `engine/strategy/scanner.py` → `engine/strategies/ivbs/scanner.py`
Old path keeps a compatibility re-export shim:
```python
# engine/strategy/scanner.py (SHIM — delete after 1 release)
from engine.strategies.ivbs.scanner import *  # noqa: F401, F403
```

#### [MOVE] `engine/strategies/ivbs/state_machine.py`
Move `engine/strategy/state_machine.py` → `engine/strategies/ivbs/state_machine.py`
Old path keeps re-export shim.

#### [MOVE] `engine/strategies/ivbs/second_spike_detector.py`
Move `engine/strategy/second_spike_detector.py` → `engine/strategies/ivbs/second_spike_detector.py`

#### [MOVE] `engine/strategies/ivbs/abandoned_setup_tracker.py`
Move `engine/strategy/abandoned_setup_tracker.py` → `engine/strategies/ivbs/abandoned_setup_tracker.py`

#### [NEW] `engine/strategies/ivbs/config.py`
Extract IVBS-specific settings from `app/core/config.py` into an IVBS-namespaced Pydantic settings block or a dedicated config dataclass. Settings like `VOLUME_SPIKE_MULTIPLE`, `REIGNITION_*`, `ASHAPE_*`, `SECOND_SPIKE_*`, `RE_ENTRY_*`, `DRYUP_*` are IVBS-specific.

Engine-level settings stay in `app/core/config.py`: `REDIS_URL`, `DATABASE_URL`, `KITE_*`, `PAPER_TRADE`, `RISK_PER_TRADE_PCT`, `MAX_CONCURRENT_POSITIONS`, etc.

---

### Phase 3: Slim Down `coordinator.py` → `engine/core/coordinator.py`

#### [MODIFY] `engine/strategy/coordinator.py` → eventually `engine/core/coordinator.py`

The refactored coordinator becomes a **pure dispatcher**:

**Keeps:**
- `candle_builders: dict[str, CandleBuilder]`
- `token_to_symbol` / `symbol_to_token` maps
- `_redis`, `_db`
- `_nifty_ema` / `_vix_ltp` / `_nifty_ltp` + Nifty gate logic
- `process_ticks()` — hot path tick routing to builders
- `on_websocket_connected/reconnect/fatal_disconnect()`
- `initialize_builders()`, `load_sma_histories()`, `persist_sma_histories()`
- `orphan_check()`, `reconcile_orders()`
- `inject_dependencies()` — now also sets up strategy_router

**Delegates to `strategy_router`:**
- `_on_candle_complete()` → calls `strategy_router.on_candle(symbol, candle, builder, token)`
- per-tick SM routing → calls `strategy_router.on_tick(symbol, ltp, ts)` only if `strategy_router.any_strategy_has_active_sm(symbol)`
- `on_order_postback()` → `strategy_router.on_order_postback(message)`
- `on_squareoff()` → `strategy_router.on_squareoff()`
- `on_market_open()` → also calls `strategy_router.on_market_open()`
- `get_stats()` → merges engine stats with `strategy_router.get_combined_stats()`

**Removes from coordinator:**
- `active_state_machines` (now inside IVBSStrategy)
- `second_spike_detector` (inside IVBSStrategy)
- `_on_candle_complete` IVBS logic
- `_handle_second_spike_entry`, `_handle_re_entry`, `_create_sm`
- `_signal_count` (now per-strategy)

---

### Phase 4: Update `runner.py`

#### [MODIFY] `engine/runner.py`
Change initialization sequence to:

```python
# Phase 4 new wiring in runner.py main()
from engine.core.strategy_router import StrategyRouter
from engine.strategies.ivbs.strategy import IVBSStrategy

strategy_router = StrategyRouter()
ivbs = IVBSStrategy(
    strategy_id="ivbs",
    redis_store=_redis_store,
    db_writer=_db_writer,
)
strategy_router.register(ivbs)

_coordinator = Coordinator(_redis_store, _db_writer, strategy_router=strategy_router)
```

Future strategy addition example (zero engine change):
```python
from engine.strategies.orb.strategy import ORBStrategy
orb = ORBStrategy("orb", redis_store=_redis_store, db_writer=_db_writer)
strategy_router.register(orb)
```

---

### Supporting Files

#### [MODIFY] `engine/store/db_writer.py`
Add an optional `strategy_id` parameter to `write_signal()` and `write_trade()` so trades can be tagged per-strategy. DB schema migration will add a `strategy_id VARCHAR` column to `signals` and `trades` tables.

#### [NEW] `alembic/versions/004_add_strategy_id_column.py`
Migration: add nullable `strategy_id` column to `signals` and `trades` tables (defaults to `"ivbs"` for existing rows).

#### [MODIFY] `tests/`
Update test imports to point to new locations. Shims make this low-priority during migration but should be cleaned up before marking complete.

---

## File Layout After Refactor

```
engine/
├── core/                           # NEW — base engine infrastructure
│   ├── __init__.py
│   ├── base_strategy.py            # ABC all strategies must implement
│   └── strategy_router.py          # Fan-out dispatcher
│
├── kite/                           # UNCHANGED
├── market/                         # UNCHANGED
├── orders/                         # UNCHANGED
├── risk/                           # UNCHANGED
├── store/                          # UNCHANGED
│
├── strategy/                       # LEGACY SHIMS during migration
│   ├── scanner.py                  # → re-exports from ivbs/scanner.py
│   ├── state_machine.py            # → re-exports from ivbs/state_machine.py
│   ├── second_spike_detector.py    # → re-exports
│   └── abandoned_setup_tracker.py  # → re-exports
│
├── strategies/                     # NEW — strategy plugins directory
│   ├── __init__.py
│   └── ivbs/                       # IVBS plugin (current strategy moved here)
│       ├── __init__.py
│       ├── strategy.py             # IVBSStrategy(BaseStrategy)
│       ├── scanner.py              # moved from engine/strategy/
│       ├── state_machine.py        # moved from engine/strategy/
│       ├── second_spike_detector.py
│       ├── abandoned_setup_tracker.py
│       └── config.py               # IVBS-only settings (extracted from main config)
│
└── runner.py                       # MODIFIED — wires strategy_router
```

---

## Verification Plan

### Phase 1 (Base layer)
- [ ] `python -m py_compile engine/core/base_strategy.py`
- [ ] `python -m py_compile engine/core/strategy_router.py`

### Phase 2 (IVBS plugin move)
- [ ] All existing unit tests pass: `.venv/Scripts/python -m pytest tests/unit/ -v`
- [ ] `py_compile` all moved files
- [ ] Shims resolve correctly: `python -c "from engine.strategy.scanner import ImpactCandle"`

### Phase 3 (Coordinator slim-down)
- [ ] Full unit test suite passes
- [ ] Integration tests pass (if any)
- [ ] Manual: start engine, verify pre-market setup logs IVBS strategy registered
- [ ] Manual: inject a fake tick and verify coordinator routes to IVBS strategy correctly

### Phase 4 (Runner wiring)
- [ ] Engine starts without errors: `python -m engine.runner` (dry run with `HISTORICAL_WARMUP_ENABLED=False`)
- [ ] Dashboard shows strategy stats correctly
- [ ] Order postback routing test: place a paper trade and verify fill routes back to IVBS SM

### Automated Tests
```bash
.venv\Scripts\python -m pytest tests/ -v --tb=short
```

### Manual Verification
- Confirm `engine:status` Redis key shows combined stats from strategy_router
- Confirm signal DB writes include `strategy_id = "ivbs"`
- Add a stub `NoOpStrategy(BaseStrategy)` and verify it can be registered alongside IVBS without interference

---

## Execution Order

| Phase | Scope | Risk | Estimated Files |
|-------|-------|------|-----------------|
| 1 | Create `engine/core/` package | Zero — pure additions | 3 new files |
| 2 | Move IVBS files to `engine/strategies/ivbs/` + shims | Low — shims preserve imports | 6 moves + 4 shims |
| 3 | Slim coordinator, wire strategy_router | Medium — core hot path change | 2 major edits |
| 4 | Update runner.py | Low — wiring only | 1 edit |
| 5 | DB migration for strategy_id column | Low | 1 new migration |
| 6 | Remove legacy shims + update tests | Low | Cleanup |
