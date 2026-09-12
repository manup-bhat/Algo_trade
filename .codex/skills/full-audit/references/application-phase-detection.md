# Application Phase Detection — Audit and Build for the Right Stage

> "The right decision depends on where the system *is*. Optimizing a prototype for scale, or a
> high-scale system for speed-of-change, are both expensive mistakes."

The same code can be excellent or alarming depending on the application's **lifecycle phase**.
A missing test suite is fine in a day-one prototype and a fire in a payment platform. Before
auditing or extending an application, **detect its phase** — it sets the bar for "good," the
tolerance for debt, and the priority of fixes.

**Use this**: first thing in any full audit (MAP stage), and when planning new work so the
approach matches the stage.

---

## The Six Phases

```
GREENFIELD → ACTIVE BUILD → SCALING → MATURE/MAINTENANCE → LEGACY → SUNSET
(0→1)        (1→MVP→GA)     (GA→growth) (steady state)      (aging)  (wind-down)
   │             │             │            │                 │         │
 optimize     optimize      optimize     optimize          optimize  optimize
 for          for           for          for               for       for
 learning     iteration     reliability  stability         safe      safe
 speed        speed         & scale      & low-risk change  change    removal
```

| Phase | One-line definition |
|-------|---------------------|
| **Greenfield (0→1)** | Brand new, exploring the problem; nothing in production |
| **Active Build (1→GA)** | Building toward / just past first real users; rapid feature work |
| **Scaling** | Real traffic growing fast; reliability and performance now bite |
| **Mature / Maintenance** | Steady users, slowing feature pace; stability is paramount |
| **Legacy** | Old, business-critical, hard to change, original authors often gone |
| **Sunset** | Being decommissioned or replaced; minimize investment, exit safely |

---

## How to Detect the Phase — Evidence Signals

Read these signals from the repo, git history, and infra. Match the cluster, not a single clue.

| Signal source | Greenfield | Active Build | Scaling | Mature | Legacy | Sunset |
|---------------|-----------|--------------|---------|--------|--------|--------|
| **Git age / commits** | Days–weeks, 1 author | Months, high churn | 1–2 yrs, steady | Years, slowing | Many yrs, sparse | Mostly stopped |
| **Tests** | Few/none | Growing, gaps | Filling critical paths | Broad suite | Brittle/outdated | Frozen |
| **CI/CD** | None/basic | Basic pipeline | Mature, staged | Robust, gated | Old/manual steps | Often frozen |
| **Deps** | Latest | Current | Current-ish | Some lag | Outdated, CVEs | Pinned, EOL |
| **Observability** | None | Basic logs | Metrics+alerts | Full o11y | Partial | Minimal |
| **Docs/ADRs** | Sketch/none | Emerging | Present | Comprehensive | Stale | "Do not touch" notes |
| **Architecture** | In flux | Solidifying | Hardening/splitting | Stable | Ossified | Replaced piecemeal |
| **TODO/FIXME** | Everywhere | Many | Decreasing | Tracked in backlog | Ancient TODOs | Ignored |
| **Prod traffic** | None | First users | Growing fast | Steady, high | Steady, critical | Declining |
| **Release cadence** | N/A | Daily/weekly | Weekly, controlled | Scheduled | Rare, risky | Freeze |

> **Greenfield-vs-Brownfield shortcut**: Is there production traffic and an established
> architecture? **No** → greenfield/active build (optimize for speed of learning). **Yes** →
> brownfield (scaling/mature/legacy — optimize for *not breaking what works*).

---

## Phase-Specific Audit & Build Strategy

What "good" means — and what to prioritize — changes by phase.

### 1. Greenfield (0→1)
- **Optimize for**: learning speed, reversibility, finding product-market fit.
- **Audit lens**: Is the architecture *reversible*? Are foundational choices (data model, auth,
  boundaries) sound? Don't penalize missing tests on throwaway spikes.
- **Acceptable debt**: high — but **only** the prudent/deliberate kind (documented shortcuts).
- **Red flags**: irreversible one-way-door choices made casually (wrong DB, public API frozen
  too early); security basics skipped on anything that will touch real users; no seam to test.
- **Build approach**: thin vertical slices, simplest thing that works, defer abstractions
  (YAGNI). See [architecture-planning.md](./architecture-planning.md).

### 2. Active Build (1→GA)
- **Optimize for**: iteration speed without painting into corners.
- **Audit lens**: Are critical-path features tested? Is auth/security real now that users exist?
  Are module boundaries holding as features pile on?
- **Acceptable debt**: medium — track it; pay down before it compounds.
- **Red flags**: duplication exploding, God objects forming, no tests on money/auth paths,
  copy-paste features diverging.

### 3. Scaling
- **Optimize for**: reliability, performance, and operability under real load.
- **Audit lens**: N+1 queries, missing indexes, unbounded work, no rate limits, single points of
  failure, missing timeouts/retries/circuit breakers, cache correctness, idempotency of writes.
  → [workflow-analysis.md](./workflow-analysis.md), [cross-cutting-analysis.md](./cross-cutting-analysis.md)
- **Acceptable debt**: lower — reliability debt now causes incidents.
- **Red flags**: no observability, manual deploys, shared mutable state under concurrency, no
  load testing, "works at 100 users" assumptions.

### 4. Mature / Maintenance
- **Optimize for**: stability and low-risk change; protect the working system.
- **Audit lens**: test-suite health, dependency freshness/CVEs, dead code, documentation
  accuracy, onboarding friction. Change blast-radius must be small and well-tested.
- **Acceptable debt**: low — but big refactors must justify their risk.
- **Red flags**: creeping dependency rot, flaky tests eroding trust, knowledge concentrated in
  one person, undocumented tribal behavior.

### 5. Legacy
- **Optimize for**: safe change in code you don't fully understand.
- **Audit lens**: Where are the seams? What's covered by *any* test? What's the blast radius of a
  change? Characterization tests before refactoring. Strangler-fig for replacement.
- **Acceptable debt**: it *is* the debt — focus on containment, not perfection.
- **Red flags**: changes with no tests, no rollback, EOL/unpatched dependencies with CVEs,
  "nobody knows how this works," big-bang rewrite temptation (usually a trap).
- **Build approach**: add characterization tests first; change in small reversible steps; wrap,
  don't rewrite, unless justified.

### 6. Sunset
- **Optimize for**: safe removal and data preservation; minimal new investment.
- **Audit lens**: What still depends on this? Data export/migration completeness, security of the
  wind-down (orphaned access, leaked secrets), decommission checklist.
- **Acceptable debt**: N/A — don't invest; just exit safely.
- **Red flags**: hidden consumers still calling it, data not migrated, access/credentials left
  live after shutdown.

---

## Debt Tolerance by Phase

The *same* finding gets a *different* severity depending on phase. Calibrate accordingly.

| Finding | Greenfield | Active Build | Scaling | Mature | Legacy |
|---------|-----------|--------------|---------|--------|--------|
| No tests on a feature | Low | Medium | High | High | Medium* |
| Missing auth check | High | Critical | Critical | Critical | Critical |
| N+1 query | Low | Low | High | Medium | Medium |
| Duplication 8% | Low | Medium | Medium | High | Low* |
| Outdated dep (no CVE) | Info | Low | Low | Medium | Medium |
| Outdated dep (**CVE**) | High | High | Critical | Critical | Critical |
| God class | Low | Medium | High | High | Accept* |
| No observability | Low | Medium | High | High | Medium |

\* Legacy: weigh the **risk of changing** against the risk of leaving it. Sometimes the safest
action is a characterization test + leave-in-place, not a refactor.

> Security findings stay high across **all** phases the moment real users/data exist. Don't
> discount auth, injection, or data-loss risks because the app is "early."

---

## Phase Transition Risks (audit for the *next* phase too)

Many incidents happen because the app entered a new phase but the practices didn't keep up.

| Transition | The trap | What to check |
|-----------|----------|---------------|
| Build → Scaling | "It worked at low volume" | Load tests, indexes, pooling, rate limits, async |
| Scaling → Mature | Velocity habits persist | Change controls, staged rollout, regression suite |
| Mature → Legacy | Knowledge & deps rot silently | Dep freshness, docs, bus-factor, test health |
| Any → Sunset | Forgotten consumers & data | Dependency census, data migration, access teardown |

---

## Phase-Detection Output (put this at the top of the audit)

```
APPLICATION PHASE ASSESSMENT
  Detected phase:   <Greenfield | Active Build | Scaling | Mature | Legacy | Sunset>
  Evidence:         <git age, tests, CI/CD, deps, traffic, observability signals>
  "Good" bar:       <what quality level this phase demands>
  Debt tolerance:   <high | medium | low | exit-only>
  Severity calibration note: <how findings were weighted for this phase>
  Next-phase risks: <what to prepare for>
```

This single block makes the entire audit's severity calibration transparent and defensible.

---

## Sources

- [Martin Fowler: Technical Debt Quadrant](https://martinfowler.com/bliki/TechnicalDebt.html) — prudent vs reckless debt by intent
- [Martin Fowler: Strangler Fig Application](https://martinfowler.com/bliki/StranglerFigApplication.html) — safe legacy replacement
- [Michael Feathers: Working Effectively with Legacy Code](https://martinfowler.com/bliki/CharacterizationTest.html) — characterization tests, seams
- [Martin Fowler: Is High Quality Software Worth the Cost?](https://martinfowler.com/articles/is-quality-worth-cost.html) — quality bar vs stage
- [12factor.net](https://12factor.net/) — readiness signals for scaling
