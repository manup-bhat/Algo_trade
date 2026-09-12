---
name: feature-audit
description: |
  Complete developer workflow for planning, implementing, improving, auditing, debugging, or fixing
  any application feature — in any tech stack, any framework, any language. Use when: planning a new
  feature, implementing a feature, improving an existing feature, finding bugs or issues, performing
  a root-cause analysis, fixing a bug properly, understanding what files to change, tracing feature
  impact across codebase layers, validating UX and user experience, reviewing for security (OWASP
  2025), preparing code for review, or verifying a fix is correct and complete. Covers the complete
  software development lifecycle: planning, discovery, impact analysis, implementation (SOLID/DRY/
  KISS/YAGNI), testing (TDD, property-based, mutation), UX validation, security audit (OWASP 2025
  A01–A10), code review (Google Engineering Practices), fix verification, and experienced developer
  practices (scientific debugging, root cause analysis, binary search debugging, hypothesis logging).
  Trigger on: "implement feature", "plan feature", "technical design", "improve feature", "feature
  audit", "what files change", "find bug", "debug issue", "root cause", "fix bug properly", "why does
  this break", "audit code", "code review", "UX review", "security review", "where does this feature
  reflect", "which files should I change", "how to add feature properly", "fix this issue",
  "what's the root cause", "regression test", "verify fix", "handle edge cases", "think like a user",
  "user experience issues", "how should I reason about this", "think harder", "step by step".
argument-hint: 'Feature name, bug description, or task (e.g. "user login", "search bar crashes on empty input", "plan payment checkout", "fix race condition in order processing")'
---

# Feature Audit & Implementation Skill

> "The best developers don't just write code — they understand the problem deeply, plan the
> approach carefully, implement the smallest correct solution, prove it works, and verify they
> haven't broken anything else." — Engineering excellence philosophy

A complete, expert-level workflow for any developer working on an application feature — planning
a new one, improving an existing one, fixing a broken one, or auditing code quality. Covers the
full software development lifecycle from first idea to verified fix in production.

**Works with any tech stack**: JavaScript/TypeScript, Python, Go, Java, Ruby, C#, Rust, or any other.

---

## 🧠 Expert Reasoning Operating System — Read This First

**This is what makes any model — large or small — operate like a senior engineer.** Weak results
come from skipping steps (jumping to code, assuming instead of verifying, ignoring edge cases,
stopping too early). Run every non-trivial task through the **EPRAVR loop**:

```
EXPLORE ─→ PLAN ─→ REASON ─→ ACT ─→ VERIFY ─→ REFLECT
 gather    decide  weigh ≥2  small,  prove it  hunt the
 ground    before  options  rever-  against   same bug
 truth     coding  + edge   sible   reality   elsewhere
(read/run) (words   cases    change  (run it!) + prevent
           first)
```

**The non-negotiable rule**: at every step, **gain ground truth from the environment** — read the
actual code, run the test, read the real output. Never proceed on an assumption you could cheaply
verify. State your **confidence**; if it's not High, get more evidence before acting.

> **Full protocol** (chain-of-thought scaffolds, confidence calibration, reversibility/one-way-door
> framework, self-verification loop, stopping conditions): see
> [llm-reasoning-protocol.md](./references/llm-reasoning-protocol.md). **Read it first for any
> non-trivial task** — it governs *how* to think; the rest of this skill governs *what* to check.

---

## ⚡ Copilot Smart Routing — Read Only What You Need

**CRITICAL**: Do NOT read all reference files for every request. Use this routing table to
determine which phases and files are relevant for the user's specific task:

| User Intent / Trigger | Phases to Execute | Reference Files to Read |
|----------------------|-------------------|------------------------|
| **"Fix this bug" / "why does X break" / "root cause"** | 1 (forensics) → 3B (root cause) → 8 (verify) | `pre-implementation.md`, `bug-detection.md`, `fix-verification.md` |
| **"Small improvement" / "refactor X" / "clean up"** | 1 → 2 → 3 → 7 | `pre-implementation.md`, `impact-analysis.md`, `implementation-guide.md`, `code-review.md` |
| **"Add new feature" / "implement X from scratch"** | 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 | `feature-planning.md` + ALL references |
| **"Plan this feature" / "technical design"** | 0 only | `feature-planning.md` |
| **"What files need to change?"** | 2 only | `impact-analysis.md` |
| **"Write tests for X"** | 4 only | `testing-strategy.md` |
| **"Is this secure?" / "security review"** | 6 only | `security-checklist.md` |
| **"Review my code" / "ready to merge"** | 7 only | `code-review.md` |
| **"UX/UI help" / "accessibility" / "design"** | 5 only | `ux-checklist.md` |
| **"Card layout" / "animation" / "modern look"** | 5 only | `ux-checklist.md` (Steps 8-14) |
| **"Dark mode" / "colors" / "typography"** | 5 only | `ux-checklist.md` (Steps 13-14) |
| **"Full feature audit" / "find all issues"** | All phases | ALL references |
| **"Best practices" / "how should I approach this"** | Practices reference | `experienced-developer-practices.md` |
| **"How should I reason / think about this" / "think harder"** | Reasoning OS | `llm-reasoning-protocol.md` |
| **"Handle edge cases" / "what could break" / "what am I missing"** | 3B + 4 | `edge-case-catalog.md`, `testing-strategy.md` |
| **"Think like a user" / "UX problems users hit" / "is this confusing"** | 5 | `user-empathy-personas.md`, `ux-checklist.md` |

**Rule**: For bug fixes, read 3 files max. For new features, read all. For targeted questions, read 1.
For ANY non-trivial task, the reasoning protocol applies even if you read nothing else.

---

## Quick Reference — All Phases

| Phase | Reference File | Purpose |
|-------|---------------|---------|
| ★ — Reasoning OS | [llm-reasoning-protocol.md](./references/llm-reasoning-protocol.md) | How to think at expert level on any model (read first) |
| 0 — Planning | [feature-planning.md](./references/feature-planning.md) | Requirements, design, scope, estimation |
| 1 — Discovery | [pre-implementation.md](./references/pre-implementation.md) | Read the feature, find issues, understand the user |
| 2 — Impact Analysis | [impact-analysis.md](./references/impact-analysis.md) | Every file/layer that must change |
| 3 — Implementation | [implementation-guide.md](./references/implementation-guide.md) | Expert coding: SOLID, DRY, YAGNI, naming |
| 3B — Bug Detection | [bug-detection.md](./references/bug-detection.md) | Scientific debugging & root cause analysis |
| 4 — Testing | [testing-strategy.md](./references/testing-strategy.md) | Test pyramid: unit → integration → E2E |
| 5 — UX Validation | [ux-checklist.md](./references/ux-checklist.md) | User journey, accessibility, error states |
| 6 — Security Audit | [security-checklist.md](./references/security-checklist.md) | OWASP 2025 Top 10 applied |
| 7 — Code Review & Ship | [code-review.md](./references/code-review.md) | Google + GitHub expert review standards |
| 8 — Fix Verification | [fix-verification.md](./references/fix-verification.md) | Prove the fix is correct, no regressions |
| — Edge Cases | [edge-case-catalog.md](./references/edge-case-catalog.md) | Encyclopedia of what could break (any stack) |
| — User Empathy | [user-empathy-personas.md](./references/user-empathy-personas.md) | Persona-based validation, journey friction |
| — Practices | [experienced-developer-practices.md](./references/experienced-developer-practices.md) | Senior engineer debugging & development practices |
| Post-Ship | [documentation.md](./references/documentation.md) | Docs, monitoring, feature flags |

---

## Complete Development Lifecycle

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    THE DEVELOPMENT LIFECYCLE                              │
│                                                                          │
│  PLAN ──→ DISCOVER ──→ IMPLEMENT ──→ TEST ──→ SECURE ──→ REVIEW ──→ SHIP│
│   │          │             │          │         │          │          │  │
│   │          │             │          │         │          │          │  │
│   │    ┌─────┴─────┐  ┌───┴───┐      │         │          │          │  │
│   │    │ Bug Path: │  │ Fix:  │      │         │          │          │  │
│   │    │ Reproduce │  │ Root  │      │         │          │          │  │
│   │    │ → Diagnose│  │ Cause │      │         │          │          │  │
│   │    │ → Fix     │  │ Only  │      │         │          │          │  │
│   │    └─────┬─────┘  └───┬───┘      │         │          │          │  │
│   │          │             │          │         │          │          │  │
│   │          └─────────────┴──→ VERIFY FIX ──→ REGRESSION TEST ─────→│  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 0 — Feature Planning & Technical Design

**Goal**: Before writing any code, clarify requirements, design the approach, and define "done."

**When to use**: New features, significant changes, or when the approach is unclear.
**Skip when**: Small bug fixes, minor refactors, or well-understood changes.

| Step | Question to Answer |
|------|-------------------|
| **1. Requirements** | WHO needs this? WHAT exactly should it do? WHY is it needed? |
| **2. Scope** | What's IN scope? What's explicitly OUT? What's MVP vs. full? |
| **3. Design** | What approaches exist? What are the tradeoffs? Which is simplest? |
| **4. Dependencies** | What does this depend on? What will depend on it? |
| **5. Risks** | What could go wrong? What's the mitigation? |
| **6. Acceptance Criteria** | When is this "done"? How do we verify it works? |
| **7. Implementation Order** | What to build first for fastest feedback? |

> **Full guide**: See [feature-planning.md](./references/feature-planning.md) for technical design documents,
> estimation heuristics, decision records, and Ship/Show/Ask decision framework.

---

## Phases 1–7 Workflow

### Phase 1 — Discovery & Existing Feature Audit

**Goal**: Understand everything about the current state before writing a single line of code.

**For new features**: Understand the codebase area where the feature will live.
**For bug fixes**: Understand the feature's current behavior and reproduce the bug.

1. **Read the existing feature end-to-end** — trace from the UI trigger (click/route/API call) all the way down through handlers, services, data access, and back.
2. **Git history audit**:
   ```
   git log --oneline --follow -- <file>    # history of specific file
   git blame <file>                         # who wrote what and when
   git log --grep="<feature-name>"         # commits mentioning the feature
   ```
3. **Find open issues**: Search `TODO`, `FIXME`, `HACK`, `XXX`, `BUG` in all feature files.
4. **Understand the user journey**: Map every step a real user takes through this feature.
5. **For bug investigations specifically**:
   - Get a reproduction recipe (exact steps, inputs, environment)
   - Define investigation scope (which files ARE and ARE NOT the problem)
   - Check git log for recent changes to the affected area
   - Use `git bisect` if the bug was recently introduced

> **Full guide**: See [pre-implementation.md](./references/pre-implementation.md)

---

### Phase 2 — Impact Analysis

**Goal**: Know every file and layer that must change before touching a line of code.

| Layer | What to Check |
|-------|--------------|
| **UI / Frontend** | Components, pages, routes that render or link to this feature |
| **API / Controllers** | Endpoints, request handlers, middleware that serve this feature |
| **Service / Business Logic** | Service classes, domain logic, event handlers |
| **Data / DB** | Models, schemas, migrations, queries, indexes |
| **Configuration** | Feature flags, environment variables, app config files |
| **Tests** | Unit tests, integration tests, E2E tests, fixtures, mocks |
| **Documentation** | README, API docs, changelogs, inline comments |

> **Full guide with dependency tracing**: See [impact-analysis.md](./references/impact-analysis.md)

---

### Phase 3 — Implementation

**Goal**: Write code that is correct, readable, tested, and no more complex than needed.

**Core principles** (from Google Engineering Practices + Fowler):
- **Correctness first**: Does the code do what the user needs?
- **Simplicity over cleverness**: Can't be understood quickly? Simplify.
- **YAGNI**: Solve the problem you know exists now. No speculative features.
- **Consistent with codebase**: Match patterns, naming, and style already in the file.
- **Names must communicate**: Long enough to be clear, short enough to be readable.
- **Comments explain WHY, not WHAT**: If code isn't self-explanatory, make code simpler.

> **Full guide**: See [implementation-guide.md](./references/implementation-guide.md)

---

### Phase 3B — Bug Detection & Root Cause Analysis

**Goal**: Find the actual root cause of bugs using scientific debugging methodology.

**The Scientific Method for Debugging** (from Zeller's Debugging Book):
```
1. OBSERVE the failure — what exactly goes wrong?
2. HYPOTHESIZE — what could cause this? (write it down!)
3. PREDICT — if my hypothesis is true, what should I observe?
4. EXPERIMENT — test the prediction (assert, log, breakpoint)
5. CONCLUDE — hypothesis confirmed or refuted?
6. REPEAT — refine hypothesis until root cause found
```

**Root Cause Verification** (both must be true before fixing):
- **Causality**: Your diagnosis explains HOW the defect causes the failure
- **Incorrectness**: Your diagnosis explains WHY the code is wrong

**Key practices**:
- **Reproduce FIRST** — can't fix what you can't reproduce
- **Write a failing test** that captures the bug BEFORE attempting a fix
- **Binary search** — use git bisect or divide-and-conquer to narrow the problem
- **Log your hypotheses** — track what you tried and what you learned
- **5 Whys** — keep asking "but WHY?" until you reach the true root cause
- **Check for same pattern elsewhere** — one bug often indicates a class of bugs

**Anti-patterns to avoid**:
- ❌ Printf debugging without a hypothesis (random logging)
- ❌ "Debugging into existence" (random changes until it works)
- ❌ Fixing the symptom, not the cause
- ❌ Skipping reproduction ("I think I know what it is")

> **Full guide**: See [bug-detection.md](./references/bug-detection.md). For the exhaustive list
> of what could break (boundary values, null/empty, concurrency, unicode, time, network, money),
> sweep [edge-case-catalog.md](./references/edge-case-catalog.md) before and after any fix.

---

### Phase 4 — Testing

**Goal**: Prove the feature works at every level of the test pyramid.

```
         ▲  E2E / UI Tests (fewest — high value user journeys only)
        ▲▲▲ Integration Tests (moderate — boundaries and contracts)
       ▲▲▲▲▲ Unit Tests (most — all logic paths, fast feedback)
```

**Rules**:
- Write tests at the same level the code was changed
- Every test: **Arrange → Act → Assert**
- Test observable **behavior**, not implementation details
- **Bug fix requirement**: The reproducing test must stay as a regression test
- Never duplicate tests across pyramid levels — push tests down

> **Full guide**: See [testing-strategy.md](./references/testing-strategy.md)

---

### Phase 5 — UX Validation

**Goal**: Verify the feature works from a real user's perspective.

**Critical states**: Happy path, Loading, Empty state, Error state, Validation error, Success feedback, Offline/slow network.

**Accessibility baseline (WCAG 2.2)**:
- Keyboard navigable, Screen reader compatible, Color contrast ≥ 4.5:1, Focus indicators visible

**Think like the human using it**: walk the feature as a First-Timer, Impatient, Confused,
Constrained, and Assisted user. At every step answer the user's three questions — *"What's
happening? What do I do next? Did it work?"* Every unanswered one is a UX bug.

> **Full guides**: mechanical UX/accessibility checks → [ux-checklist.md](./references/ux-checklist.md);
> persona-based empathy validation & journey friction → [user-empathy-personas.md](./references/user-empathy-personas.md)

---

### Phase 6 — Security Audit (OWASP 2025)

**Goal**: Ensure no security vulnerabilities are introduced or unaddressed.

| Risk | Feature-Level Check |
|------|-------------------|
| **A01 Broken Access Control** | Every route checks authorization. Users can't access others' data. |
| **A02 Security Misconfiguration** | No debug modes in prod. Secure headers. No secrets in code. |
| **A03 Supply Chain Failures** | New dependencies vetted. No known CVEs. |
| **A04 Cryptographic Failures** | Sensitive data encrypted. No MD5/SHA1 for passwords. |
| **A05 Injection** | All inputs sanitized/parameterized. No raw SQL. No eval(). |
| **A06 Insecure Design** | Threat-modeled: worst case if malicious user exploits this? |
| **A07 Authentication Failures** | Sessions expire. Tokens invalidated. Brute-force protected. |
| **A08 Data Integrity Failures** | Deserialization safe. CI/CD not injectable. |
| **A09 Logging Failures** | Audit trail for sensitive actions. No PII in logs. |
| **A10 Mishandling Exceptions** | No internal details leaked. Fail closed, not open. |

> **Full guide**: See [security-checklist.md](./references/security-checklist.md)

---

### Phase 7 — Code Review & Ship

**Goal**: Get a high-quality review, address feedback, and ship with confidence.

**Before requesting review** (self-review first):
- [ ] Read your own diff as if you're the reviewer
- [ ] PR description explains WHAT changed and WHY
- [ ] PR is as small as possible (one logical change per PR)
- [ ] All CI checks pass
- [ ] No debug code left behind
- [ ] Feature flag in place if change is large or risky

**What reviewers check** (Google Engineering Practices):
- Design, Functionality, Complexity, Tests, Naming, Comments, Style, Documentation

> **Full guide**: See [code-review.md](./references/code-review.md)

---

## Phase 8 — Fix Verification & Regression Prevention

**Goal**: After any fix or change, verify it addresses the root cause and doesn't break anything else.

**Verification checklist**:
1. **Causality proven**: The fix directly addresses the identified root cause
2. **Incorrectness proven**: You can explain WHY the old code was wrong, not just that changing it works
3. **Regression test exists**: A test that fails WITHOUT the fix and passes WITH the fix
4. **Same-pattern check**: Grep for the same defective pattern elsewhere in the codebase
5. **No new edge cases**: The fix doesn't introduce new failure modes
6. **Defensive assertions added**: Assertions at the bug site to catch future regressions
7. **Documentation updated**: If behavior changed, docs reflect the new behavior

**Post-fix homework** (from Debugging Book best practices):
- Check if same mistake exists elsewhere (same developer? same pattern? same assumption?)
- Add test coverage that would have caught this bug originally
- Consider if a static analysis rule could prevent recurrence
- Update any incorrect documentation or comments

> **Full guide**: See [fix-verification.md](./references/fix-verification.md)

---

## Experienced Developer Practices — Quick Reference

These practices apply across ALL phases. They are the habits that distinguish senior engineers:

| Practice | Rule of Thumb |
|----------|--------------|
| **Read before write** | Spend 2x time reading existing code vs writing new code |
| **Smallest possible change** | Minimize blast radius — touch fewer files, change fewer lines |
| **One logical change per commit** | Atomic, reviewable, revertable — never mix refactoring with features |
| **Write the test first** (for bugs) | TDD for bug fixes: failing test → fix → test passes |
| **Binary search for root cause** | Don't linearly scan — divide and conquer (git bisect, remove half the code) |
| **Time-box debugging** | Stuck > 30 minutes? Change approach entirely. Fresh perspective. |
| **Rubber duck debugging** | Explain the problem out loud — you'll often find the answer mid-sentence |
| **Future-proof the fix** | Fix the CLASS of bugs, not just the INSTANCE. Prevent recurrence. |
| **Boy Scout Rule** | Leave code cleaner than you found it — one small improvement per touch |
| **Measure twice, cut once** | Validate approach before implementing. Ask: "is there a simpler way?" |
| **Ship/Show/Ask** | Small fix → Ship. New pattern → Show. Uncertain approach → Ask for review |

> **Full guide**: See [experienced-developer-practices.md](./references/experienced-developer-practices.md)

---

## Decision Matrix: What Changed → What Else Must Change

| If you changed... | Also check / update... |
|-------------------|------------------------|
| UI component | Unit tests, E2E for user journey, accessibility, UX states |
| API endpoint (add/change) | API docs, consumer code, contract tests, auth/validation |
| API endpoint (remove) | All callers (search codebase), deprecation notice, changelog |
| Business logic / service | Unit tests for all code paths, integration tests |
| Database schema | Migration, seed data, ORM models, indexes, queries, backups |
| Configuration / env var | `.env.example`, deployment scripts, docs, README |
| Auth / authorization | Security audit (A01, A07), all protected routes, unauthorized tests |
| Error handling | User-facing messages, logging, monitoring alerts |
| Third-party dependency | Supply chain check (A03), license, bundle size |
| Shared utility / base class | Every caller, regression tests |
| Performance-sensitive path | Profiling, load tests, monitoring |

---

## Final Checklist

### Correctness
- [ ] Feature works on the happy path
- [ ] All known edge cases handled
- [ ] No regressions (full test suite passes)
- [ ] Bug fix includes a regression test proving the fix
### Code Quality
- [ ] Code is no more complex than needed
- [ ] Names are clear and descriptive
- [ ] No `TODO`s added without a tracking issue
- [ ] No dead code or commented-out code committed

### Testing
- [ ] New behavior covered by unit tests
- [ ] Integration points covered by integration tests
- [ ] Critical user journey covered by E2E or acceptance test
- [ ] All tests pass in CI

### Security
- [ ] Input validated at boundaries
- [ ] Authorization enforced server-side
- [ ] No secrets in code, logs, or URLs
- [ ] Errors don't leak internal details

### Documentation & Observability
- [ ] Docs updated if interface/behavior changed
- [ ] Metrics/logging/alerts in place for new behavior
- [ ] Feature flag configured if rollout needs control

---

## Sources & Further Reading

- [Google Engineering Practices](https://google.github.io/eng-practices/) — Code review and quality standards
- [Martin Fowler: Ship/Show/Ask](https://martinfowler.com/articles/ship-show-ask.html) — When to seek review vs. ship directly
- [Martin Fowler: Practical Test Pyramid](https://martinfowler.com/articles/practical-test-pyramid.html) — Test strategy
- [OWASP Top 10: 2025](https://owasp.org/Top10/2025/) — Current security risks
- [Debugging Book: Scientific Debugging](https://www.debuggingbook.org/html/Intro_Debugging.html) — Systematic root cause analysis
- [Tornhill & Borg (2022)](https://arxiv.org/abs/2203.04374) — Code quality → 15× defect density impact
- [SonarSource: Cognitive Complexity](https://www.sonarsource.com/learn/cognitive-complexity/) — Human-readable complexity metric
- [Refactoring.Guru: Code Smells](https://refactoring.guru/refactoring/smells) — Complete smell taxonomy
- [12factor.net](https://12factor.net/) — Cloud-native application methodology
