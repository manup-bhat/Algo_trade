# Audit Runner — Efficiently Executing a Full Codebase Audit

The full-audit process audits every feature in a codebase using the feature-audit methodology.
This file describes how to run that process efficiently, without burning out or missing coverage.

---

## The Core Challenge

A full audit is not a single task. It is a project. Treating it like a single task leads to:
- Starting deep, running out of time, leaving 80% uncovered
- Inconsistent depth across features ("I was tired by Feature #12")
- No traceability of what was audited vs. skipped

**Solution**: Treat the audit as a sprint. Plan capacity. Track progress. Timebox each feature.

---

## Audit Sizing — Time Per Feature

Use this table to estimate total audit time before starting.

| Feature Complexity | Typical Audit Time | When It Applies |
|-------------------|-------------------|----------------|
| Trivial (read-only, single file) | 15–30 min | Config pages, static content, simple list views |
| Simple (1–3 files, well-tested) | 30–60 min | CRUD endpoints, utility commands, single-purpose workers |
| Moderate (cross-layer, some business logic) | 1–2 hours | Feature with service + storage + tests |
| Complex (multi-component, auth, events) | 2–4 hours | Payment flow, user auth, multi-step workflows |
| Critical (high-risk, high-usage) | 4–8 hours | Core API, auth system, data pipeline, primary domain model |

**Formula**:
```
Total Audit Estimate = Σ (feature_complexity_hours × 1.3 overhead factor)
```

The 1.3× factor accounts for setup time, context-switching, note-taking, and dead-ends.

---

## Audit Execution Phases

For each feature, apply the feature-audit phases in this order:

| Phase | Reference File | Min Time | Can Skip? |
|-------|---------------|----------|-----------|
| 1. Discovery | pre-implementation.md | 15 min | Never |
| 2. Impact Analysis | impact-analysis.md | 15 min | Never |
| 3. Code Quality | implementation-guide.md | 20 min | Low-risk features |
| 3B. Bug Detection | bug-detection.md | 20 min | Low-risk features |
| 4. Testing | testing-strategy.md | 20 min | Never |
| 5. Consumer Experience | ux-checklist.md | 15 min | Headless services |
| 6. Security | security-checklist.md | 20 min | Never |
| 7. Code Review | code-review.md | 10 min | Never |

**Minimum viable audit** (for low-risk features): Phases 1, 2, 4, 6, 7 only.
**Full audit** (for high-risk features): All phases.

---

## Batching and Sequencing

### Sequence by Risk, Not by File System Order

Prioritize features in this order:
1. **Authentication / Authorization** — failure here is catastrophic
2. **Payment / billing / financial** — failure here has direct financial impact
3. **Data export / bulk operations** — high exfiltration risk
4. **User data mutation** — any write of PII or sensitive records
5. **Public-facing APIs** — highest attack surface
6. **Background jobs** — silent failure risk
7. **Internal tooling / admin** — lower risk, but often under-secured
8. **UI-only features** — typically lowest risk

### Group Related Features

Audit related features back-to-back. The context from one feature speeds up the next:
- All auth-related features together (login, logout, password reset, MFA, sessions)
- All data model features together (user profile, settings, preferences)
- All API endpoints for the same domain together

---

## Audit Log Template

Track every feature you audit. Create a row per feature:

```markdown
| # | Feature | Entry Point | Risk | Phases Done | Findings | Status |
|---|---------|-------------|------|-------------|----------|--------|
| 1 | User login | POST /auth/login | Critical | 1,2,3,4,5,6,7 | 2 findings | Complete |
| 2 | Password reset | POST /auth/reset | High | 1,2,3,4,5,6,7 | 0 findings | Complete |
| 3 | Export CSV | GET /export/users.csv | High | 1,2,6 | 1 critical | In Progress |
| 4 | Update profile | PUT /users/:id | Medium | 1,2 | — | Pending |
```

---

## Pause and Escalate Criteria

Stop the current feature audit and escalate immediately if you find:

| Finding | Action |
|---------|--------|
| **Authentication bypass** | Stop audit; file Critical finding; notify team immediately |
| **SQL / command injection** | Stop audit; file Critical finding; notify team |
| **Exposed secrets in source code** | Stop audit; rotate credentials immediately; then file Critical |
| **IDOR / broken object-level auth** | Stop audit; file Critical finding; notify team |
| **Data exfiltration vector** | Stop audit; file Critical finding; notify team |

Do not continue auditing other features until Critical findings have been triaged. A critical
finding may indicate a systemic issue that affects many features.

---

## Keeping Audit Quality High Over Time

### Avoid Audit Fatigue

- Audit for no more than 2–3 hours consecutively. Take breaks.
- Alternate between high-focus (security, logic) and lower-focus (docs, naming) phases.
- Work with a partner on critical features — two reviewers catch more than one.

### Quality Calibration

After every 5 features, review your previous findings:
- Are findings consistent in severity scoring? (Use scoring-matrix.md)
- Are you applying all phases, or starting to skip steps?
- Is your finding format consistent enough for the final report?

### Bias Check

Be aware of these common audit biases:
- **Availability bias**: Focusing only on code you know well and skimming unfamiliar areas
- **Optimism bias**: Assuming a feature is "probably fine" before checking
- **Fatigue bias**: Lower severity ratings for late-audit features because you're tired
- **Complexity blindness**: Skipping complex code because it's hard to follow

Mitigation: Use checklists. Don't rely on impression alone.

---

## Copilot / AI Agent Execution Strategy

When this audit is executed by an AI coding agent (GitHub Copilot, etc.), follow this
optimized execution pattern for maximum efficiency and coverage.

### Phase 1: Automated Tooling First (5 minutes)

Run automated tools BEFORE any manual analysis. Their output feeds all subsequent steps:

```bash
# 1. Get project structure overview
find ./src -type f -name "*.ts" -o -name "*.py" -o -name "*.go" -o -name "*.java" | wc -l
find ./src -type f | head -50

# 2. Run vulnerability scan
npm audit --json 2>/dev/null | head -50
pip-audit 2>/dev/null | head -30

# 3. Run duplication detection
npx jscpd ./src --min-lines 5 --min-tokens 50 --reporters consoleFull 2>/dev/null | tail -30

# 4. Run dead code detection
npx ts-prune 2>/dev/null | head -30
python -m vulture ./src 2>/dev/null | head -30

# 5. Get test coverage
npm test -- --coverage --silent 2>/dev/null | tail -20
pytest --cov=./src --cov-report=term-missing --quiet 2>/dev/null | tail -30

# 6. Check outdated dependencies
npm outdated 2>/dev/null | head -20
pip list --outdated 2>/dev/null | head -20

# 7. Circular dependency check
npx madge --circular ./src 2>/dev/null
```

### Phase 2: Discovery via Search Tools (10 minutes)

Use `grep_search` and `file_search` (faster than terminal commands for AI agents):

1. **Route/endpoint mapping**: Search for route definitions patterns
2. **Page/view mapping**: Search for page files by naming convention
3. **Job/worker mapping**: Search for scheduled task patterns
4. **Config mapping**: Search for environment variable usage

### Phase 3: Deep Analysis — Read High-Impact Files First

Priority order for reading files:
1. **Auth/security code** — highest impact if broken
2. **Shared utilities** — quality multiplies across system
3. **High-churn files** (from git log) — most likely to have bugs
4. **Files with TODO/FIXME** — known unresolved issues
5. **Entry points** (main, index, app) — understand architecture
6. **Configuration** — understand deployment environment

### Phase 4: Parallel Analysis Tracks

These analyses are independent — run them in any order:

| Track | Steps | Key Tool |
|-------|-------|----------|
| A: Security | OWASP Top 10 check | grep_search for patterns |
| B: Bugs | Race conditions, leaks, null propagation | read_file + grep_search |
| C: Duplication | Clone detection, dead code | Terminal (jscpd, ts-prune) |
| D: Principles | SOLID/DRY/KISS compliance | read_file + file structure |
| E: Workflow | Error path completeness | read_file tracing |

### Phase 5: Report Synthesis

After all analysis is complete:
1. Compile all findings into the report template
2. Score each finding using scoring-matrix.md
3. Calculate health score
4. Build remediation roadmap (Track 0-4)
5. Present executive summary first, details in appendix

### AI Agent Optimization Tips

- **Search before read**: Use `grep_search` to find relevant files before reading entire files
- **Read in bulk**: Read 100+ lines at a time to understand context
- **Prioritize breadth over depth initially**: Scan all features at surface level, then deep-dive high-risk
- **Use terminal tools for data**: jscpd, ts-prune, npm audit generate structured output faster than manual reading
- **Pattern recognition**: Once you find one instance of a bug pattern, grep for ALL instances
- **Cross-reference**: After finding a security issue, check if the same pattern exists elsewhere
- **Don't re-read**: If you've already read a file, reference your notes — don't read it again

---

## Automated Tooling Integration

### Pre-Audit Tooling Checklist

Run these tools before starting manual review. Check output and use it throughout the audit:

| Tool | Purpose | Install | Run Command |
|------|---------|---------|-------------|
| **npm audit** / **pip-audit** | Known vulnerabilities | Built-in / `pip install pip-audit` | `npm audit` / `pip-audit` |
| **jscpd** | Code duplication | `npm i -g jscpd` | `jscpd ./src --threshold 3` |
| **ts-prune** | Dead TypeScript exports | `npm i -g ts-prune` | `ts-prune` |
| **vulture** | Dead Python code | `pip install vulture` | `vulture ./src` |
| **depcheck** | Unused dependencies | `npm i -g depcheck` | `depcheck` |
| **madge** | Circular dependencies | `npm i -g madge` | `madge --circular ./src` |
| **ESLint (complexity)** | Complexity hotspots | Project dependency | `eslint --rule '{"complexity":["warn",10]}'` |
| **radon** | Python complexity | `pip install radon` | `radon cc ./src -s -n C` |
| **Semgrep** | Custom pattern detection | `pip install semgrep` | `semgrep --config=auto ./src` |
| **unimported** | Unused files | `npm i -g unimported` | `unimported` |

### Language-Specific Bug Detection Heuristics

#### JavaScript/TypeScript
- Missing `await` on async function calls
- `==` instead of `===` (type coercion bugs)
- `parseInt` without radix parameter
- Array methods returning new array but result unused
- `this` context issues in callbacks/arrow functions
- Promise constructor anti-pattern (wrapping existing promises)

#### Python
- Mutable default arguments (`def f(x=[])`)
- Late binding closures in loops (`lambda: i` captures reference, not value)
- `except:` (bare except catches SystemExit)
- `is` for value comparison instead of `==`
- Missing `__init__` call in subclass
- File operations without `with` statement

#### Go
- Unchecked error returns (`result, _ := function()`)
- Goroutine leaks (started but never waited/cancelled)
- Shared map without mutex (concurrent map writes = crash)
- Deferred function in loop (defers accumulate until function return)
- Nil pointer dereference after interface type assertion

#### Java
- Resource not closed (pre-try-with-resources pattern)
- `equals()` vs `==` for object comparison
- ConcurrentModificationException (modifying collection during iteration)
- Null pointer from unboxing (`Integer` to `int` when null)
- Thread-unsafe date formatters shared across threads
