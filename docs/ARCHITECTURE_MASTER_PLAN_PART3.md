# Algo-Trading Platform — Part 3: Verification, Future-Proof Architecture & Unified Roadmap

**Reads against:** `ARCHITECTURE_DEEP_DIVE.md` (ground truth of the current system), the Part 1 review (Tech-Stack Verdict & Phased Build Plan), and `ARCHITECTURE_DEEP_DIVE_PART2.md` (Common Engine for F&O + intraday). This document does three things: (1) verifies Part 2's decisions against the actual current architecture and against how production systems solve the same problems, (2) closes the gaps that stop *any future feature* — not just the ones already planned — from being added without surgery, and (3) merges Part 1's phases and Part 2's sprint backlog into one sequenced, dependency-aware roadmap.

---

## 1. Verification of Part 2's Decisions

Going through each Part 2 decision against the actual codebase (`ARCHITECTURE_DEEP_DIVE.md`) and against how institutional platforms solve the same problem.

| Part 2 decision | Verdict | Why |
|---|---|---|
| `MarketDataGateway` as sole owner of the WS connection, refcounted subscriptions | **Correct, keep.** | The current system already has a single `AsyncKiteTicker` — Part 2 doesn't add a new physical connection, it adds an ownership boundary around the one that exists. This is the same pattern IB/Bloomberg use (§3 of Part 2) and it's a pure extraction, zero behavior change. |
| Refcount on `(instrument_token, mode)`, pick cheapest-mode-that-satisfies-all | **Correct, but underspecified.** | Needs an explicit **upgrade-only** rule: if a second subscriber needs `full` on a token already held at `ltp`, the gateway must re-subscribe at `full` for *all* holders, never silently leave one subscriber under-served. Also needs a documented downgrade policy (or explicitly: never downgrade a live token mid-session, only on next refcount-driven resubscribe) to avoid a subtle bug where a strategy relying on OHLC suddenly gets `ltp`-only ticks because another strategy deactivated. |
| Hard alert near the 3,000-token ceiling | **Correct, keep.** | Matches the current system's existing pattern of hard state transitions (`IP_REJECTED`, `FATAL_DISCONNECT`) rather than a log line — consistent with the "crash-only, never silent" discipline already in `ARCHITECTURE_DEEP_DIVE.md` §9.3. |
| `CapitalAllocator` ledger + 10th pre-trade check | **Correct and important — but sequence it earlier than Part 2's backlog implies.** | Part 2 correctly identifies this as non-optional once >1 strategy is live, but its own backlog (§10) lists it as item 5, after several UI/OMS items. Given the current system already runs 2 live-capable strategies (IVBS + OptionsMomentum) sharing one Kite account, this should be pulled to the front of Phase 0 extension — see §8 below. Running two strategies against undivided margin today is the single largest latent risk in the current design that Part 2 correctly names but under-prioritizes. |
| `OrderGroup` for multi-leg orders | **Correct, keep — extend scope.** | Needed for F&O, but design it generically as "a set of orders that must be evaluated and reported as one unit," not an F&O-only concept. Equity strategies will eventually want basket entries too (e.g., a pairs-trade or a scale-in ladder) — see §3.4. |
| `EODSquareOffService` as a strategy-agnostic scheduled job | **Correct, keep — but it already partially exists.** | `ARCHITECTURE_DEEP_DIVE.md` §9.1 already runs `job_early_squareoff_check` (15:18) and `job_squareoff` (15:20) inside `engine/runner.py`. Part 2's contribution is making this **strategy-agnostic and independent of which strategies are currently registered**, i.e. it must square off positions even for a strategy that was hot-disabled or crashed. Verify on implementation that the existing scheduler jobs are refactored into this service rather than a parallel one being bolted on — two square-off code paths is exactly the kind of drift that causes a real incident. |
| Option-chain/Greeks as shared "capability nodes" | **Correct — and this is the single most important idea in Part 2 to generalize.** | Part 2 scopes this narrowly to F&O. The underlying idea — *a strategy declares a capability it needs by name, and a registry resolves it to an implementation* — is the correct extensibility mechanism for **every** kind of future addition, not just options analytics. See §3.1 (Capability Registry) below; this is where Part 2 should be extended rather than just adopted as-is. |
| One `orders`/`positions` table filtered by `strategy_id`, one UI blotter | **Correct, keep.** | Directly consistent with the current schema (`ARCHITECTURE_DEEP_DIVE.md` §8) which already has `strategy_id` on every table. This is a strict win over per-strategy stores. |
| Scoped UI panels declared via `ui.panels` in the manifest | **Correct in principle, incomplete as specified.** | The panel *type* list ("scanner_table," "option_chain," "metric_card") is hardcoded to what's known today. Without a registered panel-type system (§3.5), every new panel kind still requires a frontend code change — Part 2 says this explicitly ("a handful of reusable panel types") but doesn't give the extension mechanism for adding a new one later. Fixed below. |
| Redis Streams for `order_events` per Part 1, `strategy_id` as a field | **Correct, keep.** | Consistent with Part 1's Phase 0 item 4 and the existing Pub/Sub channel list (`ARCHITECTURE_DEEP_DIVE.md` §5.2) — this is additive, not a replacement of the live pub/sub feed the dashboard already uses. |

**Overall verdict on Part 2:** directionally correct and grounded in the real system (it correctly reuses existing components like the 9-step gate, the `strategies` table, and the existing scheduler rather than inventing parallel structures). Its main weakness is that every extensibility idea it introduces (capability nodes, UI panels, order groups) is **scoped to the specific feature that motivated it** (F&O, intraday) rather than generalized into a reusable registry pattern. That generalization is the subject of §3.

---

## 2. What Part 2 Doesn't Cover (Gaps for "Any Later Feature")

Part 2 answers "how do I add F&O and intraday cleanly." It doesn't answer "how do I add a feature class nobody has thought of yet without touching core code." The following are missing from both Part 1 and Part 2:

| Gap | Risk if unaddressed |
|---|---|
| No formal **plugin/registry mechanism** — capabilities, panel types, node types, brokers are each described as ad-hoc lists ("a handful of types") rather than a registered extension point | Every new kind of thing (not just new instance of an existing kind) requires touching shared core files — exactly the coupling the whole common-engine effort is meant to avoid |
| No **notification/alerting abstraction** | Part 2 §11 says "Telegram/SMS/email — whatever you already have wired up" — that's a hardcoded integration, not an interface. Adding a second channel (e.g. push notification, Discord) later means touching every call site |
| No **secrets/config layering strategy** beyond `.env` + Pydantic Settings | Fine solo today; becomes a real blocker the moment there's a staging environment (Part 1 already plans this) or a second broker with its own credentials |
| No **observability contract** (metrics/tracing) beyond structured logging | You'll want latency histograms (tick→signal→order), not just logs, once you're running multiple strategies and diagnosing slippage — bolting this on later means instrumenting every module again |
| No **schema/version policy** for `StrategyIR`, `StrategyManifest`, or event payloads | Part 1's IR has a `"version": 1` field but no stated migration rule — what happens when a v1 manifest is loaded by v2 code? Undefined today, will bite exactly when the agentic loop (Part 1 Phase 3) starts mutating manifests |
| No **risk-rule extensibility** — the 9 (soon 10) pre-trade checks are a fixed ordered list in one file | Every new risk rule (per-sector exposure caps, correlation limits, a rule specific to one strategy) means editing a shared, safety-critical file — the highest-risk place in the whole system to keep editing repeatedly |
| No **dependency-injection / service composition root** | Modules currently import concrete singletons (`redis_store`, `kite` client) directly. Fine at current scale; makes unit-testing new components and swapping implementations (e.g., a second broker, a mock data source for demos) harder than it needs to be |
| No **data source abstraction beyond Kite** | Today it's fine — Kite is the only source. Any future feature involving a second data source (news/sentiment, an alt-data feed, a second broker's market data) has nowhere to plug in without a parallel bespoke integration |
| No **API/contract versioning** for the dashboard REST/WS API | Not urgent solo, but the React Flow builder (Part 1 Phase 2) will be a second frontend consuming the same API — an accidental breaking change to a route today becomes a breaking change to two frontends later if this isn't versioned from the start |

None of these need to be *built* now — building them all now would be over-engineering a solo system that trades real capital and should stay simple. What's needed now is that **every one of these has a named seam reserved for it**, so adding the feature later is "implement this interface" rather than "refactor this subsystem." §3 defines those seams.

---

## 3. The Future-Proof Extensibility Layer

This is the addition this document makes on top of Parts 1 and 2: one consistent pattern — **the Capability/Provider Registry** — applied everywhere Part 2 said "a handful of types," so that adding a new *kind* of thing never means editing shared core files.

### 3.1 The pattern itself (applied five times below)

```python
# engine/core/registry.py — one generic mechanism, reused everywhere
class Registry(Generic[T]):
    def register(self, key: str, provider: T) -> None: ...
    def get(self, key: str) -> T: ...
    def list_keys(self) -> list[str]: ...

# Concrete registries, each populated at startup by a small "plugins.py"
capability_registry: Registry[CapabilityProvider] = Registry()
node_type_registry: Registry[NodeFactory] = Registry()
ui_panel_registry: Registry[PanelRenderer] = Registry()
broker_registry: Registry[BrokerAdapter] = Registry()
notification_registry: Registry[NotificationChannel] = Registry()
risk_rule_registry: Registry[RiskRule] = Registry()
```

This is the **Plugin pattern** (a.k.a. Provider/Extension Point), the same mechanism VS Code extensions, pytest plugins, and Django's app registry all use. A new implementation is added by writing one class and one registration line — never by editing the registry consumer.

### 3.2 Capability Registry (generalizes Part 2 §6.2)

Part 2 scoped "capabilities" to `option_chain`, `greeks`, `volume_sma`, `vix`. Generalize: **any** derived data a strategy might need (a technical indicator, an ML model's output, a sentiment score, a correlation matrix) is a `CapabilityProvider` registered under a string key and requested via the manifest's `requirements.capabilities` list (already the shape defined in Part 2 §5 — no schema change needed, just an open-ended key namespace instead of a fixed enum).

```python
class CapabilityProvider(Protocol):
    key: str
    def compute(self, ctx: MarketContext) -> Any: ...

capability_registry.register("volume_sma", VolumeSmaProvider())
capability_registry.register("option_chain", OptionChainProvider())
capability_registry.register("greeks", GreeksProvider())
# later, with zero changes to StrategyRouter or the manifest schema:
capability_registry.register("news_sentiment", NewsSentimentProvider())
capability_registry.register("iv_rank", IVRankProvider())
```

### 3.3 Node Type Registry (generalizes Part 1 §5, the Strategy IR)

The Strategy IR's `nodes[].type` field (`indicator.volume_sma`, `condition.gte`, `action.entry`) is currently just a string a hypothetical `RuleEngineStrategy` would `if/elif` over. Register node types instead:

```python
node_type_registry.register("indicator.volume_sma", VolumeSmaNode)
node_type_registry.register("condition.gte", GteConditionNode)
node_type_registry.register("action.entry", EntryActionNode)
# later, without touching RuleEngineStrategy:
node_type_registry.register("indicator.ml_score", MlScoreNode)      # ML-scored signal
node_type_registry.register("condition.correlation_lt", CorrelationNode)
node_type_registry.register("action.hedge_leg", HedgeLegActionNode)  # ties into OrderGroup, §3.4
```

`RuleEngineStrategy` becomes a fixed graph walker that resolves each node's `type` through the registry — this is the concrete mechanism that makes the drag-and-drop builder (Part 1 Phase 2) and the agentic loop (Part 1 Phase 3) able to introduce entirely new node kinds (a strategy built partly by an LLM proposing a new indicator combination) without changing the interpreter.

### 3.4 `OrderGroup` generalized (extends Part 2 §6.1)

Not F&O-specific. Any strategy that submits >1 order that must be evaluated/reported together (equity scale-in ladder, a pairs trade, an options spread, a hedge) uses the same `order_group_id` + `OrderGroup` construct. The pre-trade gate's group-aware check (Part 2 §6.1) becomes a general capability, not an F&O carve-out — this is one abstraction serving every future multi-order strategy shape.

### 3.5 UI Panel Type Registry (fixes the gap in Part 2 §9)

```python
ui_panel_registry.register("scanner_table", ScannerTablePanel)
ui_panel_registry.register("option_chain", OptionChainPanel)
ui_panel_registry.register("metric_card", MetricCardPanel)
# a new strategy class needing a new visualization later:
ui_panel_registry.register("correlation_heatmap", HeatmapPanel)
ui_panel_registry.register("graph_canvas", GraphCanvasPanel)  # reused directly by the Part 1 Phase 2 builder
```

The dashboard shell (Part 2 §9.2) queries `ui_panel_registry.list_keys()` it knows how to render and falls back to a generic JSON/table view for any panel type it doesn't recognize yet — so a strategy can ship a new panel type on the backend before the frontend has a bespoke renderer, degrading gracefully instead of breaking.

### 3.6 Broker & Notification Registries

`BrokerAdapter` (Part 1 §4/§6) and a new `NotificationChannel` interface both register the same way:

```python
class NotificationChannel(Protocol):
    def send(self, event: AlertEvent) -> None: ...

notification_registry.register("telegram", TelegramChannel())
notification_registry.register("sms", SmsChannel())
# later: notification_registry.register("discord", DiscordChannel())

broker_registry.register("zerodha", ZerodhaBrokerAdapter())
broker_registry.register("paper", PaperBrokerAdapter())
# later, if ever needed: broker_registry.register("upstox", UpstoxBrokerAdapter())
```

Alerts (WS disconnect, margin-approaching-limit, unhedged-leg, circuit-breaker-tripped — all already identified in Part 2 §11) are raised as a typed `AlertEvent` and fanned out to every registered channel, rather than each alert site calling a specific Telegram function directly.

### 3.7 Risk Rule Chain (fixes the gap: pre-trade checks as a monolith)

Convert the 9 (soon 10+) sequential checks in `pre_trade_checks.py` from an ordered if-chain into a **Chain of Responsibility** of `RiskRule` objects, each independently testable and independently addable:

```python
class RiskRule(Protocol):
    name: str
    def check(self, ctx: OrderContext) -> RiskResult:  # PASS / BLOCK(reason)
        ...

risk_pipeline = [
    CircuitBreakerRule(), ConcurrentPositionsRule(), MarketHoursRule(),
    EntryCutoffRule(), RiskPerShareRule(), QuantityRule(),
    MarginAvailabilityRule(), PeakMarginBufferRule(), SmaWarmupRule(),
    CapitalAllocatorRule(),      # the new 10th check from Part 2 §4.5
]
# future rules — sector exposure cap, correlation limit, a strategy-specific rule —
# are appended here, each in its own file, each independently unit-tested,
# with zero edits to the rules that already exist.
```

This is the **Specification pattern** combined with Chain of Responsibility — standard in institutional risk engines for exactly this reason: the risk pipeline is the most safety-critical code in the system, so it should be the *easiest* place to add a rule without touching existing ones, not the hardest.

### 3.8 Config, Secrets & Observability Seams (reserve now, build when needed)

- **Config**: keep Pydantic Settings for env-level config, but formalize the **layering order** now — `env vars → .env → StrategyManifest DB row → runtime feature-flag override` — so a future staging environment or a feature flag system slots into an already-defined precedence instead of an ad-hoc override.
- **Secrets**: define a `SecretsProvider` interface today with one implementation (`EnvFileSecretsProvider`); nothing else changes now, but a future move to a real vault (or a second broker's separate credentials) is a second implementation, not a rewrite of every place `os.environ` is read directly.
- **Observability**: adopt structured logging fields consistently now (already true — `structlog` is in place) and reserve a `metrics.py` seam (even as a no-op today) for counters/histograms (`order_latency_ms`, `tick_processing_lag_ms`, `signal_to_order_ms`) so wiring in Prometheus/OpenTelemetry later is additive instrumentation, not a retrofit.

---

## 4. Design Patterns Catalog — What's Used Where, and Why

Explicitly naming these matters: it's what lets a future contributor (including a future agentic loop proposing code) recognize *which* pattern to extend rather than inventing a new shape each time.

| Pattern | Where it's applied | Purpose |
|---|---|---|
| **Ports & Adapters (Hexagonal Architecture)** | Whole-system shape: `BaseStrategy`, `BrokerAdapter`, `OrderGateway`, `MarketDataGateway` are all ports; Zerodha-specific code is the one adapter implementing them | Domain logic (strategies, risk, sizing) never depends on Kite's SDK shapes directly — a second broker or a mock is a new adapter, not a domain change |
| **Strategy pattern** | `BaseStrategy` subclasses (`IVBSStrategy`, `OptionsMomentumStrategy`, future `RuleEngineStrategy`) | Interchangeable algorithms behind one interface, dispatched by `StrategyRouter` |
| **Plugin/Registry (Extension Point)** | §3.1–3.6: capabilities, node types, UI panels, brokers, notification channels, risk rules | The mechanism that makes "any later feature" additive instead of invasive |
| **Chain of Responsibility + Specification** | Pre-trade risk pipeline (§3.7) | Ordered, independently-composable safety checks; the correct shape for a system where "don't break what already works" is non-negotiable |
| **Facade** | `OrderService` as the single entry point for order placement/modification/cancellation across paper and live modes | Strategies and the risk gate depend on one simple interface, not on `kiteconnect` internals, retry logic, or cost calculation directly |
| **Gateway** | `MarketDataGateway` (Part 2 §4.1), `OrderGateway` | Encapsulates and centralizes all traffic to an external system behind one owner, enabling refcounting, rate-limiting, and dedup that would be impossible if every caller talked to Kite directly |
| **Repository** | SQLAlchemy models + a thin repository layer per aggregate (`TradeRepository`, `SignalRepository`) | Isolates business logic from persistence details; makes the SQLite→Postgres migration (Part 1 §Phase 0) a swap of implementation, not a rewrite of call sites |
| **Event Sourcing (partial)** | `signal_snapshots`, `order_events` as append-only logs of what happened, with current state derivable from them | Already present in the current schema (`ARCHITECTURE_DEEP_DIVE.md` §8) — this is exactly what gives you the audit trail an agentic loop's proposals need to be reviewable/reversible |
| **Outbox pattern** | Redis Streams for `order_events`/`state_changes` (Part 1 Phase 0 item 4, Part 2 §8) alongside the DB write | Guarantees a durable, replayable record of every state change independent of whether a downstream consumer (dashboard, future analytics, future agent) was up at the time |
| **Observer / Pub-Sub** | Redis Pub/Sub channels (`pub:signals`, `pub:orders`, etc.) feeding the dashboard's WS push workers | Decouples the engine (publisher) from any number of consumers (subscribers) without either knowing about the other |
| **Bulkhead** | `StrategyRouter`'s per-strategy try/except isolation | One strategy's fault can't sink another — already correctly implemented, keep as-is through every future phase |
| **Circuit Breaker** | `risk/circuit_breaker.py` (daily drawdown kill switch) — and conceptually the WS `on_fatal_disconnect` handling | Stops the system from continuing to do damage once a failure threshold is crossed, rather than degrading silently |
| **Saga / Process Manager** | `EODSquareOffService`, the expiry-rollover job (Part 2 §6.3), `OrderGroup` multi-leg fill tracking | Coordinates a multi-step process that must complete correctly (or fail safely) across time, independent of any single strategy's own logic |
| **Anti-Corruption Layer** | `InstrumentMaster`, `Instrument` dataclass (`engine/core/instrument.py`) | Kite's raw instrument/tick shapes are translated into the platform's own domain types at the boundary, so a future second broker's different shapes don't leak into strategy code |
| **CQRS-lite** | Write path (`OrderService` → DB) vs. read path (`AnalyticsService` materialized views, dashboard REST reads) | Keeps the hot order-placement path free of analytics query overhead, and lets the read side evolve (new materialized views, new metrics) independently |
| **Feature Toggle** | `enabled` flag on `StrategyManifest`, paper/live `trade_mode` | Ships new strategies/features dark, cuts over via config rather than a deploy, and is the mechanism that makes the strangler-fig migration (Part 1 §Phase 0) safe |

---

## 5. Unified Phased Roadmap

Merges Part 1's Phase 0–4 and Part 2's sprint backlog into one sequenced plan. Every phase preserves the existing strangler-fig discipline: **zero behavior change to live trading logic until a shadow-run parity check passes**, per Part 1 §8 and Part 2 §11.

### Phase 0 — Stabilize + Extensibility Seams (3–4 sprints)
*Goal: the refactor that makes every later phase additive instead of invasive.*
1. `BrokerAdapter` interface + `ZerodhaBrokerAdapter`/`PaperBrokerAdapter` (Part 1 §6.1) — pure extraction.
2. **`CapitalAllocator` ledger + 10th pre-trade check** (pulled forward from Part 2's later backlog per §1 above) — do this before touching anything else that adds strategies, since two live strategies already share undivided margin today.
3. Convert `pre_trade_checks.py` into the `RiskRule` chain (§3.7) — same 9 checks, same order, same behavior; only the *shape* changes, verified by an exact-parity test.
4. Introduce the generic `Registry` (§3.1) and populate the capability, broker, and notification registries with today's implementations only (`volume_sma`, `zerodha`/`paper`, `telegram`/`sms`) — no new features yet, just the seam.
5. SQLite → PostgreSQL migration (Part 1 §Phase 0.2), via a `Repository` layer so call sites don't change.
6. `StrategyManifest` DB model + `requirements`/`capital`/`risk` blocks (Part 1 §5 + Part 2 §5 schema, merged) — seed from existing `config.yaml` files.
7. Redis Streams (or Postgres outbox) for `order_events`/`state_changes` alongside existing pub/sub.
8. Containerize (Docker Compose: engine, dashboard, redis, postgres).
9. Delete the legacy `engine/strategy/` shim package.
10. Backfill tests on everything touched, plus a new **shadow-run harness** (refactored engine vs. current engine, diffed daily).

**Definition of done:** IVBS and OptionsMomentum run unchanged in paper mode for ≥5 sessions with identical signals/fills to the pre-refactor engine, *and* the two strategies now have separately tracked, non-overlapping margin allocations.

### Phase 1 — Common Engine Core (2–3 sprints)
*Goal: the shared infrastructure every future strategy — F&O, intraday, or otherwise — sits on.*
1. `MarketDataGateway` extraction with refcounted subscribe/unsubscribe (Part 2 §4.1) — wraps the existing `AsyncKiteTicker`, zero new connection.
2. `InstrumentMaster` (Part 2 §4.2) — symbol/token/lot-size/expiry lookups, option-chain builder, freeze-quantity source.
3. `HistoricalDataService` with a token-bucket rate limiter + cache (Part 2 §4.3).
4. `CandleAggregator` reading off the shared tick stream (Part 2 §4.4).
5. `EODSquareOffService` — refactor the existing 15:18/15:20 scheduler jobs into this strategy-agnostic service (verify no parallel code path emerges, per §1 above).
6. `OrderGroup` as a general multi-order construct (§3.4), not F&O-scoped.
7. `AnalyticsService` materialized views with `strategy_id` as a filter dimension (Part 1 Phase 1.2 + Part 2 §4.8, merged).
8. Node-type registry (§3.3) + a minimal `RuleEngineStrategy` interpreter, validated by hand-encoding IVBS's simplest rule as a graph and diffing backtest output against the coded version (Part 1 Phase 1.3).
9. Second and third hand-written strategies added purely to validate that the common engine generalizes (Part 1 Phase 1.1) — do this *using* the new `requirements`/`capabilities` contract, not the old direct-subscribe pattern, so it also validates §3.2.

**Definition of done:** a new strategy can be added by (a) writing a `BaseStrategy` subclass or IR graph, (b) writing a manifest with `requirements`, and (c) nothing else — no edits to `MarketDataGateway`, `OrderService`, or the risk pipeline.

### Phase 2 — F&O + Intraday Feature Completeness (2–3 sprints)
1. Multi-leg order support in `OrderService` via `OrderGroup` (Part 2 §6.1).
2. Option-chain/Greeks as registered capabilities (§3.2), consumed by any strategy declaring them — not reimplemented per strategy.
3. Expiry rollover as a scheduled common-engine job (Part 2 §6.3).
4. Freeze-quantity-aware order splitting in `OrderService` (Part 2 §6.4).
5. MIS product-type enforcement + circuit-limit-aware pre-trade rule for intraday equity (Part 2 §7), added as a new `RiskRule` — proof that §3.7's extensibility works end to end.
6. First real F&O strategy and first additional intraday equity strategy built against all of the above.

### Phase 3 — Scoped UI + Drag-and-Drop Builder (3–5 sprints)
1. `ui_panel_registry` (§3.5) + generic panel-type renderer in the existing vanilla-JS dashboard, sourced from each enabled manifest's `ui.panels` block (Part 2 §9).
2. Orders/Positions/Analytics/Risk as common, strategy-filterable screens (Part 2 §8).
3. New React Flow node-graph frontend (Part 1 Phase 2), emitting/consuming the same `StrategyIR` JSON — no new backend execution path, since Phase 1 already built the interpreter.
4. Canvas node palette is populated directly from `node_type_registry.list_keys()` (§3.3) — the builder UI never hardcodes a node list.
5. Every graph-built strategy passes through the same backtest engine and the same `RiskRule` chain as coded strategies before going live — no shortcuts.

### Phase 4 — Agentic Strategy Loop (4+ sprints, R&D budget, doesn't block Phases 0–3)
1. Agent proposes `StrategyIR` mutations only — never raw broker calls, never a manifest's `capital.allocated` value (that stays human-set, enforced by `CapitalAllocatorRule`).
2. Every proposal evaluated only through the existing backtest engine + Phase 1's analytics layer.
3. Explicit human-approval gates: backtest → paper, and separately paper → live.
4. Full lineage logged in `StrategyManifest` version history (which agent run produced which version) — this is why §2's "no schema/version policy" gap must be closed in Phase 0, before this phase needs it.

### Phase 5 — Continuous Analysis, Drift Monitoring & Hardening (ongoing)
1. Live-vs-backtest parity checks, slippage/fill-rate drift alerting, strategy retirement workflow (Part 1 Phase 4).
2. Reliability checklist items from Part 2 §11 not yet covered above: WS reconnect/heartbeat alerting, subscription-ceiling hard alert, a standalone kill switch endpoint separate from EOD square-off, margin cushion buffer in `CapitalAllocator`, unhedged-leg alerting for order groups.
3. Observability build-out using the `metrics.py` seam reserved in Phase 0 (§3.8) — latency histograms, dashboards, alerting thresholds.
4. Secrets provider upgrade (§3.8) if/when a second broker or a staging environment makes `.env`-only secrets insufficient.

---

## 6. Architecture Decision Records to Write

Per Part 1 §8's ADR discipline, extended with the decisions this document adds:

1. Broker adapter interface shape (Part 1)
2. Strategy IR schema + versioning/migration policy (this document, §2)
3. DB engine choice: Postgres (Part 1)
4. `CapitalAllocator` ledger design and margin-cushion policy (Part 2 + this document's re-sequencing)
5. Registry pattern adoption and initial set of registries (this document, §3)
6. Risk rule chain refactor — confirming exact-parity with the original 9-check sequence (this document, §3.7)
7. Secrets provider interface and initial implementation (this document, §3.8)
8. Agentic-loop approval-gate design (Part 1 Phase 3, informed by §2's versioning gap)

---

## 7. Guardrail: Don't Over-Build the Extensibility Layer Itself

Every registry in §3 should be introduced **only with its real, current implementations** (§Phase 0 item 4) — not pre-populated with speculative future providers. The value of the Plugin pattern here is that the *seam* costs almost nothing to add now (a registry is a dict with a register/get method), while the seam being *absent* is what costs real rework later. But populating it with hypothetical future node types, brokers, or panels before there's a second real instance of any of them is the classic premature-abstraction mistake (violates the Rule of Three) — resist that even though the seam itself is cheap. Concretely: build the registry mechanism in Phase 0, but only Phase 1–3 should be adding new *entries* to it, driven by real features, not speculative ones.

---

## 8. Summary

Part 2's common-engine design is sound and correctly reuses the existing architecture rather than replacing it. Its two real weaknesses — under-prioritizing the `CapitalAllocator` given two strategies already share live margin today, and scoping every extensibility idea (capabilities, panels, order groups) narrowly to the feature that motivated it — are both fixed here by (a) resequencing the roadmap so capital allocation lands in Phase 0, and (b) generalizing every one-off extension point into the same Registry pattern, so that F&O, intraday, the drag-and-drop builder, and the agentic loop all consume — and any unforeseen future feature can also consume — one consistent mechanism instead of four bespoke ones.
