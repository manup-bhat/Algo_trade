# Algo-Trading Platform — Part 2: Common Engine, Zero-Redundant Data, F&O + Intraday, Scoped UI

**Follows on from:** `ARCHITECTURE_DEEP_DIVE.md`. That document established the seams (broker adapter, Strategy IR, Postgres, Streams) and a 4-phase roadmap. This document goes deep on what you actually asked to build *right now*: F&O strategies, intraday equity strategies, and a **common engine** that serves N strategies without any of them fighting over data, margin, or screen real estate — while staying reliable enough to trust with real capital, with no product/multi-tenant concerns to slow it down.

---

## 1. The real problem, stated precisely

Adding "more strategies" is not the hard part — `StrategyRouter` already fault-isolates that. The hard part is that **three resources are shared across every strategy you'll ever add, and none of your current design treats them as shared resources with an owner**:

| Shared resource | What happens without an owner | What happens with one |
|---|---|---|
| **Market data** (WS ticks, historical candles, option chain) | Every strategy subscribes to what it wants → duplicate subscriptions, wasted bandwidth, and you silently hit Zerodha's hard subscription ceiling once you add a scanner or an options strategy | One gateway owns the connection; strategies *declare* what they need; the gateway subscribes only to the union, unsubscribes what nobody needs anymore |
| **Margin / capital** | Two strategies can each independently think they have room for a trade, and both fire — the account doesn't have two accounts | One ledger tracks allocated-vs-free margin per strategy; the pre-trade gate checks against it before either order goes out |
| **Screen space / orders view** | Every strategy tries to own its own page, or worse, they all write to one undifferentiated blob | One Orders/Positions surface, strategy as a filter facet; each strategy separately owns a small scoped panel for what's unique to it (scanner hits, option-chain view) |

Everything below is the concrete design for these three, plus what changes specifically for F&O and intraday equity.

---

## 2. Why "just subscribe to everything" doesn't work on Kite — this is a hard constraint, not a preference

This matters more than it looks, because it turns "nice to have — avoid redundant data" into "must have — or your platform silently stops receiving ticks."

- KiteTicker allows **subscribe / unsubscribe / setMode per instrument token at runtime** — this is a first-class part of the API, not a workaround. Modes are `ltp` (price only), `quote` (price + OHLC + volume), `full` (market depth) — you choose per instrument, and heavier modes cost more bandwidth per tick.
- Each WebSocket connection is capped at **3,000 instrument tokens**, and Zerodha allows **up to 3 connections per API key** (≈9,000 tokens max, and going near that ceiling is explicitly discouraged by Zerodha as bot-like usage). One NIFTY monthly option chain alone can be 80–150+ live strikes across CE/PE; a scanner strategy watching the F&O universe can burn through hundreds more. If every strategy independently subscribes to "its" instruments with no dedup, you will hit this ceiling far sooner than you'd expect, with a **silent partial failure** (excess tokens beyond 3,000 on a connection get rejected while the connection keeps running) — the worst kind of bug for a live-capital system, because nothing crashes, you just stop seeing some ticks.
- The REST API (orders, quotes, instrument margins) is rate-limited to **~3 requests/second**, and historical-data endpoints explicitly do **not** support bulk fetch — Zerodha's own guidance is *"generate candles at your end using the WebSocket API"* rather than re-polling historical data. This is exactly why a shared `CandleAggregator` (§4.4) isn't a nice-to-have — hitting historical data per-strategy, per-symbol, on demand will rate-limit you in production.
- Order placement is capped at **~200/minute at the API level**, with a separate RMS-level daily cap on MIS/BO/CO order count. Multi-leg F&O strategies (§6) that place 2–4 orders per signal need to respect this budget too, and it's exactly the kind of thing a shared `OrderService` should be tracking centrally rather than each strategy needing to know about.

None of this is unique to Kite — it's the same shape institutional platforms design around (see §3) — but these are your actual numbers, and they're the concrete justification for §4.

---

## 3. How this shared-resource problem is solved elsewhere

This is the same pattern regardless of asset class or scale, just with different names:

- **Market data fan-out / single-connection multiplexing.** Interactive Brokers' TWS API, Bloomberg's B-PIPE, and Refinitiv's Elektron all use the same idea: **one physical connection to the venue, N logical subscribers behind it**, with the gateway process deduping requests and unsubscribing when refcount hits zero. Your `MarketDataGateway` (§4.1) is this pattern at retail scale.
- **Declarative data requirements per strategy, not imperative subscription calls.** QuantConnect LEAN's Algorithm Framework and NautilusTrader both make a strategy *declare* its data universe (symbols, resolution, data types) rather than reaching out and subscribing itself — the engine owns the actual connection lifecycle. This is what lets the engine dedupe across strategies without each strategy knowing about the others. That's the model in §5.
- **Capital/risk as a shared ledger, checked centrally.** Every institutional OMS (Trading Technologies, FlexTrade) separates "strategy decides to trade" from "risk/margin engine says yes" — the strategy never has direct knowledge of firm-wide capital, it only gets an allow/deny from a central check. Your existing 9-step pre-trade gate is already this pattern for risk rules; §4.5 extends it to margin.
- **One order blotter, tagged and filtered — not one blotter per strategy.** This is universal across every OMS: a single `orders`/`fills` table/view is the source of truth, and "strategy" is a filter dimension on it, exactly like "account" or "desk" would be in a multi-desk shop. Building a separate order store per strategy is the mistake almost every DIY system makes and later regrets.
- **Plugin/panel UI composition, not one page per feature.** This is the same idea behind TradingView's per-indicator panes, NinjaTrader/Sierra Chart's "studies," and every no-code builder's node palette: a fixed shell (chrome, nav, account-wide views) plus a **registry of small scoped panels** contributed by whatever is currently active. §7 adapts this to your FastAPI + vanilla JS stack now, with a clean upgrade path to the React Flow builder frontend from Part 1 Phase 2.

---

## 4. The Common Engine — concrete components

This is the layer every strategy (F&O or intraday, hand-written or future graph-built) sits on top of. None of it is strategy-specific; all of it is what Part 1 called "additive seams."

### 4.1 `MarketDataGateway`
Owns the actual KiteTicker connection(s) — and only this component is allowed to call `subscribe` / `unsubscribe` / `setMode`. Internally:
- Maintains a **refcount per `(instrument_token, mode)`**. `StrategyRouter` tells it "strategy X is now active and needs {tokens, mode}" on activation and "no longer needs" on deactivation; the gateway subscribes/unsubscribes only on 0→1 / 1→0 transitions.
- Picks the **cheapest mode that satisfies every active subscriber** of a token — if one strategy needs `full` (depth) and another only needs `ltp` for the same token, subscribe once at `full` and let both consume from the same tick stream internally.
- Packs subscriptions across connections respecting the 3,000-token ceiling, and raises a **hard alert** (not a silent log line) if you approach it, since this is exactly the kind of failure that costs money without an obvious symptom.
- Republishes every tick internally (Redis Streams `market:ticks:{token}` or an in-process asyncio event bus if you want to avoid the extra hop) so `MarketDataGateway` is the *only* code in the system that talks to Kite's WS; everything else — including your own `CandleAggregator` — is a consumer.

### 4.2 `InstrumentMaster`
Wraps Kite's instrument dump (refreshed once daily pre-market) plus derived lookups strategies actually need:
- Symbol → token, lot size, tick size, expiry list.
- **Option-chain builder**: given underlying + expiry, return the strike ladder with CE/PE tokens — this is the single most-reused piece of infrastructure for every F&O strategy you'll add, so it belongs here once, not reimplemented per strategy.
- Freeze-quantity lookups per contract (NSE revises these periodically for index options — pull from the instrument/contract master or NSE's published list rather than hardcoding a number in code, since a stale hardcoded freeze qty silently produces rejected orders on expiry-heavy contracts).

### 4.3 `HistoricalDataService`
A thin, **rate-limit-aware** wrapper (respecting the ~3 req/sec ceiling with a token-bucket limiter) around Kite's historical API, with a local cache (Postgres or a simple parquet/SQLite cache) so the same 500-candle lookback isn't re-fetched by every strategy on every restart. Used by both the backtest engine and any strategy that needs on-boot lookback (e.g., your `volume_sma` node).

### 4.4 `CandleAggregator`
Builds OHLC candles **from the shared tick stream**, not from repeated historical-API polling — this is Zerodha's own recommended pattern and it also happens to be exactly the shared-infrastructure move: one aggregator produces 1-min/5-min/15-min candles per subscribed token once, and every strategy needing that timeframe reads the same series instead of each strategy running its own bucketing logic.

### 4.5 `CapitalAllocator` / margin ledger — the piece most DIY systems miss
This is the one addition I'd flag as **non-optional once you run more than one live strategy**, and it's especially sharp for F&O because option margin is a shared pool, not per-strategy:
- Each active strategy manifest declares a **capital/margin budget** (e.g., "IVBS: ₹X allocated," "OptionsMomentum: ₹Y allocated").
- Before any order, the pre-trade gate's *new* 10th check calls this ledger: does this strategy have enough of *its own* allocated-and-currently-free margin, not just "does the account have margin" (Kite's `get_margins()` reflects the whole account, which two strategies could each read as "sufficient" independently and both be wrong once combined).
- On fill, the ledger debits the strategy's allocation; on close, it credits it back. This also gives you, for free, real per-strategy P&L attribution and the "is this strategy over-allocated" alert you'll want before you ever consider the agentic loop from Part 1 Phase 3 (an agent should never be able to allocate itself more capital than a human approved).

### 4.6 `OrderService` / unified OMS (extends what you have)
No structural change from Part 1 — it's the same centralized service — but two things to enforce now while you add F&O:
- Every order row (and every Redis order-event) carries `strategy_id` **and** `order_group_id` (new — see §6.1 for multi-leg). This is what makes "all orders in one place, filterable by strategy" true by construction rather than by UI convention.
- The service tracks the ~200/min order-placement budget centrally and queues/throttles rather than letting a multi-leg F&O signal blow through the API limit — this belongs here, not in each strategy.

### 4.7 `EODSquareOffService`
A scheduled, **strategy-agnostic** job that queries all open MIS/intraday positions across every strategy and squares them off ahead of the exchange cutoff, independent of whether the strategy that opened a position is even still running. This is a common-engine responsibility precisely because it must work even if a strategy crashed mid-day and never got the chance to exit itself — treat it with the same "never bypassable" status as the pre-trade risk gate.

### 4.8 `AnalyticsService`
Same shared analytics schema from Part 1 §Phase 1, with `strategy_id` as a standard filter dimension everywhere (per-strategy P&L, win rate, slippage, drawdown) plus an unfiltered "whole account" rollup. One schema, one set of materialized views, sliced by strategy in the query layer — not a separate analytics pipeline per strategy.

---

## 5. The Strategy Data Contract — how a strategy tells the engine what it needs

This is what makes §4.1's "only subscribe to what's active" actually work, and it's a natural extension of the `StrategyManifest` from Part 1 §5 — add a `requirements` block:

```json
{
  "strategy_id": "ivbs_v2",
  "type": "code",
  "enabled": true,
  "requirements": {
    "instruments": { "mode": "watchlist", "symbols": ["RELIANCE", "TCS", "..."] },
    "candle_intervals": ["1min", "5min"],
    "tick_mode": "quote",
    "capabilities": ["volume_sma", "vix"]
  },
  "capital": { "allocated": 200000, "currency": "INR" },
  "risk": { "max_concurrent": 3, "circuit_breaker_pct": 2.0 }
}
```

```json
{
  "strategy_id": "banknifty_options_momentum",
  "type": "code",
  "enabled": true,
  "requirements": {
    "instruments": { "mode": "option_chain", "underlying": "BANKNIFTY", "expiry": "nearest_weekly", "strike_range_pct": 5 },
    "candle_intervals": ["1min"],
    "tick_mode": "full",
    "capabilities": ["option_chain", "greeks"]
  },
  "capital": { "allocated": 150000, "currency": "INR" },
  "risk": { "max_concurrent": 2, "circuit_breaker_pct": 3.0 }
}
```

On `StrategyRouter.activate(strategy_id)`: resolve `requirements` → concrete instrument tokens (via `InstrumentMaster` for the option-chain case, since strikes shift daily) → call `MarketDataGateway.subscribe(tokens, mode)` with refcounting. On `deactivate`: mirror in reverse. A strategy's business logic **never touches the WS client directly** — same "never talk to the broker/data feed directly" discipline Part 1 recommended for order placement, applied symmetrically to market data.

This also directly answers your "rest should be idle" requirement: an idle (disabled) strategy has zero footprint on the data layer, because it has no active subscriptions and the gateway holds no tokens on its behalf.

---

## 6. What's actually different for F&O strategies

Everything in §4 is shared infrastructure; this section is what's genuinely strategy-class-specific and needs to exist once, in the common engine, so every F&O strategy you add afterward gets it for free.

### 6.1 Multi-leg orders as a first-class concept
An F&O signal is frequently *not* one order — a spread, a hedge, a straddle exit. Introduce an `OrderGroup` (a.k.a. basket) concept in `OrderService`: a strategy submits a list of legs with a shared `order_group_id`; the service places them (respecting the rate budget from §4.6), tracks the group's aggregate fill state, and the pre-trade gate can evaluate the *group's* net risk (e.g., a hedged spread should not be risk-gated as if both legs were naked) rather than leg-by-leg. This is the seam that keeps hedge-aware strategies from being punished by a risk gate that only understands single orders.

### 6.2 Option-chain and Greeks as shared capability nodes
`InstrumentMaster`'s option-chain builder (§4.2) plus a shared Greeks calculator (Black-Scholes off your own tick data, or Kite's option-chain response fields where available) belong in the common engine as `capabilities` a strategy can request (see the `requirements.capabilities` field in §5) — not reimplemented per options strategy. This is exactly the "capability node" idea from Part 1's Strategy IR (§5 of Part 1), applied concretely.

### 6.3 Expiry rollover as a scheduled common-engine job, not strategy logic
A weekly/monthly job that: refreshes `InstrumentMaster`'s current-expiry mapping, closes or rolls any positions in contracts expiring that day per each strategy's configured rollover policy, and updates any `option_chain`-mode subscriptions to the new nearest expiry. This should not live inside individual strategies — it's the same class of problem as `EODSquareOffService`, and for the same reason: it must run even if a strategy's own logic has a gap.

### 6.4 Freeze quantity / order-splitting
NSE caps the maximum quantity per single order for index F&O contracts ("freeze quantity"), and exceeding it gets the order rejected outright rather than partially filled. Since this value is revised periodically by the exchange, don't hardcode it — have `InstrumentMaster` source it from the contract master / a small config table you refresh alongside your daily instrument sync, and have `OrderService` auto-split any order exceeding it into multiple orders under one `order_group_id`. This is a one-time build that every current and future F&O strategy benefits from silently.

---

## 7. What's actually different for intraday equity strategies

Lighter list — most of the heavy lifting is shared infra you already have or are adding in §4:

- **Product type discipline**: MIS orders specifically, enforced at `OrderService` level (reject/flag any intraday-tagged strategy that tries to place a CNC/NRML order) rather than trusting each strategy to get the product type right.
- **EOD square-off** (§4.7) is the main safety-critical addition — this is the single most important reliability item for intraday equity given you're running this personally with no ops team watching the clock.
- **Circuit-limit awareness**: `MarketDataGateway`'s `quote`-mode ticks already carry upper/lower circuit fields from Kite — surface this in the shared pre-trade gate so *any* intraday strategy automatically gets "don't enter within X% of a circuit limit" without reimplementing the check.

---

## 8. Orders/positions: one place, filtered by strategy — the concrete shape

- **Backend**: single `orders` table (already true in your design) with `strategy_id`, `order_group_id` (new, §6.1), `mode` (paper/live). Single `positions` view aggregating fills, queryable filtered or unfiltered.
- **Event stream**: single `order_events` Redis Stream (per Part 1 §Phase 0 item 4) — one topic, `strategy_id` as a field on each event, not one stream per strategy. A future audit/analytics/agent consumer subscribes once and filters in-process; it doesn't need to know your strategy list in advance.
- **UI**: one Orders/Positions screen, strategy as a filter facet (dropdown or chip multi-select) plus an "All" aggregate default — this is the "big company" pattern (a single blotter, strategy/account/desk as a facet) rather than a page per strategy, and it's also just less UI to build and maintain for a one-person system.

---

## 9. Scoped UI for strategy-specific things (scanners, chain views) — architecture

The Orders/Positions/Analytics/Risk screens are common and strategy-agnostic (§8, §4.8). What's genuinely strategy-specific — a volume-spike scanner table for IVBS, a live option-chain-with-signal-overlay for an options strategy — should be **scoped panels**, not separate apps, using a plugin-panel pattern:

1. Each strategy manifest gets an optional `ui` block declaring what scoped views it contributes, e.g. `"ui": {"panels": [{"type": "scanner_table", "endpoint": "/api/strategies/ivbs_v2/scan"}]}`.
2. The dashboard shell renders a fixed set of common views (Orders, Positions, Analytics, Risk) plus a **dynamically generated tab/section per currently-enabled strategy**, sourced from its `ui.panels` declaration — so enabling/disabling a strategy in the manifest automatically shows/hides its scoped UI, with zero dashboard code changes per new strategy.
3. Backend-wise, each strategy exposes its own small scoped read endpoint (`/api/strategies/{id}/scan`, `/api/strategies/{id}/chain`) that the shell fetches into its panel — this keeps strategy-specific query logic inside the strategy's own module rather than leaking into a shared "God controller," while the shell itself stays completely generic.
4. This is deliberately the same "canvas is generic, content is declared as data" idea as the Strategy IR from Part 1 §5 — you're applying it to the UI layer instead of the execution layer, and it's what makes the drag-and-drop builder (Part 1 Phase 2) a natural extension later rather than a rewrite: a graph-built strategy just declares the same `ui.panels` shape a hand-written one does.

With your current vanilla-JS + Chart.js dashboard, this is realistic as: a `panels` array in the frontend config fetched from `/api/dashboard/config` (server-side aggregation of every enabled strategy's `ui.panels`), each rendered by a small generic panel-type renderer (`scanner_table`, `option_chain`, `metric_card` — a handful of reusable panel *types*, not one bespoke component per strategy). When you move to the React Flow builder frontend in Part 1 Phase 2, the same `ui.panels` contract carries over unchanged.

---

## 10. Concrete sprint backlog for *this* task (F&O + intraday + common engine)

This slots into / tightens Part 1's Phase 0–1, reordered around what you said is the current task:

1. **`MarketDataGateway` with refcounted subscribe/unsubscribe/mode** (§4.1) — this unblocks everything else and is the highest-leverage single piece of work, since without it every F&O strategy you add risks the silent 3,000-token failure mode from §2.
2. **`StrategyManifest.requirements` block + resolution logic** (§5) — including the `option_chain` requirement type resolved via `InstrumentMaster`.
3. **`InstrumentMaster`** with option-chain builder and freeze-quantity lookup (§4.2, §6.4) — needed before you can write a single real F&O strategy.
4. **`CandleAggregator`** off the shared tick stream (§4.4) — replaces any per-strategy historical polling before you hit the 3 req/sec ceiling in practice.
5. **`CapitalAllocator` ledger + pre-trade gate's 10th check** (§4.5) — do this *before* your second live strategy goes live, not after; retrofitting it once two strategies have already been fighting over margin is much more painful to diagnose.
6. **`OrderGroup` / multi-leg support in `OrderService`** (§6.1) — needed for any spread/hedge F&O strategy.
7. **`EODSquareOffService`** (§4.7) — build this even before your first intraday strategy goes live with real capital; it's your safety net if the strategy process dies mid-session.
8. **Orders/Positions UI: add strategy filter facet** (§8) — mechanical once `strategy_id`/`order_group_id` are on every row.
9. **First F&O strategy + first additional intraday equity strategy**, written against the above — this doubles as the validation that the common engine actually generalizes (same insurance-against-overfitting logic as Part 1 Phase 1 item 1).
10. **Scoped UI panel contract** (`ui.panels` + generic panel-type renderer, §9) — do this alongside item 9 so your new strategies prove the pattern rather than getting hand-built pages that need to be retrofitted later.

Items 1–7 are common-engine work with **zero behavior change to your existing two strategies** — same strangler-fig discipline as Part 1 Phase 0. Shadow-run before cutover, same as before.

---

## 11. Reliability checklist — this is real money, no ops team

Since this stays personal (not a product) but trades live capital, the bar is "boringly reliable," not "feature-complete":

- **WS reconnect + heartbeat monitoring** in `MarketDataGateway` with an explicit alert (Telegram/SMS/email — whatever you already have wired up) on disconnect, not just an auto-reconnect that silently works most of the time. A silent data gap during market hours is worse than a crash, because nothing tells you your strategies are now trading blind.
- **Hard alert, not a log line**, when subscription count approaches the 3,000-per-connection ceiling (§2) — this is the one failure mode that produces no error and no crash.
- **Kill switch**: one command/endpoint that immediately disables all strategies (stops new signals) without needing to touch running positions — separate from the EOD square-off, for the "something's wrong, stop everything now" case.
- **Margin cushion buffer** in `CapitalAllocator` — don't allocate 100% of available margin across strategies; leave explicit headroom so a slippage-driven margin call on one strategy doesn't cascade into forced square-offs on another.
- **Order-group atomicity for hedges**: if leg 1 of a spread fills and leg 2 fails/rejects, `OrderService` needs an explicit "unhedged leg" alert and ideally an auto-flatten-the-orphan-leg policy — this is the F&O-specific version of the orphan-position check you already have.
- Keep the existing crash-only discipline (Redis NX locks, reconciliation loop, orphan-position checks) untouched and extend it to cover `order_group_id` groups and the new `CapitalAllocator` state, per the same "don't refactor safety-critical behavior without a parity test" rule from Part 1 §8.

---

## 12. Sources consulted (in addition to Part 1's)

- Kite Connect WebSocket modes (ltp/quote/full) and subscribe/unsubscribe semantics: https://kite.trade/docs/connect/v3/websocket/
- Kite Connect forum — confirmed 3,000 instruments/connection, up to 3 connections/API key, soft-limit risk beyond that: https://www.kite.trade/forum/discussion/comment/51588/
- Kite Connect forum — REST API ~3 requests/second, historical API has no bulk endpoint, recommendation to build candles from WebSocket ticks rather than re-polling: https://kite.trade/forum/discussion/comment/35069/ , https://kite.trade/forum/discussion/6329/kiteconnect3-api-limits
- Kite Connect forum — ~200 order placements/minute at API level plus separate RMS-level daily MIS/BO/CO caps: https://kite.trade/forum/discussion/6329/kiteconnect3-api-limits
