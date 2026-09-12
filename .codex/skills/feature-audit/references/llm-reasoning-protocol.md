# LLM Reasoning Protocol — Operate at Expert Level on Any Model

> "Maintain simplicity. Prioritize transparency by explicitly showing the planning steps.
> Gain ground truth from the environment at each step." — Anthropic, *Building Effective Agents*

This reference is a **model-agnostic reasoning operating system**. Its purpose is to make
*any* Copilot model — small or large — behave like a careful senior engineer. Weaker models
fail not because they lack knowledge, but because they **skip steps**: they jump to code,
assume instead of verifying, ignore edge cases, and stop too early. This protocol forces the
behaviors that strong models do naturally.

**Read this first for any non-trivial task.** It governs *how* to think; the other references
govern *what* to check.

---

## The Core Loop — EPRAVR

Every task — feature, bug, refactor, audit — runs through six phases. Never skip a phase;
for small tasks, spend seconds on each, but still pass through them.

```
   EXPLORE ─→ PLAN ─→ REASON ─→ ACT ─→ VERIFY ─→ REFLECT
      │         │        │        │        │         │
   gather    decide   choose    make    prove     learn
   ground    the      the      the     it works  & record
   truth     approach  option   change  (ground   the
   (read,    (before   (trade-  (small,  truth,    pattern;
   search,   coding)   offs,    rever-   run it,   check for
   run)               edge      sible)   read      same bug
                      cases)             output)   elsewhere
      ▲                                                │
      └────────────── loop back if VERIFY fails ───────┘
```

| Phase | One-line mandate | Gate question before leaving the phase |
|-------|------------------|----------------------------------------|
| **Explore** | Read before you write. Get ground truth. | "Have I actually read the relevant code, or am I assuming?" |
| **Plan** | Decide the approach before touching code. | "Can I state the approach in 2-3 sentences and name what I'm NOT doing?" |
| **Reason** | Choose between options on explicit trade-offs. | "Did I consider at least 2 approaches and the edge cases of each?" |
| **Act** | Make the smallest correct, reversible change. | "Is this the minimum diff that solves the actual problem?" |
| **Verify** | Prove it works against reality, not assumption. | "Did I run/trace it and read the ACTUAL output — not imagine it?" |
| **Reflect** | Capture the lesson; hunt the same bug elsewhere. | "Does this pattern exist elsewhere? What would prevent recurrence?" |

> **The single most important rule**: At every step, **gain ground truth from the
> environment** — read the file, run the test, check the actual output. Never proceed on an
> assumption you could cheaply verify.

---

## Why This Makes Weak Models Strong

| Failure mode in weaker models | What this protocol forces instead |
|-------------------------------|-----------------------------------|
| Jumps straight to writing code | **Explore + Plan gates** must pass first |
| Assumes how code behaves | **Ground-truth rule**: read/run it before claiming |
| Picks the first idea | **Reason phase** requires ≥2 options + trade-offs |
| Ignores edge cases | **Edge-case sweep** is a mandatory checklist (see edge-case-catalog.md) |
| Confirmation bias ("it's probably X") | **Falsification**: actively try to disprove the hypothesis |
| Big risky rewrites | **Smallest reversible change** rule |
| Says "done" without checking | **Verify phase** requires evidence |
| Fixes the symptom | **Root-cause gate**: causality + incorrectness both proven |
| Forgets the rest of the codebase | **Reflect phase**: same-pattern sweep |

---

## Phase 1 — EXPLORE: Get Ground Truth Before Anything

**Goal**: Replace assumptions with facts. Build an accurate mental model of the system.

**Mandatory actions before forming any plan:**
1. **Read the actual code paths** end-to-end — from entry point (route/click/CLI) down through
   services, data access, and back. Do not infer behavior from names.
2. **Search for the real shape of things** — find all callers, all implementations, all configs.
3. **Run it / trace it** when cheap — reproduce the bug, run the test, print the actual value.
4. **State what you DON'T yet know** — list open questions explicitly.

**Exploration budget heuristic** (read-to-write ratio):

| Task size | Time exploring before acting |
|-----------|------------------------------|
| One-line fix | ~2× the edit time |
| Single-function change | ~2-3× |
| New feature | Explore until you can draw the data flow from memory |
| Bug in unfamiliar code | Until you can reproduce it AND explain the mechanism |

> **Anti-pattern — "Assumed Reality"**: Claiming `getUser()` validates input because the name
> suggests it. **Fix**: open `getUser()` and read it. If you cannot read it, say so and lower
> your confidence.

**Parallelize exploration** when investigation threads are independent (e.g., "how does auth
work" + "how does the DB layer work" + "where are the tests"). Independent read-only
investigations can be dispatched simultaneously — this is *sectioning* (Anthropic
parallelization pattern) and keeps the main reasoning thread clean.

---

## Phase 2 — PLAN: Decide the Approach Before Coding

**Goal**: Commit to an approach in words before committing it in code. Transparency first.

**Write a micro-plan** (even one line) that states:
- **What** will change (the specific files/functions)
- **How** the approach works (the mechanism, in plain language)
- **What you are explicitly NOT doing** (scope boundary — prevents over-engineering)
- **How you will verify** success (the test/observation that will prove it)

**Plan quality gate** — a good plan can answer all of these:

```
[ ] I can name every file that will change and why.
[ ] I can state the approach in 2-3 sentences.
[ ] I know the ONE test or observation that proves it works.
[ ] I know what I am deliberately leaving out of scope.
[ ] I know the blast radius (what else could this affect?).
```

> For new features or unclear approaches, escalate to a real design pass — see
> [feature-planning.md](./feature-planning.md). For bugs, the plan is the root-cause
> hypothesis — see [bug-detection.md](./bug-detection.md).

**Decompose large tasks** (prompt-chaining pattern): break the work into a sequence of small,
independently verifiable steps, each with its own gate. A task you can't decompose into
verifiable steps is a task you don't understand yet — return to Explore.

---

## Phase 3 — REASON: Choose on Explicit Trade-offs

**Goal**: Make the decision deliberately, not by reflex. This is where expert judgment lives.

### Always generate ≥ 2 options

For any non-trivial decision, list at least two viable approaches and compare them. The
"obvious" first idea is an anchor, not a conclusion.

```
Decision: <what is being decided>

Option A: <approach>
  + <benefit>   − <cost/risk>   Edge cases: <...>
Option B: <approach>
  + <benefit>   − <cost/risk>   Edge cases: <...>

Chosen: <A/B> because <the decisive factor: simplicity / reversibility / fit / risk>.
```

### Reversibility — the one-way vs two-way door test

| Door type | Definition | How to treat it |
|-----------|-----------|-----------------|
| **Two-way (reversible)** | Cheap to undo (rename, local refactor, config tweak) | Decide fast, act, verify. Bias to action. |
| **One-way (irreversible)** | Costly to undo (schema migration, public API contract, data deletion, dependency lock-in) | Slow down. Consider more options. Prefer the choice that **preserves future options**. Ask the user if uncertain. |

> Spend reasoning effort in proportion to reversibility. Don't agonize over a rename; do
> agonize over a database migration or a breaking API change.

### Mandatory edge-case sweep

Before choosing, run the input/state/failure sweep from
[edge-case-catalog.md](./edge-case-catalog.md): What happens with empty/null? Boundary values?
Concurrent access? Network failure? Malicious input? The chosen option must survive these.

### Calibrate confidence — and act on it

State your confidence and let it drive behavior:

| Confidence | Signal | Required action |
|-----------|--------|-----------------|
| **High** | Read the code, reproduced it, understand the mechanism | Proceed to Act. |
| **Medium** | Reasoned it through but haven't confirmed against reality | Get one more piece of ground truth (run/read) before acting. |
| **Low** | Guessing, unfamiliar area, conflicting evidence | Do NOT act. Explore more, or ask the user a precise question. |

> **Never convert low confidence into a confident-sounding change.** A weak model's most
> dangerous habit is fluent guessing. Say "I need to verify X" and verify it.

---

## Phase 4 — ACT: Smallest Correct, Reversible Change

**Goal**: Implement with minimal blast radius.

- **Minimize the diff** — touch the fewest files and lines that fully solve the *actual*
  problem. A large diff for a small problem signals a misunderstanding.
- **One logical change at a time** — never mix a refactor with a behavior change in the same
  step. Separate them so each is independently reviewable and revertable.
- **Match the existing codebase** — follow the patterns, naming, and style already present in
  the file. Consistency beats personal preference.
- **Don't gold-plate** — solve the problem in front of you (YAGNI). No speculative abstractions,
  no "while I'm here" extras unless they're trivial and clearly correct (Boy Scout rule).
- **Leave guardrails** — for bug fixes, add an assertion or validation at the bug site so the
  defect cannot silently return.

> Implementation depth: [implementation-guide.md](./implementation-guide.md).

---

## Phase 5 — VERIFY: Prove It Against Reality

**Goal**: Replace "it should work" with "I observed that it works." This is the
**evaluator-optimizer** loop — generate, then critically evaluate, then refine.

**Ground-truth verification ladder** (use the strongest rung available):

```
strongest │ 1. Run the test / the code and read the ACTUAL output
          │ 2. Reproduce the original failure → confirm it's now gone
          │ 3. Trace the exact changed path line-by-line with real values
weakest   │ 4. Re-read the diff as an adversarial reviewer
```

**Self-critique pass** — before declaring done, attack your own work:
```
[ ] Does this actually solve the user's stated problem (not a nearby one)?
[ ] Did I run it, or am I assuming it works?
[ ] What input would break this? Did I handle it? (edge-case-catalog.md)
[ ] Did I introduce a new failure mode, regression, or performance cliff?
[ ] For a bug fix: does a test now FAIL without my change and PASS with it?
[ ] Are there errors in the file? (check diagnostics)
```

**For bug fixes, the root-cause gate must pass** (both true):
- **Causality** — you can explain HOW the defect produces the failure.
- **Incorrectness** — you can explain WHY the old code was wrong (not just that changing it
  helped). See [fix-verification.md](./fix-verification.md).

> If Verify fails, **loop back to Reason or Explore** — do not patch the patch blindly.

---

## Phase 6 — REFLECT: Generalize and Prevent Recurrence

**Goal**: Convert a one-off fix into systemic improvement.

```
[ ] Same-pattern sweep: grep for the same defective pattern elsewhere.
[ ] Class-of-bug fix: did I fix the instance or the whole class?
[ ] Prevention: could a test, type, lint rule, or assertion stop recurrence?
[ ] Docs/comments: did behavior change in a way docs must reflect?
[ ] Lesson: is there a reusable insight worth recording in memory?
```

> One bug usually means a *class* of bugs. The expert move is to fix all of them and add the
> guardrail that prevents the next one.

---

## Decision Frameworks Cheat-Sheet

Pull the right frame for the decision in front of you:

| Decision type | Frame to apply |
|---------------|----------------|
| "Which approach?" | ≥2 options + trade-off table + reversibility test |
| "How risky is this change?" | Blast radius × reversibility (one-way vs two-way door) |
| "Is it worth the complexity?" | YAGNI + KISS — does the problem *today* require it? |
| "Should I refactor now?" | Boy Scout (small, in-scope) vs separate PR (large, out-of-scope) |
| "Am I sure?" | Confidence calibration → get ground truth if < High |
| "Is the bug really fixed?" | Causality + Incorrectness both proven |
| "Should I ask the user?" | One-way door + Medium/Low confidence → ask a precise question |
| "When do I stop?" | Stopping conditions (below) are met |

---

## Stopping Conditions — Know When You're Done (and When You're Stuck)

**Done** when ALL are true:
- The user's actual request is satisfied (re-read it — not a nearby problem).
- Verified against ground truth (ran it / reproduced-then-fixed / traced it).
- No new errors introduced (diagnostics clean).
- Edge cases from the catalog are handled.
- For bugs: regression test exists and the root-cause gate passed.

**Stuck** (change approach, don't grind) when:
- You've tried the same approach twice and it failed both times → **switch strategy entirely**.
- You're making changes without a hypothesis → **stop, return to Explore**.
- You've been guessing for a while → **state the blocker and ask the user a precise question.**

> **Time-box the struggle.** Repeating a failing approach is the clearest sign to step back and
> reconsider the problem from the Explore phase. Do not brute-force.

---

## Transparency Protocol — Show Your Work

Strong reasoning is *visible* reasoning. Make the thinking inspectable:
- **State the plan** before acting (even briefly).
- **Name your hypothesis** before testing it.
- **Report what you actually observed** (the real output), not what you expected.
- **Flag low confidence and unknowns** instead of hiding them behind fluent prose.
- **Surface assumptions** so they can be checked — an unspoken assumption is an unverified bug.

---

## Orchestration — Delegate and Parallelize

For large tasks, act as an **orchestrator** (Anthropic orchestrator-workers pattern):
- **Decompose** the task into independent sub-investigations.
- **Dispatch** independent read-only research in parallel (sectioning).
- **Synthesize** the results into one coherent plan before acting.
- Use a **second-opinion / voting** pass on high-stakes decisions (e.g., security-sensitive
  code): evaluate the same change from multiple angles before committing.

Keep each delegated task **narrowly scoped with a crisp deliverable** — the same way you'd
write a precise ticket for a junior engineer.

---

## The Universal Pre-Flight Checklist (Any Task, Any Stack)

Before you say "done," confirm:

```
EXPLORE  [ ] I read the real code; I'm not assuming behavior.
PLAN     [ ] I had an approach in words before I wrote code.
REASON   [ ] I weighed ≥2 options and swept edge cases.
ACT      [ ] The change is the smallest correct, reversible one.
VERIFY   [ ] I observed it work against ground truth (ran/traced it).
REFLECT  [ ] I checked for the same issue elsewhere and added prevention.
SCOPE    [ ] I solved the user's ACTUAL request, nothing more, nothing less.
```

---

## Sources

- [Anthropic: Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents) — workflows vs agents, prompt chaining, routing, parallelization, orchestrator-workers, evaluator-optimizer, ground-truth principle
- [Debugging Book: Scientific Debugging](https://www.debuggingbook.org/html/Intro_Debugging.html) — hypothesis-driven reasoning
- [Martin Fowler: Ship/Show/Ask](https://martinfowler.com/articles/ship-show-ask.html) — calibrating when to seek review
- [Reversible vs irreversible decisions](https://www.allthingsdistributed.com/2024/12/the-art-of-decision-making.html) — one-way vs two-way doors
- [Google Engineering Practices](https://google.github.io/eng-practices/) — small changes, reviewer mindset
