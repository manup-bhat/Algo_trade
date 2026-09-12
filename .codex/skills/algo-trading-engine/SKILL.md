---
name: algo-trading-engine
description: >
  Authoritative guide to THIS repository's multi-strategy NSE/F&O trading engine
  (IVBS platform). Use when: adding a new trading strategy (equity, futures, or
  options), extending the engine without touching its core, implementing the
  BaseStrategy plugin contract, wiring a strategy into the StrategyRouter/runner,
  writing a per-strategy config.yaml, resolving an option chain / ATM strike /
  expiry, lot-based F&O position sizing, placing asset-aware Kite orders
  (NSE/NFO, MIS/NRML), backtesting or replaying a strategy, validating in PAPER
  before going LIVE, understanding real-trading idempotency guards, the editable
  watchlist hot-reload, or running the test suite. Trigger phrases: "add a
  strategy", "new strategy", "options strategy", "futures strategy", "plug in a
  strategy", "how does the engine work", "backtest my strategy", "per-strategy
  config", "go live checklist", "paper trade validation", "option chain",
  "position sizing lots". DO NOT USE FOR: unrelated codebases, generic Python
  questions, or non-trading features.
---

# Algo Trading Engine — Developer Guide

This repo is a **multi-strategy, multi-asset (equity + F&O) intraday trading engine**
for Zerodha Kite, with a FastAPI dashboard. The core design goal: **add a new
strategy by writing one plugin package — never edit the engine core.**

## 1. Architecture at a glance

Two processes talk over **Redis** (never in-process across the boundary):

- **Engine** (`engine/`, run as `python -m engine.runner`) — connects to Kite,
  builds 1-min candles, and drives strategies. Runs as a **child subprocess** of
  the dashboard (`app/main.py` → `subprocess.Popen`).
- **Dashboard** (`app/`, FastAPI) — REST + WebSocket UI (`app/static/dashboard.html`).
  It reads/writes Redis and signals the engine (auth, TRADE_MODE, watchlist edits).

Inside the engine, event flow is a strict funnel:

```
Kite WS ticks ─▶ AsyncKiteTicker ─▶ Coordinator ─▶ StrategyRouter ─▶ Strategy plugins
                  (candle build)     (PURE data       (fan-out +        (all decisions:
                                       router)          isolation)        signals/orders)
```

- **Coordinator** (`engine/strategy/coordinator.py`) is a **pure data router**:
  candle building, Nifty/VIX market gate, dashboard publish, order reconcile. It
  makes **no** strategy decisions.
- **StrategyRouter** (`engine/core/strategy_router.py`) fans every lifecycle event
  out to each registered strategy, wrapping every call in try/except so **one
  strategy's exception can never crash the engine or a sibling**.
- **BaseStrategy** (`engine/core/base_strategy.py`) is the plugin contract. All
  trading logic lives behind it.

### Key directories

| Path | Purpose |
|------|---------|
| `engine/core/` | Framework: `base_strategy.py`, `strategy_router.py`, `instrument.py`, `strategy_config.py`, `order_gateway.py` |
| `engine/strategies/<id>/` | One package per strategy: `strategy.py` + `config.yaml` |
| `engine/strategy/` | Engine internals: `coordinator.py`, plus IVBS leaf modules (scanner, state_machine, second_spike_detector, abandoned_setup_tracker) |
| `engine/market/` | `candle_builder.py`, `universe.py`, `watchlist.py`, `option_chain.py`, `calendar.py`, `historical_warmup.py` |
| `engine/orders/` | `order_service.py`, `order_tracker.py`, `fill_timeout.py`, `cost_calculator.py` |
| `engine/risk/` | `position_sizer.py`, `pre_trade_checks.py`, `circuit_breaker.py`, `margin_tracker.py` |
| `engine/store/` | `redis_store.py`, `db_writer.py`, `sma_file_store.py` |
| `engine/backtest/` | `engine.py`, `metrics.py`, `portfolio.py`, `sim_broker.py` |
| `engine/kite/` | `client.py`, `ticker.py`, `instruments.py`, `auth.py` |

Reference implementations to copy from:
- **Equity** — `engine/strategies/ivbs/strategy.py` (`IVBSStrategy`, the production strategy)
- **Options** — `engine/strategies/options_momentum/strategy.py` (`OptionsMomentumStrategy`, index-options momentum buyer)

## 2. Add a new strategy (the only workflow you need)

Adding a strategy is **4 steps and zero engine-core edits**.

### Step 1 — Create the package

```
engine/strategies/<strategy_id>/
    __init__.py        # exports your class
    strategy.py        # subclass of BaseStrategy
    config.yaml        # per-strategy config (id MUST equal <strategy_id>)
```

> **Critical:** `strategy_id` passed to the constructor **must equal the directory
> name** — `load_strategy_config(strategy_id)` maps the id straight to
> `engine/strategies/<strategy_id>/config.yaml`. A mismatch silently loads `{}`.

### Step 2 — Implement `BaseStrategy`

```python
# engine/strategies/orb/strategy.py
from __future__ import annotations
from typing import Any
import structlog
from engine.core.base_strategy import BaseStrategy

log = structlog.get_logger(__name__)


class ORBStrategy(BaseStrategy):
    """Opening-range breakout (skeleton). Copy IVBS/options_momentum for a full impl."""

    def __init__(self, strategy_id, redis_store, db_writer):
        super().__init__(strategy_id, redis_store, db_writer)
        # self.config is already loaded from config.yaml by the base class.
        self._lookback = int(self.config.get("signal", {}).get("lookback_candles", 15))
        self._active: dict[str, Any] = {}   # symbol -> your per-symbol state

    # ── Required hooks ──────────────────────────────────────────────
    async def on_market_open(self) -> None:
        self._active.clear()                # fresh state each session (09:15)

    async def on_candle(self, symbol, candle, builder, instrument_token) -> None:
        if not self.new_entries_enabled:    # STOP/START gate — respect it
            return
        # ... your entry logic; place orders via self._order_service (see §5) ...

    async def on_order_postback(self, message: dict[str, Any]) -> None:
        # MUST be idempotent and ignore orders this strategy does not own (see §6).
        ...

    async def on_squareoff(self) -> None:
        # 15:20 — force-close every position this strategy owns.
        self._active.clear()

    def get_stats(self) -> dict[str, Any]:
        return {"active": len(self._active)}

    def is_symbol_active(self, symbol: str) -> bool:
        return symbol in self._active       # drives per-tick forwarding

    # ── Optional hooks (safe no-op defaults in the base class) ──────
    async def on_tick(self, symbol, ltp, exchange_ts) -> None: ...
    async def on_session_end(self) -> None: ...
    async def on_fatal_disconnect(self) -> None:   # default = on_squareoff()
        await self.on_squareoff()
```

`__init__.py`:
```python
from engine.strategies.orb.strategy import ORBStrategy
__all__ = ["ORBStrategy"]
```

### Step 3 — Add `config.yaml`

See the annotated example in §4. Keep `enabled: false` until PAPER-validated.

### Step 4 — Register in `runner.py` (opt-in)

In `engine/runner.py` where the router is built (search for `StrategyRouter()`):

```python
_strategy_router = StrategyRouter()
_strategy_router.register(IVBSStrategy("ivbs", _redis_store, _db_writer))

# opt-in: only register when its config enables it
if load_strategy_config("orb").get("enabled"):
    from engine.strategies.orb.strategy import ORBStrategy
    _strategy_router.register(ORBStrategy("orb", _redis_store, _db_writer))

_coordinator = Coordinator(_redis_store, _db_writer, strategy_router=_strategy_router)
```

That is the **entire** integration. The Coordinator, ticker, order tracker, DB,
and dashboard now drive your strategy automatically.

## 3. The `BaseStrategy` lifecycle contract

| Hook | When | Must do |
|------|------|---------|
| `inject_execution(order_service, order_tracker, fill_timeout_manager, kite)` | once, after auth | wired by the router — don't call yourself |
| `on_market_open()` | 09:15 | reset per-session state |
| `on_candle(symbol, candle, builder, instrument_token)` | every completed 1-min candle, every universe symbol | scan / manage; entry logic here |
| `on_tick(symbol, ltp, exchange_ts)` | per tick, **only** for symbols where `is_symbol_active(symbol)` is True | tight SL/target management |
| `on_order_postback(message)` | raw Kite order update | **idempotent**; ignore foreign orders |
| `on_squareoff()` | 15:20 | force-close everything you own |
| `on_session_end()` | 15:25 | optional persistence (no-op default) |
| `on_fatal_disconnect()` | WS reconnect exhausted | emergency close (defaults to `on_squareoff()`) |
| `get_stats()` | dashboard/logging | JSON-serializable dict |
| `is_symbol_active(symbol)` | router tick routing | True while you hold/manage the symbol |

Rules:
- **Never import another strategy.** Plugins are isolated.
- `self.config` is loaded for you; `self._order_service/_order_tracker/_fill_timeout/_kite`
  are `None` until `inject_execution` runs (they stay `None` in warmup).
- Always honour `self.new_entries_enabled` before a fresh entry (STOP/START control).

## 4. Per-strategy config (`config.yaml`)

`load_strategy_config(strategy_id)` (`engine/core/strategy_config.py`) reads
`engine/strategies/<id>/config.yaml` into `self.config`. It is **fail-soft** — a
missing file, missing PyYAML, or parse error returns `{}`, so always `.get(...)`
with defaults.

Annotated example (from `engine/strategies/options_momentum/config.yaml`):

```yaml
id: options_momentum          # MUST equal the directory name
name: Index Options Momentum
asset_class: OPTION           # EQUITY | FUTURE | OPTION
enabled: false                # opt-in; flip to true only after PAPER validation

underlying: NIFTY             # Kite instrument `name` for chain lookup
underlying_symbol: "NIFTY 50" # symbol whose 1-min candles drive the signal
product: MIS                  # MIS (intraday) | NRML (carry)

signal:
  lookback_candles: 5
risk:
  stop_loss_pct: 30
  target_pct: 60
  max_lots: 5
  max_premium_exposure_pct: 10
  max_positions: 1
timing:
  entry_cutoff: "14:30"       # no new entries after this IST time
```

> IVBS currently still reads most tunables from `app/core/config.py` settings; its
> `config.yaml` mirrors them. New strategies should be **config-authoritative**.

## 5. F&O / multi-asset

The asset abstraction lives in `engine/core/instrument.py`:

- Enums: `AssetClass` (EQUITY/FUTURE/OPTION), `Exchange` (NSE/BSE/NFO/CDS/BCD/MCX),
  `Product` (CNC/NRML/MIS/MTF), `OptionType` (CE/PE).
- `Instrument` — frozen dataclass with `instrument_token, tradingsymbol, exchange,
  asset_class, tick_size, lot_size, underlying, expiry, strike, option_type, segment`
  and helpers (`is_option/is_future/is_derivative`, `default_intraday_product`, etc.).

**Option chain** — `engine/market/option_chain.py` `OptionChainResolver`
(load it from the NFO dump via `engine.kite.instruments.load_fno_instruments_async`):

```python
resolver.load(nfo_dump)
exp    = resolver.nearest_expiry("NIFTY")                     # date | None
ce     = resolver.atm_option("NIFTY", spot, OptionType.CE)    # Instrument | None
strike = resolver.atm_strike("NIFTY", spot, exp)              # nearest listed strike
fut    = resolver.future("NIFTY")                             # nearest-expiry future
```

**Lot-based sizing** — `engine/risk/position_sizer.py`:

```python
qty = compute_lots(
    capital, entry_price, stop_loss, lot_size,
    risk_pct=None,                     # defaults to settings.RISK_PER_TRADE_PCT
    max_lots=5,
    max_premium_exposure_pct=10,       # premium outlay cap as % of capital
)   # returns lots*lot_size, or 0 if a single lot can't be funded within limits
```

**Asset-aware orders** — `engine/orders/order_service.py` `place_entry(...)` takes
`exchange` / `product` / `tag` (default `NSE` / `MIS` / IVBS tag → equity path
unchanged). For F&O pass `Exchange.NFO` and `Product.NRML` (carry) or `MIS`
(intraday). The `tag` should identify the owning strategy.

## 6. Real-trading safety (read before going LIVE)

- **Modes:** `TRADE_MODE` = `PAPER` | `LIVE` | `SIMULTANEOUS`; legacy `PAPER_TRADE`
  bool kept in sync. The dashboard can override at runtime via Redis; the engine's
  `_poll_config()` applies it every 5s. **Always validate in PAPER first.**
- **Idempotency (already enforced — mirror it in your strategy):**
  - `state_machine.on_order_filled` guards `if self.position is not None or
    self._fill_in_progress: return` set **before any await** — prevents double SL /
    double margin block on a racing postback + reconcile.
  - `order_tracker.on_postback` dedups on `(order_id, status)` (claim-first).
  - Partial fills: CANCELLED/REJECTED with `filled_quantity > 0` routes to
    `on_order_filled` for the filled portion.
- `on_order_postback` **must** ignore orders you don't own and be safe to call twice.
- Recovery: 5-min reconcile loop + orphan check + Redis NX exit lock already exist.

### Go-live checklist
1. `enabled: true` only after a full PAPER session behaves correctly.
2. Confirm lot size, exchange, product, expiry, and `entry_cutoff` for the instrument.
3. Verify `compute_lots` caps (risk %, max_lots, premium exposure) match your risk.
4. Watch the dashboard reconcile counter rising; confirm SL/target place once.
5. Start with `max_positions: 1` and a small capital cap.

## 7. Backtesting / replay

`engine/backtest/engine.py` runs your **real** strategy unchanged (environment
parity — same router + plugin, a `SimBroker`, and a fake Redis):

```python
from engine.backtest.engine import BacktestEngine

def build(redis, db):                       # factory: return your strategy instances
    return [ORBStrategy("orb", redis, db)]

bt = BacktestEngine(build, starting_capital=500_000)
summary = await bt.run(candles, warmup_volumes=[...])   # single-symbol convenience
# or drive manually: await bt.market_open(); await bt.feed_candle(c); await bt.squareoff()
print(summary)   # net_pnl, win_rate, profit_factor, expectancy, max_drawdown, sharpe...
```

`feed_candle` also simulates an intrabar low→high tick path so SL/target trigger
realistically. Metrics live in `engine/backtest/metrics.py::compute_metrics`.

## 8. Editable watchlist (hot-reload)

The dashboard edits the watchlist (`app/static/dashboard.html` modal →
`POST/DELETE /api/v1/universe/symbols`), which persists `universe.txt` and calls
`RedisStore.set_pending_watchlist(...)`. The engine's `_poll_config()` consumes it
and calls `Coordinator.apply_watchlist(symbols, resolve)` to add/remove
`CandleBuilder`s + WS subscriptions live — **never removing a symbol that a
strategy still holds** (`any_strategy_has_active_symbol`). No restart needed.

## 9. Testing & commands

Environment (Windows, from repo root):

```powershell
# create/activate venv once (only Python 3.14 available here; project targets 3.12)
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt pytest pytest-asyncio httpx "fakeredis[aioredis]"

# run the whole suite (must stay green)
.\.venv\Scripts\python.exe -m pytest tests -q
```

- `pip install -e .` is **broken** (hatchling has no package decl); run from repo
  root so `engine`/`app` are importable.
- `tests/conftest.py` forces `PAPER_TRADE=true`, an in-memory SQLite DB, and
  `asyncio_mode=auto`; it provides `fake_redis` and `redis_store` (a `RedisStore`
  backed by FakeRedis) fixtures. Dashboard tests call endpoint functions directly
  after `dashboard_router.set_dependencies(redis_store, None)`.

Write tests for every new strategy:
- Unit — put decision logic under test (`tests/unit/test_<id>.py`); use the
  `redis_store` fixture and a paper `OrderService`.
- Backtest — a small candle series through `BacktestEngine` proving ≥1 trade + metrics.

## 10. Guardrails (do / don't)

- ✅ Add a strategy = new package + register line. **Don't** edit Coordinator/router.
- ✅ `strategy_id` == directory name == `config.yaml` `id`.
- ✅ `.get(..., default)` on `self.config` (it may be `{}`).
- ✅ Idempotent `on_order_postback`; ignore foreign orders.
- ✅ PAPER-validate before `enabled: true`.
- ❌ Never import one strategy from another.
- ❌ Never assume execution deps are non-None during warmup.
- ❌ Never block the engine event loop with sync I/O in a hook.
