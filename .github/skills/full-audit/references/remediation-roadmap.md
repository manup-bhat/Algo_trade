# Remediation Roadmap — From Findings to Sprint-Ready Work

A pile of audit findings is not a remediation plan. This file converts findings into
an actionable, prioritized backlog that engineering teams can execute against.

---

## Track Structure (4 Tracks)

Organize all work into four tracks, based on urgency and nature:

```
Track 0 — Emergency Response (now, before anything else)
Track 1 — High Priority Fixes (current sprint)
Track 2 — Medium Priority Improvements (next 1–2 sprints)
Track 3 — Tech Debt & Low Priority (rolling backlog)
```

---

## Track 0: Emergency Response

**Threshold**: Any finding marked Critical.

Critical findings represent active or near-immediate risk. They skip normal sprint planning.
They are addressed immediately, regardless of what else is in progress.

### Track 0 Protocol

1. **Identify**: List all Critical findings from the audit.
2. **Assign immediately**: Each item gets one owner with a fix deadline (hours, not days).
3. **Contain first if needed**: If exploitable now, implement a temporary mitigation (disable endpoint, rotate credential, add rate limit) before the full fix.
4. **Fix**: Implement the proper fix, with a test that proves the finding no longer exists.
5. **Verify**: Second person reviews the fix for correctness.
6. **Deploy**: Deploy as a hotfix, outside normal release cycle if necessary.
7. **Post-mortem**: After the fix, ask: how did this get in? What process change prevents recurrence?

| Finding | Owner | Contain By | Fix By | Status |
|---------|-------|-----------|--------|--------|
| [Critical #1] | | | | |
| [Critical #2] | | | | |

---

## Track 1: High Priority (Current Sprint)

**Threshold**: All High severity findings. Plus any Medium findings adjacent to Critical areas.

### Track 1 Backlog Template

```markdown
## Sprint [N] Security & Quality Fixes

### From Audit

- [ ] **Finding #[N]**: [Short title] — [file:line]
  - Severity: High
  - Category: [Security / Quality / Testing]
  - Estimate: [S/M/L]
  - Acceptance: [How do we know this is fixed?]

- [ ] **Finding #[N]**: [Short title] — [file:line]
  ...
```

**Track 1 rules**:
- No new feature work in the same code area until High findings are resolved
- Each fix must include a test (or updated test) that would have caught the issue
- Fixes are reviewed by a second engineer
- Sprint velocity reduction for Track 1 work should be communicated to stakeholders

---

## Track 2: Medium Priority (Next 1–2 Sprints)

**Threshold**: All Medium severity findings.

### Track 2 Backlog Template

```markdown
## Quality & Security Improvements — [Sprint Range N+1 to N+2]

### Security Hardening
- [ ] Add rate limiting to [endpoint/action] (Finding #N)
- [ ] Remove unused dependency [name] with CVE (Finding #N)
- [ ] Fix verbose error messages in [module] (Finding #N)

### Code Quality
- [ ] Extract auth logic duplication into shared middleware (Finding #N)
- [ ] Add missing tests for [feature] error paths (Finding #N)
- [ ] Refactor [function] with complexity > 20 (Finding #N)

### Observability
- [ ] Add structured logging to [background job] (Finding #N)
- [ ] Define success/failure metrics for [feature] (Finding #N)
```

---

## Track 3: Tech Debt Backlog (Rolling)

**Threshold**: Low severity findings, Informational findings, and all technical debt register items.

Track 3 items are not time-boxed. They are addressed:
- Opportunistically, when a developer is already in the file for another reason ("Boy Scout Rule")
- In dedicated tech debt sprints (schedule one per quarter minimum)
- When a debt item's priority increases because a related feature is planned

### Track 3 Item Format

```markdown
- **Debt Item**: [Description]
  - Files: [location(s)]
  - Why it matters: [brief rationale]
  - How to fix: [brief approach]
  - Effort: Low / Medium / High
  - Priority: P3 (do when convenient) / P2 (schedule next quarter)
```

---

## Scheduling the Work

### Sprint Capacity Allocation

Use this as a starting guide for allocating audit remediation work within sprints:

| Team Situation | Suggested Allocation |
|---------------|---------------------|
| Active incident or Critical findings open | 100% to Track 0 until resolved |
| Multiple High findings | 40–60% of sprint to Track 1 |
| Only Medium/Low findings | 15–25% of sprint to Track 2/3 |
| Post-audit, findings under control | 10–15% ongoing for Track 3 |

### Communicating to Stakeholders

Use this framing:
```
"The audit identified [N] issues:
  - [N] Critical: require immediate fixes before any new features
  - [N] High: require fixes within this sprint
  - [N] Medium: scheduled for next 2 sprints
  - [N] Low/Info: in rolling backlog

This requires approximately [X] engineer-weeks of capacity.
Features [list] will be delayed by approximately [timeframe].
Not addressing Critical/High findings poses [specific risk]."
```

---

## Backlog Ticket Format

Each finding becomes a backlog ticket. Use a consistent format so all tickets are estimable:

```markdown
## [AUDIT] Fix: [Short Finding Title]

**Severity**: Critical / High / Medium / Low  
**Finding #**: [N from audit report]  
**Category**: Security / Quality / Testing / Observability / UX / Docs

### Context
[1–3 sentences explaining what the issue is and why it matters]

### Current Behavior
[What happens now — code snippet, example request/response, or description]

### Expected Behavior
[What should happen after the fix]

### Acceptance Criteria
- [ ] [Specific, testable condition 1]
- [ ] [Specific, testable condition 2]
- [ ] Test added/updated that would have caught this issue originally

### References
- Audit Finding: [link to finding in report]
- File: [path:line]
- [OWASP / CVE / design doc / other link if applicable]

### Notes for Reviewer
[Anything the reviewer should pay special attention to when reviewing this fix]
```

---

## Closing the Loop: Verification

After each track is completed, verify:

- [ ] Every finding in the track has a corresponding commit that fixes it
- [ ] Every fix has an associated test (unit, integration, or E2E as appropriate)
- [ ] Re-run the security scanner to confirm CVEs are cleared
- [ ] Re-run static analysis to confirm quality findings are resolved
- [ ] Re-run duplication detection to confirm duplication % decreased
- [ ] Re-run complexity analysis to confirm hotspots are resolved
- [ ] Update the audit report with the resolution status of each finding

### Regression Check

For all Critical and High fixes, run a regression check:
1. Checkout the commit *before* the fix
2. Confirm the test **fails** (proving the test catches the issue)
3. Checkout the fix commit
4. Confirm the test **passes** (proving the fix works)
5. Confirm no other tests broke

This gives you and reviewers confidence the fix is real, not cosmetic.

---

## Categorized Remediation by Debt Type

### Duplication Remediation

| Priority | Action | Technique |
|----------|--------|-----------|
| P0 | Fix diverged copies causing bugs NOW | Merge into single source of truth |
| P1 | Extract 4+ copy patterns this sprint | Extract Method / Extract Module |
| P2 | Extract 2-3 copy patterns next sprint | Extract Method with parameterization |
| P3 | Document acceptable duplication | Note why it's intentional (different bounded contexts) |

### Principle Debt Remediation

| Priority | Action | Technique |
|----------|--------|-----------|
| P0 | Fix DIP violations blocking testability | Introduce dependency injection |
| P1 | Fix SRP violations > 500 lines in high-churn files | Extract Class / Extract Module |
| P2 | Fix OCP violations (growing switch statements) | Strategy Pattern / Registry |
| P3 | Address YAGNI (unused abstractions) | Inline Class / Remove Dead Code |

### Workflow Debt Remediation

| Priority | Action | Technique |
|----------|--------|-----------|
| P0 | Add transaction boundaries to financial operations | Wrap in DB transaction |
| P1 | Add error handling to critical async paths | try/catch + user notification |
| P2 | Add timeouts to all external service calls | Configure timeout + fallback |
| P3 | Add retry with idempotency to job processing | Idempotency key + status check |

### AI-Generated Debt Remediation

| Priority | Action | Technique |
|----------|--------|-----------|
| P0 | Fix hallucinated imports / phantom packages | Remove or replace with real packages |
| P1 | Fix tests that don't actually test anything | Rewrite with meaningful assertions |
| P2 | Normalize inconsistent AI patterns to match codebase | Refactor to follow conventions |
| P3 | Remove over-comments on obvious code | Delete redundant comments |

---

## Continuous Audit Integration

To prevent audit findings from recurring, integrate these checks into CI/CD:

| Check | Tool | When | Gate |
|-------|------|------|------|
| Dependency vulnerabilities | npm audit / pip-audit | Every PR | Block on Critical/High CVE |
| Code duplication | jscpd --threshold 5 | Every PR | Block if duplication increases |
| Complexity | ESLint complexity rule | Every PR | Block if new function > 15 complexity |
| Dead code | ts-prune / vulture | Weekly | Alert if unused exports grow |
| Test coverage | Coverage reporter | Every PR | Block if coverage drops below threshold |
| Type safety | tsc --noEmit | Every PR | Block on type errors |
| Circular dependencies | madge --circular | Every PR | Block on new circular deps |

This creates a "quality ratchet" — quality can only improve, never degrade.
