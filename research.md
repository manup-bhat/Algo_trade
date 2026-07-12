Here's what real evidence supports for each parameter group — and where I want to be honest that "best value" only exists after *your* backtest runs, not from general research. I'll flag both types clearly.

## A framing note before the tables

Two different kinds of "best value" questions:
- **Values a general principle can genuinely justify** (e.g., don't scan the opening 15 minutes because volume there is structurally elevated for reasons unrelated to institutional accumulation) — these I can ground in real evidence.
- **Values that only exist as an answer to "what worked on NSE mid-caps historically"** (e.g., is 15× the right multiple, or would 12× or 18× have produced a better Sharpe) — no amount of general research substitutes for running your own backtest engine, which you already have and haven't pointed at IVBS yet. I'll say so explicitly rather than inventing false precision.

## Scanner parameters

NSE tick-by-tick data shows unusually high volatility, trading volume and number of trades during the opening and closing minutes of the market, forming a 'U'-shaped curve of activity throughout the day, and most volume and spread-related liquidity measures on NSE Nifty-index stocks are U-shaped, similar to quote-driven markets.

| Setting | Current | Assessment | Reasoning |
|---|---|---|---|
| `SCANNER_START_MINUTE` | 30 | **Reasonable, arguably still slightly early** | The U-shape isn't a clean step function — elevated volume typically decays gradually from the open rather than ending sharply at 9:30. Since your own SMA comparison is time-of-day-blind (a flat 500-period rolling average doesn't know it's 9:31 vs 11:00), candles just after 9:30 still sit in an elevated-volume tail. Worth checking empirically: what fraction of SCAN_HITs land in 9:30–9:45 vs. later, and do the 9:30–9:45 hits convert to trades at a lower rate? If so, push to 09:35–09:40. |
| `VOLUME_SMA_PERIOD=500` (mean, flat) | — | **Structurally biased, worth a methodology upgrade** | Because volume is U-shaped, a candle's "normal" volume depends on *what time of day it is*, not just the flat 500-candle average. A 9:35 candle and a 12:30 candle are being judged against the same baseline even though their genuine baseline differs by design. This is a real, fixable bias: either (a) use a time-of-day-bucketed baseline (e.g., separate rolling averages per 5-minute-of-day bucket), or (b) accept the bias but recognize your 15× threshold is implicitly *harder to clear* at midday (when true baseline volume is lower relative to the flat average) and *easier to clear* near open/close — which may explain some of the 9:15 candle false-positive pattern you already noted in your own docs. |
| `VOLUME_SPIKE_MULTIPLE=15.0` (arithmetic-mean-based) | — | **Sound direction, but mean-of-volume is a fragile baseline** | Volume distributions are heavy-tailed/right-skewed — a handful of huge-volume candles (news, block deals) drag the arithmetic mean up, which then *raises the bar* for what counts as a spike right after a real spike happened (self-suppressing). Market-microstructure and signal-detection practice generally favors a **median or MAD-based (median absolute deviation) baseline** over a mean for exactly this reason — it's robust to the outliers you're trying to detect in the first place. This is a concrete, testable upgrade: run your backtest with `median(500)` instead of `mean(500)` as the denominator and compare signal counts/quality. |
| `MIN_TURNOVER_CRORE=8.0`, `MIN_PRICE/MAX_PRICE=50/5000` | — | **Keep** | No strong evidence-based case to move these without your own data; they're sensible liquidity/manipulability screens and your own Part 18.3 review trigger (>15 hits/day → raise, <3/week → lower) is the right mechanism — just make sure it's actually being tracked, not just documented. |
| `SCAN_CUTOFF_HOUR=14` vs `MAX_ENTRY_TIME=13:30` | — | **Keep, internally consistent** | Already correctly distinguished per your Part 21.2 clarification. |

## Dry-up / monitoring parameters

There isn't NSE-specific published research on "optimal consolidation duration before re-ignition" — this is a genuinely strategy-specific empirical question. What I can say with more confidence:

| Setting | Current | Assessment |
|---|---|---|
| `DRYUP_MAX_MINUTES` | 20 (README) vs 25 (config.yaml) | **Fix the disagreement first, tune second.** Until these match, you don't actually know which value is live. Once unified: a 20–25 minute dry-up window against a 1-minute-candle strategy is a reasonable order of magnitude (comparable to the "compression duration ≥ 8 bars" style thresholds used in general momentum-ignition scanners), but the right number is genuinely a backtest question — too short and you cut off real accumulation, too long and you're holding a scan hit through the U-shape's midday liquidity trough where re-ignition is structurally less likely to fire on real volume regardless of setup quality. |
| `MIN_DRYUP_CANDLES=2` | — | Keep as a floor; this is more about avoiding a 1-candle noise trigger than a tunable edge parameter. |
| `ASHAPE_*` thresholds | — | No general literature to anchor these against — pure strategy-specific behavior, backtest territory. |

## Entry / re-ignition parameters

A common momentum-breakout design uses a statistical threshold — e.g., a momentum indicator exceeding its own moving average by one standard deviation — combined with trend alignment via a longer moving average, and general momentum-ignition scanner designs in current use treat volume expansion of roughly 1.5× the 20-period average as the confirmation threshold, on top of a prior compression/consolidation condition.

This is genuinely useful comparative context: **most generic breakout/momentum scanners confirm on 1.5–2× volume expansion. Your `REIGNITION_VOLUME_MULTIPLE=2.0` sits right in that mainstream range** — which is the correct relative calibration, since re-ignition is a *confirmation* signal layered on top of an already-rare 15× impact candle, not a standalone spike-detection filter. Using a 15×-style threshold for re-ignition too would be over-filtering (you'd almost never see two 15× events in the same setup) — 2.0× against the dry-up baseline is the right order of magnitude for "the pause is over," and I wouldn't move it without backtest evidence either way.

| Setting | Current | Assessment |
|---|---|---|
| `REIGNITION_VOLUME_MULTIPLE=2.0` | — | **Well-calibrated relative to general practice** — keep. |
| `REIGNITION_MIN_PCT_OF_IMPACT=0.08` | — | Reasonable floor to stop a tiny dry-up baseline from producing a technically-2× but practically-trivial re-ignition; no external benchmark exists for the exact 8% figure, pure backtest territory. |
| `ENTRY_BUFFER_PCT` | 0.003 (README) vs 0.001 (config.yaml) | **Another disagreement to resolve first.** 0.1% vs 0.3% is a meaningfully different fill-rate/slippage tradeoff on liquid mid-caps — worth explicitly measuring actual fill rate at whichever value is really live. |

## Risk / exit parameters — the best-grounded section

This is where I found the most transferable, evidence-backed guidance.

ATR multiplier selection genuinely varies by holding-period: roughly 1–1.5× for scalping, 1.5–2.5× for day trading, 2–3× for swing trading, and 3–4× for position trading, and below 1× ATR, stop-out rates from pure noise exceed 65%. Separately, the classic Chandelier Exit uses a 22-period lookback with a 3× ATR multiplier, designed for daily-chart swing-to-position timeframes, with a 2.5–3× ATR range typically capturing the most profit from sustained trends while still protecting against major reversals.

| Setting | Current | Assessment |
|---|---|---|
| `ATR_TRAIL_MULTIPLIER=2.5` | — | **Well-placed within the day-trading band (1.5–2.5×) from general ATR-stop research** — this is good calibration, not a number pulled from nowhere. |
| `ATR_PERIOD=14` **on 1-minute candles** | — | **This is the one place I'd flag a real methodological concern.** Every piece of Chandelier/ATR research above anchors its multiplier guidance to *daily-bar* ATR periods (14–22 *days*). Your ATR(14) is computed over 14 *one-minute bars* — a 14-minute rolling volatility estimate is inherently much noisier (smaller effective sample, more sensitive to a single wide candle) than a 14–22 *day* ATR. The multiplier guidance above doesn't automatically transfer across that timeframe change. Concretely: consider testing a somewhat longer 1-minute-bar ATR window (20–30 minutes) to smooth the estimate, or anchor ATR to a slightly coarser bar (e.g., compute it on 3-minute resampled bars even though signals stay on 1-minute) — and treat 2.5× as a starting point to re-validate specifically at the 14-minute lookback rather than assuming the daily-chart literature's endorsement transfers cleanly. |
| Fixed 1:4 R-multiple exit ladder | — | Fixed-point stops that ignore volatility regime are the known failure mode — but you're not using a fixed-point stop, you're using a fixed-*R* target (which already scales with your ATR/swing-low-derived risk-per-share), so this critique doesn't really apply to your design; the fixed-R structure is a different and more defensible choice than a fixed-rupee or fixed-percent target would be. |
| `DYNAMIC_TRAILING_ENABLED=false` (default off) | — | Your own sequencing (test flag-gated, compare against fixed-ladder baseline, never enable both new features at once) is exactly right and matches how the ATR-stop literature itself recommends rollout — keep it OFF until you've specifically re-validated the 14-minute ATR window per the point above. |

## Market-regime gate

India VIX has spent the recent weeks trading below 12 for the first time consistently since February 2026, and as of today India VIX is trading around 12.25, having moved between a 52-week low of 8.72 and high of 28.91 — with a brief spike to ~14.7 on July 8 on geopolitical news before settling back down.

| Setting | Current | Assessment |
|---|---|---|
| `HIGH_VIX_THRESHOLD` | 18.0 (config.yaml) vs 20.0 (.env ref) | **Resolve the disagreement; 18 is the better-justified value** — with the regime spending most of 2026 in the 9–15 band and even the sharpest recent spike topping out under 15, an 18 threshold still only fires on genuinely unusual days, not on routine daily noise. A 20 threshold would almost never fire in the current regime, silently disabling a safety feature you built. |
| `HIGH_VIX_TURNOVER_CRORE=12.0` | — | Fine as-is; not currently active given the regime, which is expected and correct behavior. |
| `NIFTY_GATE_ENABLED=true`, `NIFTY_EMA_PERIOD=20` | — | 20-period EMA on 5-minute bars is a standard, unremarkable trend filter choice — no strong evidence either way to move it; low priority relative to the config disagreements above. |

## The actual highest-leverage move

Every single "keep as-is, no strong evidence to change" verdict above is a **hypothesis**, not a validated conclusion — same caveat as last time. The parameters with genuine external research backing (2.0× re-ignition, 2.5× ATR multiplier, U-shape-aware scan timing) are *directionally* well-chosen; the ones with no external literature (turnover floor, dry-up minutes, A-shape thresholds) are pure NSE-specific empirical questions that no amount of general market-microstructure research can answer for you. Before touching any of these numbers again, I'd fix the **three config-source disagreements** (`DRYUP_MAX_MINUTES`, `HIGH_VIX_THRESHOLD`, `ENTRY_BUFFER_PCT`) — those aren't tuning questions, they're bugs, since you don't currently know which value is actually running — and then run the pending historical IVBS backtest with median-vs-mean volume baseline as one of the first things to compare, since that's a genuinely free improvement candidate with a clear mechanism, not just a number to fiddle with.










# IVBS Platform — Architecture, Strategy & Indian Market Research
### Deep analysis against current (July 2026) regulation, cost structure, and market microstructure evidence

---

## 0. Bottom line

The codebase is unusually well-engineered for a solo/small-team retail project — two-process isolation, a real plugin framework, idempotent order handling, a documented state machine with regression tests for its own past bugs. The strategy logic (spike → dry-up → re-ignition) is a coherent, defensible implementation of a real market-microstructure idea, not a random indicator soup.

But there is **one urgent, non-strategy issue that overrides everything else**: SEBI's retail algo-trading framework became **fully mandatory for every broker and every API user on 1 April 2026**, and today is 12 July 2026 — the platform has been running in a changed regulatory environment for over three months. Two of the framework's technical requirements are **not present anywhere in this codebase** and will cause silent order failures or account suspension risk if not addressed before the next live session. This is covered first because it's the one finding that's a "stop and fix before you place another order" item, not a "tune later" item.

---

## 1. CRITICAL — Regulatory compliance gap (SEBI/NSE Algo Framework, live since April 1, 2026)

SEBI issued its retail algo-trading circular in February 2025 and, after two deadline extensions, the framework became **fully enforceable for all brokers and all existing API users on April 1, 2026**. This is not a future concern — it is the current legal operating environment for every Kite Connect API user, including this platform.

What actually changed, and how it maps to this codebase:

| Requirement (live since Apr 1, 2026) | What it means | Status in this codebase |
|---|---|---|
| **Static IP whitelisting for order-placement calls.** Read-only endpoints (WebSocket ticks, orderbook, positions) are exempt; only order placement/modification requires a whitelisted static IP registered at the Kite Connect *developer-account* level. | Zerodha now rejects order API calls from unregistered/dynamic IPs. | **Not present.** Nothing in `engine/kite/client.py`, the `.env` reference, or the deployment docs mentions a static IP. If this is run from a home connection with a dynamic IP or a cloud box without a fixed egress IP, live orders will be rejected outright — the bot will scan and signal correctly but fail silently at the order-placement step. |
| **`market_protection` parameter mandatory on MARKET-type orders.** Orders without it are rejected; `-1` requests Zerodha's automatic protection band, or you can pass an explicit 1–10% band. | The spec's Part 9.4 (Exit Market Order) already lists `market_protection: -1` — so the **squareoff/emergency-exit path is correctly speced**. | **Gap: the SL-M order (Part 9.2) has no `market_protection` field at all.** SL-M is a market order once triggered, and Zerodha/community reports around the April rollout are explicit that market-type executions need the parameter; several developers using SL-type orders hit rejections until the SDKs were patched. This needs to be verified directly against the current `pykiteconnect` SDK behavior for `SL-M` specifically (the Kite dev forum shows some ambiguity even among Zerodha's own responders on whether SL-type orders need it), but given the ambiguity, the safe engineering move is to add `market_protection=-1` to every order path that can execute as a market fill — entry-limit widening to market, SL-M, and exit-market — and to add an integration test that asserts the parameter is present before shipping. |
| **App ID / API key bound to one static IP; one order-path per app.** | Multiple orders from unregistered IPs get rejected outright, not queued or retried. | Order retry logic (`ORDER_MAX_RETRIES=3`, exponential backoff) will not help here — an IP-rejection is not a `NetworkException`/`GeneralException`, it will most likely surface as a 4xx/`InputException`-class rejection, which the spec's own exception table classifies as **non-retryable**. Good news: the existing exception handling won't infinite-loop on this, but it also means a misconfigured IP produces silent order rejections with no automatic remediation — this needs explicit alerting, not just a log line. |
| **Daily session reset, OAuth + 2FA once per trading day; long-lived refresh-token flows are discontinued.** | Sessions must be re-established each morning. | **Already compliant.** The platform's daily 9:00 AM re-authentication flow (Part 17.1) and `.kite_token` 24h-TTL design were built for daily token refresh anyway — no change needed. |
| **10 orders-per-second (OPS) threshold** — below this, no formal exchange algo-registration/Algo-ID is required for a self-built strategy used for personal/family trading. | This is the one piece of good news. | IVBS is fundamentally an intraday swing strategy — at most `MAX_CONCURRENT_POSITIONS` positions with occasional entry/SL/modify/exit calls. Realistic peak order rate is a small number of orders per **minute**, nowhere near 10/second. **As a personally-coded "white box" strategy run for your own account (not sold, not rented to others), this almost certainly falls under the exempt personal-use bucket and does not need exchange algo-registration or an Algo-ID** — provided the static-IP and market-protection requirements above are met. The moment this is offered to *other* people's accounts (family sharing is allowed only within the legally defined "family" — spouse, dependent children/parents — with 2FA-verified consent per IP), the registration/empanelment obligations kick in. |
| **Market and IOC order types are restricted/reshaped for algo execution** on some exchange guidance (NSE FAQ, Nov 2025) — the practical effect for Kite users has landed as the market-protection requirement above rather than an outright type ban. | — | Confirms the market_protection item above is the operative constraint, not a ban on market orders per se. |

**Action before the next live session:**
1. Provision and register a static IP (a small VPS/cloud egress IP or a static-IP add-on from your ISP; community pricing is roughly ₹1,500/year) at the Kite Connect developer-account level — this covers *all* apps under that account, including any paper/live split.
2. Add `market_protection` to every code path that places or converts to a market-type order (`order_service.place_stop_loss`, `place_exit_market`, and the fill-timeout/entry-widening path if it ever escalates to market), and pin/upgrade `pykiteconnect` to a version confirmed to carry the parameter through (the parameter was still being backfilled into SDKs, including Python, around the April rollout — verify your installed version explicitly rather than assuming).
3. Add a startup/pre-trade check that fails loudly (not just logs) if a test order-margin call returns an IP-rejection-shaped error, so a misconfigured static IP is caught at 9:00 AM pre-market setup rather than discovered as a string of silent rejected entries mid-session.
4. Treat this platform as personal/family "white box" use only — do not distribute it, sell signals from it, or run it for non-family accounts without going through exchange empanelment; that is a materially different (and much heavier) compliance regime.

---

## 2. Architecture assessment

### 2.1 What's genuinely well done
- **Two-process isolation with Redis as the only IPC boundary** is the correct call for exactly the reason stated in the docs: `kiteconnect` is synchronous and `KiteTicker` runs its own thread, so keeping the dashboard's uvicorn loop out of the trading engine's asyncio loop avoids a whole class of event-loop contention bugs. This mirrors how most serious retail/prop algo stacks in India are actually built (separate execution engine from UI/reporting layer).
- **The plugin framework (`BaseStrategy` + `StrategyRouter` with per-strategy exception isolation)** is a real architectural investment, not decoration — it means a bug in the `options_momentum` strategy literally cannot take down IVBS, which is exactly the failure mode that kills naive single-file bots.
- **Idempotency and race-condition handling** (Redis NX exit locks, `(order_id, status)` dedup, pre-update snapshots for the two documented bug regressions, reconciliation every 5 minutes, orphan detection on startup) — this is the layer most hobby bots skip entirely, and it's the layer that actually prevents account-blowing incidents (double SL, double exit, naked positions after a missed postback).
- **`noeviction` Redis policy** is the right choice and stated correctly — an OOM error is recoverable/alertable, silent eviction of strategy state is not.

### 2.2 Gaps and risks beyond the regulatory item above

| Area | Issue | Why it matters |
|---|---|---|
| **Redis TTL hygiene** (already flagged in your own Part 21.6) | `position:{symbol}`, `engine:blocked_margin`, `engine:status`, `engine:circuit_breaker` have no TTL. | If the engine crashes mid-session and Redis persists (`--save 60 1`), a restart on a new trading day can read stale MANAGING-state positions or a stale blocked-margin figure before `job_pre_market_setup` resets them — the orphan-detection logic mitigates this for actual broker positions, but blocked-margin and circuit-breaker flags reading stale on a fast restart mid-day (not just next-day) is a real gap. |
| **Cost calculator for `options_momentum`** | The documented `cost_calculator.py` charges table (Part 19.1) is built around **equity intraday STT (0.025% sell-side)**. Options STT was hiked from 0.10%/0.125% to **0.15% flat** (premium and exercise) effective April 1, 2026 as part of Budget 2026. | If `engine/orders/cost_calculator.py` shares one code path across strategies with a single STT constant, the options plugin's net-P&L and pre-trade cost estimates will be understated by roughly 20–50% relative to the old rate. This directly affects the options strategy's real edge calculation — worth an explicit per-asset-class STT config split rather than one global `STT_INTRADAY_SELL_PCT`. |
| **Single-machine, single-Redis, no secrets management** | `.env` holds API secret + token; Redis has no password by default (`requirepass ""` in the sample compose file) with a comment to add one "if running on any non-isolated machine." | Reasonable for a bound-to-127.0.0.1 personal deployment as documented, but worth stating explicitly: the moment this runs on any shared or cloud VPS (which the static-IP requirement above may now force), the Redis password and OS-level firewalling become mandatory, not optional. |
| **APScheduler misfire handling** | Own audit already flags `misfire_grace_time`/`coalesce` as needed; README says these are set (`misfire_grace_time=300s`, `coalesce=True`, `max_instances=1`), but Part 21.6 lists it as still-pending. | Worth reconciling — if README is describing the target state rather than shipped state, the 15:20 squareoff job and 9:00 AM setup job are exactly the two jobs where a missed/duplicated fire is costly (double squareoff attempt is harmless; a *missed* 15:20 fire on a slow machine is not). |
| **Single point of failure: one machine, one broadband/VPS link** | No documented failover for a mid-session ISP drop beyond WS reconnect (10 attempts) and eventual `on_fatal_disconnect` emergency close. | Reasonable for a solo retail setup, but the emergency-close path itself now depends on the *same* static IP and market_protection compliance above — if the fatal-disconnect handler's market order gets rejected for a compliance reason rather than a connectivity reason, the position sits open and unmonitored. Worth a distinct "compliance-rejection during emergency close" alert path, separate from ordinary retry logic. |

### 2.3 Pipeline / data-flow review

The tick → candle → coordinator → router → strategy → order funnel is clean and the per-symbol FSM is textbook-correct for this kind of setup: `IDLE → SCAN_HIT → MONITORING → ACTION_PENDING → MANAGING → CLOSED`, with a documented re-entry loop back to `SCAN_HIT`. The two historical bugs you regression-tested (using post-update consolidation data for the breakout/volume check instead of a pre-update snapshot) are exactly the class of subtle bug that this kind of state machine is prone to, and fixing them with explicit snapshot variables (`prev_volumes`, `breakout_level`) captured *before* `consolidation.update()` is the right pattern — this is worth keeping as a permanent code-review checklist item any time the consolidation-update step is touched again.

One pipeline nuance worth double-checking empirically rather than assuming: the 9:15 AM opening-candle volume spike interacting with a *loaded* (not fresh) 500-period SMA. Your own docs call this out as "expected and desired," but it's exactly the kind of edge case that should show up as a measurable line item in the eventual historical backtest (Section 21.3 flags the backtest itself as the top pending validation task) — specifically, what fraction of daily SCAN_HITs are 9:15 candles, and what their conversion-to-trade rate looks like versus mid-session spikes.

---

## 3. Strategy soundness — evidence-based, not vibes-based

**Verdict, unchanged from your own Part 21.1 and worth reinforcing with current sourcing: structurally sound, unproven-after-costs, and the missing piece is still the same one you already identified — a real historical backtest of IVBS itself.**

What the current (2026) literature and market-structure writing actually supports:

- **Volume-confirmed breakouts have a documented edge over unconfirmed ones.** The consistent theme across current trading-education and market-microstructure sources is that breakouts on relative-volume expansion show materially better continuation odds than breakouts on flat/declining volume, and that a large share of "breakouts" that fail do so specifically because they weren't backed by real participation. This is the textbook justification for your 15× volume-spike filter as a *screen*, not as a standalone entry signal.
- **The dominant failure mode of naive breakout trading is the false breakout / stop-hunt / liquidity-sweep**, where price pokes through a level on the initial spike and then reverses before real continuation — current trading-education sources consistently describe this as driven by informed/institutional participants absorbing retail momentum-chasers at the level, then reversing. Your architecture's core idea — **don't buy the first spike, wait for a dry-up/retest, buy the re-ignition** — is the textbook mitigation for exactly this failure mode, not an arbitrary design choice.
- **Wyckoff-style accumulation framing** (spike → secondary test on lower volume → sign-of-strength) remains the standard classical vocabulary for this pattern, and your abandoned-setup re-entry tracker (re-watching a discarded setup all day for a smaller secondary spike) is a faithful implementation of the "secondary test" concept rather than a bolt-on feature.

**What's still unproven, and what the honest gap is:** none of this literature quantifies a retail net-of-cost edge specifically for NSE mid-caps at your exact thresholds (15×, ₹8Cr, 2.0× re-ignition, 1:4). Your own Part 21.3 is correct that the win-rate table in Part 1.5 is a **hypothesis**, and that the backtest engine exists but IVBS itself has not been run through it on real NSE history. That remains the single highest-value next step — everything else in this report is secondary to actually measuring the strategy's historical performance before scaling capital.

### Current market regime context (as of July 12, 2026)
India VIX is trading around **12.2–14.7** as of this week, having spent most of June and early July in an unusually calm 11–13 band before a geopolitical-driven spike to ~14.7 on July 8, before settling back near 12.2 today. For context, readings below 12 are historically read as an exceptionally calm regime, 12–15 as normal, 15–20 as cautious, and above 20 as stressed. Your `HIGH_VIX_THRESHOLD=18.0` (in the platform's config.yaml) or `20.0` (in the older .env reference — worth reconciling the two, they disagree) sits comfortably above the current regime, meaning the `HIGH_VIX_TURNOVER_CRORE` tightening is **not currently active** and the scanner is running at its normal ₹8Cr turnover floor. Per your own Section 1.5 hypothesis table, a low-VIX, range-bound-to-mildly-trending regime like the current one is closer to the "choppy/sideways" bucket (15–25% expected win rate) than the "bull tailwind" bucket (35–45%) — worth keeping expectations calibrated to that rather than the more optimistic scenario while VIX stays this low.

---

## 4. Cost-model verification against current (post–Budget 2026) rates

Good news: your equity-intraday cost assumptions are **still accurate** after the April 2026 Budget changes, because the Budget's STT hike targeted derivatives specifically and left cash/intraday-equity untouched.

| Config value | Spec default | Verified current (July 2026) | Status |
|---|---|---|---|
| `STT_INTRADAY_SELL_PCT` | 0.00025 (0.025%, sell-side only) | Confirmed unchanged — intraday equity STT stayed at 0.025% sell-side through the April 2026 Budget, which only raised futures STT (0.02%→0.05%) and options STT (0.10%/0.125%→0.15% flat). | ✅ Accurate |
| `BROKERAGE_PER_ORDER_INR` | ₹20.0 | Confirmed unchanged — Zerodha's flat ₹20-or-0.03%-whichever-is-lower model for intraday has been stable since 2010 and remains current as of mid-2026 (note: negative account balance triggers ₹40/order instead of ₹20 — not currently modeled, low-priority edge case). | ✅ Accurate |
| `GST_ON_BROKERAGE_PCT` | 18.0 | Confirmed unchanged. | ✅ Accurate |
| `STAMP_DUTY_BUY_PCT` | 0.00003 (0.003% intraday) | Confirmed — matches Zerodha's current published intraday stamp-duty rate. | ✅ Accurate |
| Options-strategy STT (if `cost_calculator.py` is shared) | Not separately specced | **0.15% flat on premium** (both on sale and on exercise) as of April 1, 2026 — more than double the pre-2026 sell-side rate. | ⚠️ Needs an explicit per-asset-class override if `options_momentum` reuses the equity STT constant. |

Your Part 19 breakeven math (≈20.3–21.5% win rate after costs+slippage) therefore remains numerically valid for the IVBS equity strategy specifically — no update needed there. The one place this table matters operationally is if/when the `options_momentum` plugin goes live: its cost/edge math needs the 0.15% options STT, not a copy of the equity constant, or its simulated P&L will be systematically optimistic.

---

## 5. Config value recommendations (with reasoning, current-regime-aware)

Most of your Group A–E defaults are already reasonable and internally consistent — this section flags where current market conditions or the regulatory findings above argue for a specific tweak, rather than re-litigating values that are already well-justified in your own Part 1.3/18.

| Setting | Current default | Recommendation | Reasoning |
|---|---|---|---|
| `HIGH_VIX_THRESHOLD` | 18.0 (config.yaml) vs 20.0 (.env reference in the spec) | **Reconcile to one value** — 18.0 is the more conservative and better-justified choice given VIX has spent most of 2026 in the 9–15 band with brief spikes to ~15, so an 18 threshold still only fires during genuinely elevated conditions, not on ordinary daily noise. | Two config sources disagreeing on the same key is itself a bug risk — whichever loader wins silently determines behavior. |
| `DRYUP_MAX_MINUTES` | 20 (README) vs 25 (config.yaml) | **Reconcile** — same issue as above; pick one and remove the other source of truth, or make config.yaml genuinely authoritative per your own migration note. | Same reasoning — silent divergence between the two config surfaces is a latent bug, not a tuning question. |
| `VOLUME_SPIKE_MULTIPLE` | 15.0 | Keep as-is until the historical backtest exists — don't tune this on vibes. | Your own Part 1.3 rationale (10x = too noisy, 20x = misses real accumulation) is sound reasoning, but it's *reasoning*, not *measurement*. Changing it before backtesting removes your ability to know whether a future change helped or hurt. |
| `MIN_TURNOVER_CRORE` | 8.0 | Keep, but log actual daily scan-hit counts explicitly against your own stated triggers (>15/day → raise, <3/week → lower) — this is already in your Part 18.3 review schedule; the recommendation is just to make sure it's actually being tracked, not just documented as a policy. | — |
| `MAX_CONCURRENT_POSITIONS` | 2 | For the first live month post-compliance-fix, drop to **1**, consistent with your own Part 20 Phase 8 go-live checklist ("Maximum 1 concurrent position for first 2 weeks"). | This isn't a strategy tweak — it's specifically because you're about to change the order-placement code path (adding `market_protection`) for the first time under live compliance rules, and a single-position cap minimizes blast radius while you confirm orders aren't silently failing. |
| `RISK_PER_TRADE_PCT` | 1.0 | Keep. | Standard, well-justified, consistent with SEBI's broader direction of pushing traders toward capital-disciplined position sizing (peak-margin framework, 5x leverage cap) — 1% risk per trade is conservative even relative to that regulatory backdrop. |
| `DAILY_LOSS_LIMIT_PCT` | 3.0 | Keep, but consider a temporary tighter limit (e.g., 1.5–2%) during the first week back live after the compliance fix, mirroring your own Part 13.3 guidance for high-volatility event days — treat "first week on new order-placement code" the same as you'd treat a Budget/RBI day. | Same blast-radius reasoning as the concurrent-positions recommendation. |
| `SCANNER_START_MINUTE` / `MAX_ENTRY_TIME` / `SCAN_CUTOFF_HOUR` | 30 / 13:30 / 14 | Keep as-is — internally consistent and already correctly distinguished in your Part 21.2 clarification (entry cutoff ≠ scan cutoff). | — |

---

## 6. How this compares to other Indian retail algo-trading platforms

For context on where this sits in the broader Indian retail-algo landscape as of mid-2026:

- **No-code/strategy-marketplace platforms** (Streak, Tradetron, AlgoTest, uTrade Algos, Fintrens' Firefly) are built around SEBI's "black box" category when they sell third-party strategies, which is exactly the empanelment/Research-Analyst-license-heavy regime this report recommends you stay clear of by keeping IVBS personal/family-only. Their core technical differentiator versus this codebase is that they've already built the exchange-empanelment and Algo-ID plumbing that this project has not (and, per Section 1 above, does not currently need to, as long as usage stays personal/family and under the 10-OPS threshold).
- **Direct-API "white box" personal bots** like this one are explicitly the category SEBI's framework says needs the *least* additional friction — static IP and market-protection compliance, but no exchange registration — provided the strategy logic is fully your own and not distributed. That matches this project's actual posture.
- Architecturally, this platform's two-process/Redis-IPC/plugin-strategy design is closer to what a small prop desk or a serious semi-professional retail quant would build than to the typical single-script retail bot — the explicit state-machine bug-regression tests and reconciliation/orphan-detection logic in particular are not something most public retail-bot codebases bother with. The main way it currently falls short of "production institutional-grade" is exactly the compliance gap in Section 1 (every serious desk running API orders in India has already had to solve the static-IP/market-protection problem this year) and the still-pending historical backtest (Section 3) — both are closeable gaps, not architectural rewrites.

---

## 7. Prioritized action list

1. **[Blocking, before next live session]** Provision + register a static IP at the Kite Connect developer-account level for order-placement traffic.
2. **[Blocking, before next live session]** Add `market_protection` to `place_stop_loss` (SL-M) and confirm the installed `pykiteconnect` version actually threads the parameter through for your order types; add an integration test asserting it's present on every market-type order payload.
3. **[High]** Add a fail-loud pre-market check (part of `job_pre_market_setup`) that detects IP-rejection-shaped order errors and halts/alerts rather than silently logging.
4. **[High]** Reconcile the two disagreeing config surfaces (`DRYUP_MAX_MINUTES`, `HIGH_VIX_THRESHOLD`) — pick config.yaml as authoritative per your own migration note and finish the "mechanical follow-up" you already flagged.
5. **[High]** Run the pending historical IVBS backtest (Section 21.3's own top item) before increasing capital or concurrent positions beyond the go-live checklist's conservative defaults.
6. **[Medium]** Split the cost calculator's STT constant by asset class before `options_momentum` goes anywhere near live capital — 0.15% flat now, not the old 0.0625%/0.10%/0.125% tiers.
7. **[Medium]** Add TTLs to `position:{symbol}`, `engine:blocked_margin`, `engine:status`, `engine:circuit_breaker` per your own audit note.
8. **[Low]** For the first week on the newly-compliant order path, run with `MAX_CONCURRENT_POSITIONS=1` and a tightened daily loss limit, treating it like any other "changed something in the order pipeline" event.

---

## Sources consulted

- SEBI circular SEBI/HO/MIRSD/MIRSD-PoD/P/2025/0000013 (Feb 4, 2025) and subsequent NSE implementation circulars (NSE/INVG/66524, /67858, /70309) — retail algo-trading framework, static IP, market protection, OPS threshold.
- Zerodha Kite Connect developer documentation and forum threads on static IP and market_protection rollout (kite.trade/forum, support.zerodha.com), April 2026.
- Zerodha official charges page (zerodha.com/charges) and multiple independent 2026 brokerage-comparison summaries, for brokerage/STT/stamp-duty verification.
- Clear, Bajaj Finserv, 5paisa, LegalClarity, Zerodha support — Securities Transaction Tax rates pre/post Budget 2026.
- Bajaj Broking, Angel One, GEPL Capital, White Stallion — SEBI peak-margin and 5x intraday leverage framework, 2026 status.
- HDFC Sky / Kotak Neo / Anand Rathi India VIX live data, July 2026.
- Investopedia-style and current (2025–2026) trading-education sources on volume-confirmed breakouts, false-breakout/liquidity-sweep dynamics, and Wyckoff secondary-test framing, used only for general market-microstructure consensus, not as a substitute for your own backtest.

*This document is engineering and regulatory research, not legal, tax, or investment advice. Verify the static-IP and market_protection implementation against your own live Kite Connect account and current SDK version before trading live capital, and consult a professional for anything tax- or compliance-critical.*