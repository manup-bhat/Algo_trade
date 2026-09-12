# LLM Reasoning Protocol for Auditing — Think Like a Principal Engineer on Any Model

> "Prioritize transparency by explicitly showing reasoning steps. Gain ground truth from the
> environment at each step." — Anthropic, *Building Effective Agents*

This reference makes *any* Copilot model audit like a principal engineer. An audit is only as
good as its **reasoning discipline**: systematic coverage (miss nothing), evidence-based
findings (no hallucinated bugs), calibrated severity (no crying wolf), and root-cause depth
(fix the disease, not the symptom). Weaker models produce shallow or fabricated audits; this
protocol forces rigor.

**Read this first when running any audit.** It governs *how to reason*; the other references
govern *what to inspect*.

---

## The Audit Reasoning Loop — MAP · PROBE · PROVE · RANK · ROOT · ROADMAP

```
  MAP ──→ PROBE ──→ PROVE ──→ RANK ──→ ROOT ──→ ROADMAP
   │        │         │         │        │         │
 build    inspect   confirm   score    trace    sequence
 the      each      every     by       to the   fixes by
 model    surface   finding   real     true     risk ×
 of the   for       with      impact   cause &  effort,
 system   issues    evidence  not      blast    prove
 (ground  (cover-   (no       gut      radius   no new
  truth)   age)      guesses)  feel             risk
```

| Stage | Mandate | Gate before leaving |
|-------|---------|---------------------|
| **MAP** | Build a true model of the system (features, layers, data flow). | "Can I name the components and how data flows between them?" |
| **PROBE** | Systematically inspect each surface — miss nothing. | "Did I cover every category, or just the obvious ones?" |
| **PROVE** | Every finding cites file:line evidence. | "Can I point to the exact code that proves this? Did I read it?" |
| **RANK** | Severity = real exploitability/impact, not vibes. | "Is this severity defensible to a skeptical engineer?" |
| **ROOT** | Trace each issue to its cause and cross-system impact. | "Is this a symptom of a deeper, repeated cause?" |
| **ROADMAP** | Sequence fixes by risk × effort; verify no new risk. | "Is the highest-risk, lowest-effort item first?" |

> **Prime directive of auditing**: *No finding without evidence; no severity without
> justification.* A fabricated or miscalibrated finding destroys trust in the whole audit.

---

## Why This Makes Weak Models Audit Well

| Weak-model audit failure | What this protocol forces |
|--------------------------|---------------------------|
| Lists generic issues without reading the code | **PROVE**: every finding needs file:line evidence |
| Hallucinates vulnerabilities that aren't there | **Ground-truth rule**: read the actual code before claiming |
| Only checks the obvious (e.g., SQL injection) | **PROBE coverage matrix**: every category, every layer |
| Calls everything "Critical" | **RANK rubric**: severity tied to exploitability × impact |
| Reports symptoms, misses the systemic cause | **ROOT**: 5-whys + same-pattern sweep |
| Dumps 200 findings with no priority | **ROADMAP**: risk × effort sequencing |
| Stops after the first file | **Stopping conditions** require coverage, not exhaustion |

---

## Stage 1 — MAP: Build Ground Truth of the System

You cannot audit what you don't understand. Before judging anything:

1. **Detect the application's phase** — greenfield, active build, scaling, mature, legacy, or
   sunset. This sets debt tolerance and what "good" means.
   → [application-phase-detection.md](./application-phase-detection.md)
2. **Inventory features and entry points** — routes, jobs, events, admin functions.
   → [feature-discovery.md](./feature-discovery.md)
3. **Trace the data flow** — how a request moves through layers and where data is transformed.
   → [workflow-analysis.md](./workflow-analysis.md), [architecture-planning.md](./architecture-planning.md)
4. **Run the automated tools first** — they give objective ground truth (coverage, duplication,
   CVEs, complexity) that anchors the manual review. → SKILL.md "Copilot Execution Strategy".

> **Anti-pattern — auditing from names**: concluding `validateInput()` is safe because of its
> name. Open it and read it. An audit built on assumptions is worthless.

---

## Stage 2 — PROBE: Systematic Coverage (Miss Nothing)

Weak audits are *shallow* — they find the first issue and stop. Force breadth with a coverage
matrix: every category × every high-risk area.

```
                 Auth  Data  API   Async  Shared  External
                 layer layer layer jobs   utils   deps
Security          [ ]   [ ]   [ ]   [ ]    [ ]     [ ]
Bugs/concurrency  [ ]   [ ]   [ ]   [ ]    [ ]     [ ]
Edge cases        [ ]   [ ]   [ ]   [ ]    [ ]     [ ]
Duplication       [ ]   [ ]   [ ]   [ ]    [ ]     [ ]
Principles/SOLID  [ ]   [ ]   [ ]   [ ]    [ ]     [ ]
Performance       [ ]   [ ]   [ ]   [ ]    [ ]     [ ]
Tests/coverage    [ ]   [ ]   [ ]   [ ]    [ ]     [ ]
```

**Risk-based sequencing** — audit in order of impact, not file order:
1. Authn/authz & security-sensitive code (highest blast radius)
2. Shared utilities/base classes (quality multiplies across the codebase)
3. High-churn files (git shows where bugs cluster — `git log` hotspots)
4. Money/data-integrity paths
5. Everything else

**Parallelize independent tracks** (Anthropic sectioning pattern): bug-scan, duplication-scan,
workflow-trace, and principles-check are independent — run them concurrently, then synthesize.

> Apply the full edge-case sweep to each surface — see the feature-audit
> `edge-case-catalog.md` and [bug-detection-advanced.md](./bug-detection-advanced.md).

---

## Stage 3 — PROVE: Evidence or It Didn't Happen

Every finding must be **falsifiable and sourced**. Use this record for each:

```
FINDING-NNN
  Claim:      <what is wrong, one sentence>
  Evidence:   <file:line> — <the actual code snippet that proves it>
  Why wrong:  <the rule/principle/threat it violates>
  Confidence: High / Medium / Low
  Impact:     <what breaks, for whom, under what condition>
```

**Confidence calibration controls false positives:**

| Confidence | Meaning | Action |
|-----------|---------|--------|
| **High** | Read the code; the defect is concrete and reproducible | Report as a firm finding |
| **Medium** | Pattern looks wrong but context might justify it | Report as "potential — verify"; note what would confirm it |
| **Low** | Suspicion only; haven't confirmed | Do NOT report as a defect. Investigate or list under "areas to review" |

> **Never inflate a Low-confidence hunch into a confident finding.** A noisy audit full of
> false positives gets ignored. Precision builds trust.

**Falsification discipline**: actively try to *disprove* each finding before reporting it. "Is
there a guard elsewhere that already handles this? A middleware? A DB constraint?" Trace it.

---

## Stage 4 — RANK: Calibrated Severity (No Crying Wolf)

Severity must be defensible. Use **exploitability/likelihood × impact**, not gut feel.

```
            IMPACT →   Low        Medium      High (data loss,
LIKELIHOOD ↓                                  RCE, auth bypass)
High (easy, common)    Medium     High        CRITICAL
Medium                 Low        Medium       High
Low (hard, rare)       Info       Low          Medium
```

For each finding, justify the placement: *"Likelihood High because the input is user-controlled
and reaches the query unsanitized; Impact High because it exposes all users' records → Critical."*

> Full rubric with examples: [scoring-matrix.md](./scoring-matrix.md). Calibrate severity to the
> **application phase** — a Critical in a payment system may be a Low in a throwaway prototype.

---

## Stage 5 — ROOT: Cause and Cross-System Impact

Shallow audits report symptoms. Expert audits find the **disease**.

For each significant finding:
1. **5 Whys** — keep asking "but why?" until you reach a systemic cause (missing pattern, absent
   guardrail, wrong abstraction, team-wide habit).
2. **Same-pattern sweep** — grep the codebase: does this defect class repeat elsewhere? One IDOR
   usually means many. Report the *class*, not just the instance.
3. **Blast-radius / impact-on-other-functionality** — what else depends on this code? Changing
   it affects whom? A bug in a shared util is N bugs. → [cross-cutting-analysis.md](./cross-cutting-analysis.md)
4. **Causality + Incorrectness** — explain HOW it fails and WHY the code is wrong, so the fix is
   real, not cosmetic.

```
ROOT-CAUSE RECORD
  Symptom(s):        <observed findings>
  Root cause:        <the single underlying reason, via 5-whys>
  Instances found:   <file:line list — the whole class>
  Blast radius:      <what else this code/cause affects>
  Systemic fix:      <the change that kills the whole class + prevents recurrence>
```

---

## Stage 6 — ROADMAP: Sequence and De-Risk

Turn findings into an ordered plan. Priority = **(risk reduced) ÷ (effort)**, with hard
dependencies respected.

```
[ ] Critical security/data-loss first (blocking).
[ ] High risk × low effort next (quick wins that cut the most risk).
[ ] Group fixes by root cause (fix the class once, not each instance).
[ ] Flag fixes that are one-way doors (migrations, API breaks) for extra review.
[ ] For each fix, define the verification that proves it AND proves no new risk.
```

> Full method: [remediation-roadmap.md](./remediation-roadmap.md),
> [technical-debt-assessment.md](./technical-debt-assessment.md).

---

## Auditor Bias Checklist — Stay Objective

Weak models (and tired humans) fall into these. Check yourself:

| Bias | Symptom | Counter |
|------|---------|---------|
| **Confirmation** | Only finding issues you expected | Run the full coverage matrix |
| **Anchoring** | First file sets your whole opinion | Sample broadly before concluding |
| **Severity inflation** | Everything is "Critical" | Apply the likelihood × impact grid |
| **Hallucination** | Reporting issues not in the code | PROVE rule: file:line or it doesn't exist |
| **Recency** | Over-weighting the last thing you read | Re-rank all findings together at the end |
| **Tooling trust** | Treating a linter hit as ground truth | Verify each tool finding in the actual code |
| **Premature closure** | Stopping at the first plausible cause | 5-whys until systemic |

---

## Stopping Conditions for an Audit

**Done** when:
- The coverage matrix is filled for all high-risk areas (not every file — risk-weighted).
- Every reported finding has evidence (file:line) and a justified severity.
- Significant findings are traced to root cause with a same-pattern sweep.
- The roadmap sequences fixes by risk × effort.

**Re-scope / ask the user** when:
- The codebase is too large to fully cover in scope → audit by risk priority and state coverage.
- You can't determine intent/severity without product context → ask a precise question.
- Findings depend on runtime/config you can't see → flag as "verify in environment."

> An honest "I audited the top-risk 60% and here's what I found, here's what's uncovered" beats
> a fake "I reviewed everything." State your coverage.

---

## Sources

- [Anthropic: Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents) — orchestrator-workers, parallelization (sectioning + voting), evaluator-optimizer, ground-truth
- [OWASP Risk Rating Methodology](https://owasp.org/www-community/OWASP_Risk_Rating_Methodology) — likelihood × impact severity
- [Debugging Book: Scientific Debugging](https://www.debuggingbook.org/html/Intro_Debugging.html) — hypothesis-driven, falsification
- [Google Engineering Practices: Code Review](https://google.github.io/eng-practices/review/) — evidence-based, calibrated review
- [Tornhill & Borg (2022)](https://arxiv.org/abs/2203.04374) — hotspot/churn-based risk prioritization
