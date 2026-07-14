---
name: full-audit
description: |
  Complete whole-application audit that systematically discovers every feature in the codebase
  and runs the full feature-audit methodology on each one. Use when: performing a comprehensive
  application audit, onboarding to a new codebase, preparing for a security audit, assessing
  technical debt across the entire system, identifying all bugs and issues across all features,
  producing an audit report for stakeholders, understanding the health of the entire application,
  building a remediation roadmap, doing a pre-release or pre-launch full review, or conducting
  a compliance review. Also use when: finding duplicate code, detecting dead code, analyzing
  code smells, checking development principles (SOLID/DRY/KISS/YAGNI), assessing code reusability,
  tracing workflow completeness, detecting race conditions and concurrency bugs, finding resource
  leaks, identifying copy-paste bugs, measuring cognitive complexity, checking 12-Factor compliance,
  detecting over-engineering, finding speculative generality, auditing AI-generated code quality.
  Combines feature discovery, per-feature deep audit (all 7 phases), advanced bug detection,
  duplicate/waste code analysis, workflow & data flow analysis, reusability & principles assessment,
  cross-cutting system-wide analysis, risk scoring, technical debt quantification, and a
  prioritized remediation roadmap. Outputs a structured audit report with executive summary,
  per-feature findings table, critical issues list, and sprint-ready action plan.
  Trigger on: "full audit", "audit the whole app", "audit entire codebase", "application health
  check", "full codebase review", "technical debt assessment", "find all issues", "comprehensive
  review", "audit all features", "pre-launch audit", "security audit", "compliance review",
  "find duplicate code", "detect dead code", "code smell analysis", "check SOLID principles",
  "DRY violations", "workflow analysis", "find bugs", "code reusability check", "quality audit",
  "detect waste code", "over-engineering check", "cognitive complexity analysis",
  "architecture review", "plan new application", "data flow analysis", "system design",
  "what architecture to use", "monolith vs microservices", "application planning",
  "what phase is this app", "greenfield audit", "brownfield audit", "legacy code audit",
  "is this production ready", "production grade review", "how should I reason about this audit",
  "handle edge cases", "think like a user", "end to end analysis", "how is this connected".
argument-hint: 'Optional scope: "entire app", "backend only", "frontend only", "duplicates only", "bugs only", "architecture only", "plan new app", "what phase", "legacy audit", or a specific module path'
---

# Full Application Audit Skill

> "Neglecting internal quality leads to rapid build-up of cruft. This cruft slows down
> feature development. High internal quality keeps cruft to a minimum, allowing a team to
> add features with less effort, time, and cost." — Martin Fowler

> "Low-quality code has 15× higher defect density and takes 2× longer to change."
> — Tornhill & Borg, 2022 (CodeScene study of 39 proprietary codebases)

A complete, systematic audit of every feature in an application. This skill wraps the
**feature-audit** methodology and applies it to the entire codebase — not just one feature.
The result is a structured audit report with risk scores, a severity-ranked findings table,
and a sprint-ready remediation roadmap.

**What makes this audit comprehensive**: Beyond security and testing, this skill detects
duplicate code, dead code, code smells, development principle violations (SOLID/DRY/KISS/YAGNI),
workflow gaps, concurrency bugs, resource leaks, over-engineering, and AI-generated code issues.

---

## 🧠 Expert Audit Reasoning Operating System — Read This First

**This is what makes any model — large or small — audit like a principal engineer.** Weak audits
are shallow, hallucinated, or miscalibrated. Run every audit through the **MAP · PROBE · PROVE ·
RANK · ROOT · ROADMAP** loop:

```
 MAP ─→ PROBE ─→ PROVE ─→ RANK ─→ ROOT ─→ ROADMAP
 model   cover    cite     score   trace   sequence
 the     every    file:    by real  to     by risk
 system  surface  line     impact   cause  × effort
(ground  (miss    (no      (no      & blast (no new
 truth)   nothing) guesses) vibes)   radius  risk)
```

**Prime directive**: *No finding without evidence (file:line); no severity without justification.*
At every step, **gain ground truth** — read the actual code before you claim anything. State
**confidence** per finding; never inflate a Low-confidence hunch into a firm finding (false
positives destroy trust in the whole audit).

> **Full protocol** (coverage matrix, confidence calibration, severity grid, root-cause/5-whys,
> auditor bias checklist, stopping conditions): see
> [llm-reasoning-protocol.md](./references/llm-reasoning-protocol.md). **Read it first.**

---

## How This Skill Relates to `feature-audit`

```
full-audit
├── Step 0: Detect the application's lifecycle phase (sets the quality bar)
│       └── → reference: application-phase-detection.md
├── Step A: Architecture & Planning Assessment (for new apps or architecture review)
│       └── → reference: architecture-planning.md
├── Step 1: Discover ALL features in the codebase
│       └── → reference: feature-discovery.md
├── Step 2: For EACH feature → run complete feature-audit (7 phases)
│       └── → delegates to: feature-audit skill (all 7 phases)
│       └── → reference: audit-runner.md
├── Step 3: Advanced Bug Detection Deep Scan
│       └── → reference: bug-detection-advanced.md
├── Step 4: Duplicate Code & Waste Code Analysis
│       └── → reference: duplicate-waste-analysis.md
├── Step 5: Workflow & Data Flow Analysis
│       └── → reference: workflow-analysis.md
├── Step 6: Reusability & Development Principles Assessment
│       └── → reference: reusability-principles.md
├── Step 7: Cross-cutting system-wide analysis
│       └── → reference: cross-cutting-analysis.md
├── Step 8: Score and classify every finding
│       └── → reference: scoring-matrix.md
├── Step 9: Quantify technical debt
│       └── → reference: technical-debt-assessment.md
├── Step 10: Build remediation roadmap
│       └── → reference: remediation-roadmap.md
└── Step 11: Compile the audit report
        └── → reference: report-template.md
```

---

## Quick Reference

| Step | Reference File | Purpose |
|------|---------------|---------|
| ★ — Reasoning OS | [llm-reasoning-protocol.md](./references/llm-reasoning-protocol.md) | How to audit at expert level on any model (read first) |
| 0 — Phase Detection | [application-phase-detection.md](./references/application-phase-detection.md) | Detect lifecycle phase; calibrate the quality bar |
| 1 — Feature Discovery | [feature-discovery.md](./references/feature-discovery.md) | Map every feature in the codebase |
| 2 — Audit Runner | [audit-runner.md](./references/audit-runner.md) | Apply feature-audit to each feature systematically |
| 3 — Bug Detection | [bug-detection-advanced.md](./references/bug-detection-advanced.md) | Deep scan for concurrency bugs, leaks, logic errors |
| 4 — Duplicate & Waste | [duplicate-waste-analysis.md](./references/duplicate-waste-analysis.md) | Find clones, dead code, speculative generality |
| 5 — Workflow Analysis | [workflow-analysis.md](./references/workflow-analysis.md) | Trace data flows, error propagation, async lifecycle |
| 6 — Reusability & Principles | [reusability-principles.md](./references/reusability-principles.md) | SOLID/DRY/KISS/YAGNI/12-Factor compliance |
| 7 — Cross-Cutting Analysis | [cross-cutting-analysis.md](./references/cross-cutting-analysis.md) | System-wide patterns, shared code, architecture |
| 8 — Scoring Matrix | [scoring-matrix.md](./references/scoring-matrix.md) | Risk score every finding: Critical/High/Medium/Low |
| 9 — Technical Debt | [technical-debt-assessment.md](./references/technical-debt-assessment.md) | Quantify and classify all debt |
| 10 — Remediation Roadmap | [remediation-roadmap.md](./references/remediation-roadmap.md) | Prioritized sprint-ready action plan |
| 11 — Report Template | [report-template.md](./references/report-template.md) | Structure the final audit report |
| A — Architecture & Planning | [architecture-planning.md](./references/architecture-planning.md) | Architecture decisions, data flow, app type patterns |

---

## ⚡ Copilot Smart Routing — Read Only What's Needed

**CRITICAL**: Do NOT read all reference files for every request. Match the user's intent to the
right subset of steps:

| User Intent / Task Size | Steps to Execute | Reference Files to Read |
|------------------------|------------------|------------------------|
| **"Full audit" / "audit entire codebase"** | All steps (0–11) | ALL references |
| **"What phase/stage is this app?" / "greenfield/legacy/brownfield audit"** | 0 only | application-phase-detection |
| **"How should I reason about this audit" / "audit methodology"** | Reasoning OS | llm-reasoning-protocol |
| **"Find bugs" / "what's broken"** | 1 → 3 → 8 | feature-discovery, bug-detection-advanced, scoring-matrix |
| **"Find duplicate code" / "dead code"** | 4 only | duplicate-waste-analysis |
| **"Check architecture" / "data flow"** | A + 5 + 7 | architecture-planning, workflow-analysis, cross-cutting-analysis |
| **"Technical debt" / "code quality"** | 6 + 9 | reusability-principles, technical-debt-assessment |
| **"Security audit" / "OWASP check"** | 2 (Phase 6 only) + 7 | audit-runner (security focus), cross-cutting-analysis |
| **"Pre-launch review" / "ready to ship?"** | 1 → 3 → 5 → 7 → 8 | feature-discovery, bug-detection-advanced, workflow-analysis, cross-cutting-analysis, scoring-matrix |
| **"Onboarding" / "understand this codebase"** | 0 + 1 + A + 7 | application-phase-detection, feature-discovery, architecture-planning, cross-cutting-analysis |
| **"Plan new application" / "architecture decisions"** | A only | architecture-planning |
| **"Build remediation plan" / "what to fix first"** | 8 → 9 → 10 | scoring-matrix, technical-debt-assessment, remediation-roadmap |
| **"Workflow analysis" / "data flow check"** | 5 only | workflow-analysis |
| **"SOLID/DRY check" / "principles compliance"** | 6 only | reusability-principles |
| **"Generate audit report"** | 11 only | report-template |

**Rule**: For targeted queries, read 1-3 files. For full audits, read all. Never read everything for a focused question.
For ANY audit, the reasoning protocol and phase detection apply first — they calibrate every later severity.

---

## Copilot Execution Strategy

When executing this skill as an AI agent, follow this optimized sequence:

### Phase A — Automated Tooling First (Run Before Manual Analysis)
```bash
# Run these tools first — they provide data for all subsequent steps
# 1. Dependency vulnerabilities
npm audit 2>/dev/null || pip-audit 2>/dev/null || cargo audit 2>/dev/null

# 2. Duplicate code detection
npx jscpd ./src --min-lines 5 --min-tokens 50 --reporters consoleFull 2>/dev/null

# 3. Dead code / unused exports
npx ts-prune 2>/dev/null || python -m vulture ./src 2>/dev/null

# 4. Complexity hotspots
npx eslint --rule '{"complexity": ["warn", 10]}' ./src 2>/dev/null

# 5. Test coverage
npm test -- --coverage 2>/dev/null || pytest --cov=./src --cov-report=term-missing 2>/dev/null

# 6. Outdated dependencies
npm outdated 2>/dev/null || pip list --outdated 2>/dev/null
```

### Phase B — Discovery (Use Search Tools)
- Use `grep_search` for route/endpoint mapping, job discovery, event handlers
- Use `file_search` for page/view files, test files, config files
- Use `semantic_search` for feature understanding and relationship mapping

### Phase C — Deep Analysis (Use Read + Grep)
- Read high-churn files first (they contain the most bugs)
- Read shared utilities (quality multiplies across codebase)
- Read auth/security code (highest impact area)

### Phase D — Parallel Analysis Tracks
These analyses are independent — run them in parallel when possible:
- Track A: Bug detection (Step 3)
- Track B: Duplication scan (Step 4)
- Track C: Workflow tracing (Step 5)
- Track D: Principles check (Step 6)

### Phase E — Synthesis
- Cross-cutting analysis combines findings from all tracks
- Score all findings uniformly
- Build remediation roadmap from scored findings

---

## Step 0 — Application Phase Detection

**Goal**: Before judging anything, detect what lifecycle phase the application is in. The *same*
finding has a *different* severity depending on the phase — a missing test suite is fine in a
day-one prototype and a fire in a payment platform. This single step makes the entire audit's
severity calibration defensible.

**Detect the phase from evidence** (git age, tests, CI/CD, dependency freshness, observability,
production traffic, release cadence):

| Phase | Optimize for | Detect by |
|-------|-------------|-----------|
| **Greenfield (0→1)** | Learning speed, reversibility | Days-old repo, no prod traffic, architecture in flux |
| **Active Build (1→GA)** | Iteration without painting into corners | High churn, growing tests, first users |
| **Scaling** | Reliability & performance under load | Growing traffic, metrics/alerts, perf work |
| **Mature / Maintenance** | Stability, low-risk change | Slowing commits, broad tests, scheduled releases |
| **Legacy** | Safe change in code you don't fully grasp | Old, sparse commits, outdated deps, original authors gone |
| **Sunset** | Safe removal, data preservation | Declining traffic, freeze, "do not touch" notes |

**Output the phase assessment block** at the top of the audit so all later severities are
calibrated to it. Security findings stay high across **all** phases once real users/data exist.

> **Full guide** (detection signal matrix, debt tolerance by phase, phase-transition risks,
> phase-specific audit strategy): see [application-phase-detection.md](./references/application-phase-detection.md)

---

## Step 1 — Feature Discovery

**Goal**: Build a complete inventory of every feature in the application before auditing anything.

A "feature" is any discrete unit of functionality that a user or system can invoke:
- A user-facing workflow (login, checkout, search, profile management)
- An API endpoint or group of related endpoints
- A background job or scheduled task
- An event handler or webhook
- An administrative function
- A batch process or data pipeline

**Discovery approach** (see [feature-discovery.md](./references/feature-discovery.md) for full detail):

```bash
# 1. Map all routes/endpoints
grep -rn "app\.\(get\|post\|put\|delete\|patch\)\|router\.\|@app\.route\|@GetMapping\|@PostMapping" ./src

# 2. Map all UI pages and views
find ./src -name "*.page.*" -o -name "*.view.*" -o -name "pages/" | head -40

# 3. Map all background jobs and scheduled tasks
grep -rn "cron\|schedule\|@Scheduled\|celery\|sidekiq\|bull\|Worker\|Job\b" ./src

# 4. Map all event/webhook handlers
grep -rn "on(\|addEventListener\|@EventListener\|subscribe\|handler\b" ./src

# 5. Map all admin/internal features
grep -rn "admin\|internal\|management\|console\|dashboard" ./src --include="*.ts" --include="*.py"
```

**Output**: Feature Inventory Table (see Step 11 / report-template.md)

---

## Step 2 — Per-Feature Audit (Applying feature-audit to Each)

**Goal**: For each feature in the inventory, run the complete 7-phase feature-audit.

This step is the heart of the full-audit. For every feature discovered in Step 1:

```
Feature: [Feature Name]
─────────────────────────────────────────────────────────────
Phase 1 — Discovery:     Read the feature end-to-end, git history, TODO/FIXME scan
Phase 2 — Impact:        Map all files/layers this feature touches
Phase 3 — Implementation: Code quality, SOLID, complexity, naming, error handling
Phase 4 — Testing:       Test pyramid coverage assessment
Phase 5 — UX:            User journey, states, accessibility
Phase 6 — Security:      OWASP 2025 A01–A10 applied to this feature
Phase 7 — Code Review:   PR/review readiness, documentation
─────────────────────────────────────────────────────────────
Output: Feature Audit Card (filled in scoring-matrix.md format)
```

> **Full procedure**: See [audit-runner.md](./references/audit-runner.md) for how to
> efficiently run feature-audit across many features including sequencing, templates,
> and time estimates.

---

## Step 3 — Advanced Bug Detection Deep Scan

**Goal**: Systematically detect bugs that per-feature audits often miss — concurrency issues,
resource leaks, state machine violations, and subtle logic errors.

| Bug Category | Detection Method |
|-------------|-----------------|
| **Race conditions** | Find shared mutable state accessed without synchronization |
| **Resource leaks** | Track open/close pairs (connections, files, streams) |
| **Null propagation** | Trace nullable values through call chains |
| **Error swallowing** | Find catch blocks with empty bodies or only logging |
| **Copy-paste bugs** | Find near-duplicate code with subtle differences |
| **State violations** | Map valid state transitions, find invalid paths |
| **Temporal coupling** | Find operations that must execute in order but aren't enforced |
| **Integer overflow** | Find arithmetic on user-controlled values without bounds |
| **Logic inversions** | Find negation errors, wrong comparison operators |
| **API contract violations** | Compare documented behavior with actual implementation |

> **Full guide with detection patterns per language**: See [bug-detection-advanced.md](./references/bug-detection-advanced.md)

---

## Step 4 — Duplicate Code & Waste Code Analysis

**Goal**: Identify all code that is duplicated, dead, or speculative — reducing maintenance
burden and attack surface.

| Analysis Type | Threshold | Tool |
|--------------|-----------|------|
| **Exact clones** (Type 1) | Any occurrence | jscpd, PMD CPD |
| **Renamed clones** (Type 2) | Any occurrence | jscpd, Semgrep |
| **Gapped clones** (Type 3) | > 10 lines | jscpd --min-lines 10 |
| **Semantic clones** (Type 4) | Manual review | Semantic analysis |
| **Dead code** | Never called | ts-prune, vulture |
| **Speculative generality** | Unused abstractions | Manual + ts-prune |
| **Feature flag graveyards** | Flags > 90 days old | grep + git log |
| **Commented-out code** | Any block > 3 lines | grep patterns |

**Duplication health thresholds**:
- ✅ < 3% duplication — Excellent
- 🟡 3–5% duplication — Acceptable, monitor
- 🔴 > 5% duplication — Action needed

> **Full guide**: See [duplicate-waste-analysis.md](./references/duplicate-waste-analysis.md)

---

## Step 5 — Workflow & Data Flow Analysis

**Goal**: Trace complete user workflows end-to-end, verifying data integrity, error propagation,
and async operation lifecycle at every step.

| Analysis | What to Verify |
|---------|---------------|
| **Happy path completeness** | Does the flow work from trigger to completion? |
| **Error path completeness** | Is every possible error handled and surfaced to the user? |
| **Data flow integrity** | Is data validated, transformed, and stored correctly at each boundary? |
| **Async lifecycle** | Are all promises awaited? Are there dangling operations? |
| **Transaction boundaries** | Can partial writes occur? Are rollbacks handled? |
| **Retry safety** | Are operations idempotent? Can retries cause duplicates? |
| **Event flow** | Are events emitted and consumed symmetrically? Any orphans? |
| **Cascading failures** | Does one service failure bring down the whole system? |

> **Full guide**: See [workflow-analysis.md](./references/workflow-analysis.md)

---

## Step 6 — Reusability & Development Principles Assessment

**Goal**: Evaluate adherence to proven software engineering principles that determine
long-term maintainability and team velocity.

| Principle | What to Check |
|----------|--------------|
| **Single Responsibility (S)** | Does each module/class do exactly one thing? |
| **Open/Closed (O)** | Can behavior be extended without modifying existing code? |
| **Liskov Substitution (L)** | Can subtypes replace their base types safely? |
| **Interface Segregation (I)** | Are interfaces focused, or do clients depend on methods they don't use? |
| **Dependency Inversion (D)** | Do high-level modules depend on abstractions, not concretions? |
| **DRY** | Is logic duplicated that should be extracted into shared utilities? |
| **KISS** | Is code more complex than the problem requires? Over-engineered? |
| **YAGNI** | Are there features/abstractions built for hypothetical future needs? |
| **12-Factor** | Does the app follow cloud-native best practices? |
| **Cognitive Complexity** | Can a developer understand each function in < 30 seconds? |

> **Full guide with per-principle checklist**: See [reusability-principles.md](./references/reusability-principles.md)

---

## Step 7 — Cross-Cutting System Analysis

**Goal**: Identify issues that span multiple features or affect the whole system.

These problems are often invisible when looking at one feature at a time:

| Analysis Area | What to Look For |
|--------------|-----------------|
| **Architecture** | Circular dependencies, layer violations, God classes |
| **Shared code quality** | Utility/helper modules used everywhere — quality of these has outsized impact |
| **Authentication/Authorization** | Is auth consistent across all features? Any gaps? |
| **Error handling patterns** | Is error handling consistent? Any unhandled promise rejections or uncaught exceptions? |
| **Logging consistency** | Are all features logging consistently? Any blind spots? |
| **Dependency health** | Outdated dependencies, known CVEs across all packages |
| **Test infrastructure** | Are tests organized consistently? Shared fixtures accurate? |
| **Configuration sprawl** | Env vars, feature flags, config — are they documented and consistent? |
| **Performance hotspots** | N+1 queries, missing indexes, large payload patterns |
| **Dead code** | Unused functions, unused routes, unused components |
| **AI-generated code quality** | Hallucinated imports, phantom packages, inconsistent patterns |
| **Duplication hotspots** | Which patterns repeat most across features? |

> **Full guide**: See [cross-cutting-analysis.md](./references/cross-cutting-analysis.md)

---

## Step 8 — Score and Classify Every Finding

**Goal**: Assign severity to every finding so effort is focused on what matters most.

Every finding from Steps 2–7 gets a risk score:

| Severity | Definition | Response Time |
|----------|-----------|--------------|
| **Critical** | Security vulnerability exploitable by attacker, data loss risk, or system-down bug | Fix before next deploy |
| **High** | Feature broken for users, significant security risk, severe UX failure, no tests on critical path | Fix in current sprint |
| **Medium** | Feature partially broken, OWASP risk present but not immediately exploitable, UX degraded | Fix in next 1–2 sprints |
| **Low** | Code quality issue, minor UX inconsistency, missing documentation, test gap on non-critical path | Backlog / next quarter |
| **Informational** | Observation, best practice suggestion, no active risk | Consider when convenient |

> **Full scoring rubric with examples**: See [scoring-matrix.md](./references/scoring-matrix.md).
> **Calibrate severity to the application phase** (Step 0): the same finding can be Low in a
> throwaway prototype and Critical in a payment platform. Security findings stay high in every
> phase once real users or data exist.

---

## Step 9 — Technical Debt Assessment

**Goal**: Quantify the debt so business stakeholders understand the cost of not addressing it.

Based on Martin Fowler's Technical Debt model:
- **Interest**: The extra time it takes to add features because of existing cruft
- **Principal**: The effort required to remove the cruft
- Low-quality code has **15× higher defect density** and takes **2× longer** to change (Tornhill & Borg, 2022)

Debt is classified by quadrant (Fowler's Technical Debt Quadrant):
- **Reckless + Deliberate**: "We don't have time for design" → highest interest
- **Reckless + Inadvertent**: "What's layering?" → systematic quality problem
- **Prudent + Deliberate**: "Ship now, document the debt" → manageable if tracked
- **Prudent + Inadvertent**: "We now know how we should have done it" → normal team learning

**Additional debt categories** (2026):
- **Duplication Debt**: Cost of maintaining multiple copies of the same logic
- **Principle Debt**: Cost of SOLID/DRY violations compounding over time
- **Workflow Debt**: Incomplete error handling, missing edge cases that cause incidents
- **AI-Generated Debt**: Low-quality AI-written code that passed superficial review

> **Full assessment method**: See [technical-debt-assessment.md](./references/technical-debt-assessment.md)

---

## Step 10 — Remediation Roadmap

**Goal**: Turn audit findings into a prioritized, sprint-ready action plan.

Findings are organized into tracks:

| Track | Content | Timeline |
|-------|---------|---------|
| **Track 0: Critical** | Security vulnerabilities, data loss risks, broken critical paths | This sprint (blocking) |
| **Track 1: High Priority** | Major functional issues, high OWASP risks, missing critical tests | Next 1–2 sprints |
| **Track 2: Medium Priority** | Quality improvements, UX fixes, medium security issues | Next quarter |
| **Track 3: Technical Debt** | Structural improvements, refactors, test coverage expansion | Ongoing — 20% capacity |
| **Track 4: Enhancements** | Identified improvements beyond fixing issues | Roadmap / future |

> **Full roadmap building guide**: See [remediation-roadmap.md](./references/remediation-roadmap.md)

---

## Step 11 — Audit Report

**Goal**: Compile all findings into a clear, actionable report for developers and stakeholders.

The report contains:
1. **Executive Summary** — Application health score, top 5 risks, recommended immediate actions
2. **Feature Inventory** — Complete list of features audited
3. **Findings Table** — All issues sorted by severity with per-feature breakdown
4. **Bug Detection Results** — Race conditions, leaks, logic errors found
5. **Duplicate Code Report** — Duplication percentage, clone map, dead code inventory
6. **Workflow Analysis Results** — Data flow gaps, async issues, transaction problems
7. **Principles Compliance** — SOLID/DRY/KISS/YAGNI scorecard per module
8. **Security Audit Results** — OWASP 2025 coverage with pass/fail per risk category
9. **Technical Debt Register** — Classified debt with estimated remediation effort
10. **Remediation Roadmap** — Sprint-organized action plan
11. **Appendix** — Raw audit notes per feature

> **Full report template**: See [report-template.md](./references/report-template.md)

---

## Audit Scope Options

Adapt the scope based on your constraints:

| Scope | What to Audit | Typical Time |
|-------|-------------|-------------|
| **Full application** | All features, all steps (1–11) | Days to weeks |
| **Security focus** | Steps 2 (Phase 6 only) + Step 7 cross-cutting auth | 1–2 days |
| **Critical path only** | Top 5–10 most-used features, all phases | 1–2 days |
| **Duplicates & waste** | Steps 4 + 6 (DRY analysis + duplication scan) | Half-day |
| **Bug hunt** | Steps 3 + 5 (bug detection + workflow analysis) | 1–2 days |
| **New developer onboarding** | Steps 1 + 2 (Phase 1–2 only) | Half-day |
| **Pre-launch review** | All phases for launch-blocking features | 1 week |
| **Technical debt snapshot** | Steps 4 + 6 + 9 (duplication + principles + debt) | 1–2 days |
| **Principles compliance** | Step 6 (SOLID/DRY/KISS/YAGNI across all features) | 1 day |

---

## Audit Health Score

At the end of the audit, compute a Health Score for each feature and the whole application:

```
Application Health Score = (
  Code Quality Score     × 0.20
  + Test Coverage Score  × 0.15
  + Security Score       × 0.25
  + Bug Density Score    × 0.15    (inverse: fewer bugs = higher score)
  + Duplication Score    × 0.10    (inverse: less duplication = higher score)
  + Principles Score     × 0.10    (SOLID/DRY/KISS compliance)
  + Documentation Score  × 0.05
) × 100
```

**Per-dimension scoring** (each dimension scored 0–100):
- **Code Quality**: Cognitive complexity, naming, consistency, error handling
- **Test Coverage**: Line coverage %, branch coverage %, critical path coverage
- **Security**: OWASP Top 10 pass rate, dependency CVE count, secret exposure
- **Bug Density**: Bugs found per 1000 LOC (inverse scale: 0 bugs = 100 score)
- **Duplication**: % of codebase that is duplicated (inverse: 0% = 100, >10% = 0)
- **Principles**: SOLID compliance rate, DRY score, KISS/YAGNI violations count
- **Documentation**: API docs, README, inline comments quality

| Score | Health Rating | Meaning |
|-------|-------------|---------|
| 90–100 | ✅ Excellent | Well-maintained, ready for production |
| 75–89 | 🟡 Good | Minor issues, low risk |
| 60–74 | 🟠 Fair | Notable gaps, medium risk, action needed this quarter |
| 40–59 | 🔴 Poor | Significant issues, high risk, action needed this sprint |
| 0–39 | 💀 Critical | Major issues, system at risk, immediate action required |

---

## Development Principles Quick Reference

These principles underpin the entire audit methodology:

| Principle | Rule of Thumb | Violation Signal |
|----------|--------------|-----------------|
| **SRP** | "A class should have only one reason to change" | File > 300 lines, > 5 public methods |
| **OCP** | "Open for extension, closed for modification" | Switch statements growing with each feature |
| **LSP** | "Subtypes must be substitutable for their base types" | Type checks or casts after calling base |
| **ISP** | "No client should depend on methods it doesn't use" | Interfaces > 5 methods, many no-op implementations |
| **DIP** | "Depend on abstractions, not concretions" | `new ConcreteClass()` in business logic |
| **DRY** | "Every piece of knowledge has a single representation" | Same logic in 3+ places |
| **KISS** | "The simplest solution that works" | Abstractions with one implementor |
| **YAGNI** | "You aren't gonna need it" | Unused parameters, empty extension points |
| **12-Factor** | "Treat config as environment, logs as streams" | Hardcoded URLs, file-based logging |
| **Boy Scout** | "Leave the code cleaner than you found it" | High churn files getting worse over time |

---

## Sources

- [Martin Fowler: Software Architecture Guide](https://martinfowler.com/architecture/) — Architecture decisions, patterns, enterprise
- [OWASP ASVS 5.0.0](https://owasp.org/www-project-application-security-verification-standard/) — Application security verification standard
- [OWASP Top 10:2025](https://owasp.org/Top10/2025/) — Current top web security risks
- [Martin Fowler: Is High Quality Software Worth the Cost?](https://martinfowler.com/articles/is-quality-worth-cost.html) — Technical debt economics
- [Martin Fowler: Technical Debt](https://martinfowler.com/bliki/TechnicalDebt.html) — Debt quadrant model
- [Martin Fowler: Microservices](https://martinfowler.com/microservices/) — When and how to use microservices
- [Google Engineering Practices](https://google.github.io/eng-practices/) — Code review and quality standards
- [Tornhill & Borg (2022)](https://arxiv.org/abs/2203.04374) — Quantified impact of code quality on defects and velocity
- [Refactoring.Guru: Code Smells](https://refactoring.guru/refactoring/smells) — Complete code smell taxonomy
- [SonarSource: Cognitive Complexity](https://www.sonarsource.com/learn/cognitive-complexity/) — Human-readable complexity metric
- [SonarSource: Code Quality 2026](https://www.sonarsource.com/solutions/clean-code/) — Modern quality standards in the AI age
- [12factor.net](https://12factor.net/) — Cloud-native application methodology
- [DORA Metrics](https://dora.dev/) — Elite team performance indicators
- [Semgrep](https://semgrep.dev/) — Pattern-based static analysis for custom rules
- [SmartBear Study](https://smartbear.com/learn/code-review/best-practices-for-peer-code-review/) — Review effectiveness drops past 400 LOC
- [LinearB Research](https://linearb.io/blog/engineering-metrics-benchmarks-what-makes-elite-teams/) — Elite teams: < 7h PR pickup, < 225 LOC per PR
- [C4 Model](https://c4model.com/) — Visualizing software architecture at 4 levels
- [ADR (Architecture Decision Records)](https://adr.github.io/) — Documenting architecture decisions
- feature-audit skill — The per-feature audit methodology this skill orchestrates
