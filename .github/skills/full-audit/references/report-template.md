# Full Audit Report Template

This is the report structure for a complete codebase audit. Copy this template into
a Markdown document and fill in each section as the audit progresses.

Replace all `[placeholder]` text with real findings and data.

---

# Codebase Audit Report

**Project**: [Project Name]  
**Auditor(s)**: [Name(s)]  
**Audit Date**: [Start Date] — [End Date]  
**Report Version**: 1.0  
**Classification**: [Internal / Confidential / Public]

---

## Executive Summary

### Project Overview

| Field | Value |
|-------|-------|
| Project Type | [Web App / API / CLI / Service / Library / Pipeline / Other] |
| Primary Language(s) | [e.g., TypeScript, Python, Go] |
| Deployment Environment | [Cloud / On-premise / Embedded / SaaS] |
| Team Size | [N engineers] |
| Codebase Age | [Years/months since initial commit] |
| Audit Scope | [Full audit / Targeted audit of [N] features] |

### Overall Health Score

```
Code Quality:  [score]/25   (25% weight)
Test Coverage: [score]/20   (20% weight)
Security:      [score]/30   (30% weight)
UX/Experience: [score]/15   (15% weight)
Documentation: [score]/10   (10% weight)
────────────────────────────────────────
Total:         [score]/100
```

**Health Grade**:
- 85–100: Healthy — minor improvements recommended
- 70–84: Adequate — several areas need improvement
- 55–69: Concerning — significant investment needed
- < 55: At Risk — immediate action required

### Finding Summary

| Severity | Count | Resolved | Outstanding |
|---------|-------|---------|------------|
| Critical | | | |
| High | | | |
| Medium | | | |
| Low | | | |
| Informational | | | |
| **Total** | | | |

### Key Risks (Top 3)

1. **[Risk 1]**: [One sentence description and potential impact]
2. **[Risk 2]**: [One sentence description and potential impact]
3. **[Risk 3]**: [One sentence description and potential impact]

### Recommended Immediate Actions

- [ ] [Action 1 — Critical/High priority]
- [ ] [Action 2 — Critical/High priority]
- [ ] [Action 3 — Critical/High priority]

---

## Feature Inventory and Coverage

### Features Audited

| # | Feature | Entry Point | Risk Level | Phases Audited | Findings | Status |
|---|---------|-------------|-----------|----------------|----------|--------|
| 1 | [Feature name] | [file:line or route] | C/H/M/L | [1,2,3,4,5,6,7] | [N findings] | Complete |
| 2 | | | | | | |
| 3 | | | | | | |

**Audit Coverage**: [N] of [Total] identified features fully audited ([%])

### Features Not Audited / Out of Scope

| Feature | Reason Not Audited | Recommended Priority |
|---------|-------------------|---------------------|
| [Feature] | [e.g., deprecated, not in scope] | [High / Medium / Low] |

---

## Findings Detail

### Critical Findings

#### Finding C-1: [Short Title]

| Field | Value |
|-------|-------|
| Severity | Critical |
| Category | Security / Quality / Other |
| Feature | [Feature name or "Cross-cutting"] |
| Location | [file:line] |
| CVSS Score | [if security] |
| Status | Open / In Progress / Resolved |

**Description**:  
[Clear description of the issue and its impact]

**Evidence**:  
```
[Code snippet, request/response, or description of evidence]
```

**Recommendation**:  
[Specific, actionable fix recommendation]

**References**:  
- [OWASP link, CVE, or other reference]

---

#### Finding C-2: [Short Title]
[Repeat format above]

---

### High Severity Findings

#### Finding H-1: [Short Title]
[Same format as Critical]

---

### Medium Severity Findings

#### Finding M-1: [Short Title]
[Same format]

---

### Low Severity Findings

> Low findings are summarized here rather than detailed individually.

| # | Finding | Location | Recommendation |
|---|---------|----------|---------------|
| L-1 | [Short title] | [file] | [Brief fix] |
| L-2 | | | |

---

### Informational Observations

| # | Observation | Context | Suggested Action |
|---|------------|---------|-----------------|
| I-1 | | | |

---

## Security Audit Results

### OWASP Top 10 Coverage

| # | Category | Status | Findings |
|---|---------|--------|---------|
| A01:2025 | Broken Access Control | Pass / Partial / Fail | [Finding refs] |
| A02:2025 | Cryptographic Failures | Pass / Partial / Fail | |
| A03:2025 | Vulnerable and Outdated Components | Pass / Partial / Fail | |
| A04:2025 | Cryptographic Failures (data) | Pass / Partial / Fail | |
| A05:2025 | Injection | Pass / Partial / Fail | |
| A06:2025 | Insecure Design | Pass / Partial / Fail | |
| A07:2025 | Authentication Failures | Pass / Partial / Fail | |
| A08:2025 | Software and Data Integrity Failures | Pass / Partial / Fail | |
| A09:2025 | Security Logging and Monitoring Failures | Pass / Partial / Fail | |
| A10:2025 | Mishandling of Exceptional Conditions | Pass / Partial / Fail | |

### Dependency Vulnerability Summary

| Dependency | Version | CVE | Severity | Fix Available |
|-----------|---------|-----|---------|--------------|
| [name] | [ver] | [CVE-XXXX-XXXX] | High | Yes — upgrade to [ver] |

---

## Code Quality Summary

### Test Coverage

| Component / Module | Line Coverage | Branch Coverage | Integration Tests | Notes |
|-------------------|--------------|----------------|------------------|-------|
| [Module 1] | [%] | [%] | Yes / No | |
| [Module 2] | | | | |

**Overall coverage**: [%] line, [%] branch

### Complexity Hotspots

| File | Function/Method | Cyclomatic Complexity | Churn (edits/6mo) | Priority |
|------|----------------|----------------------|------------------|---------|
| [file] | [function] | [score] | [N edits] | High |

### Architecture Consistency

| Concern | Status | Notes |
|---------|--------|-------|
| Auth enforcement layer | Consistent / Inconsistent | |
| Input validation boundary | Consistent / Inconsistent | |
| Error format | Consistent / Inconsistent | |
| Logging structure | Consistent / Inconsistent | |

---

## Bug Detection Results

### Summary

| Bug Category | Count | Critical | High | Medium | Low |
|-------------|-------|---------|------|--------|-----|
| Race Conditions | | | | | |
| Resource Leaks | | | | | |
| Null Propagation | | | | | |
| Error Swallowing | | | | | |
| Copy-Paste Bugs | | | | | |
| State Violations | | | | | |
| Logic Inversions | | | | | |
| **Total** | | | | | |

### Critical Bugs

| # | Category | Location | Description | Impact |
|---|----------|----------|-------------|--------|
| B-1 | | [file:line] | | |

---

## Duplicate & Waste Code Report

### Duplication Score: [X]% — Status: ✅ / 🟡 / 🔴

| Metric | Value | Threshold |
|--------|-------|-----------|
| Overall duplication % | [X]% | < 3% excellent, 3-5% ok, > 5% action needed |
| Exact clones (Type 1) | [N] blocks | 0 target |
| Near-duplicates (Type 2-3) | [N] blocks | Review each |
| Dead exports | [N] | Remove all |
| Unused files | [N] | Remove all |
| Commented-out code blocks | [N] | Remove all |
| Feature flag zombies (> 90 days) | [N] | Clean up |
| Speculative generality | [N] instances | Simplify |

### Top Duplications

| # | Files | Lines | Type | Recommendation |
|---|-------|-------|------|---------------|
| 1 | [file A] ↔ [file B] | [N] | 1/2/3 | Extract / Parameterize |

---

## Workflow & Data Flow Analysis

### Coverage

| Metric | Value |
|--------|-------|
| Workflows fully traced | [N] of [Total] |
| Error paths fully handled | [%] |
| Async operations properly awaited | [%] |
| External calls with timeouts | [%] |
| Multi-step writes with transactions | [%] |

### Workflow Gaps

| # | Workflow | Gap Type | Location | Severity |
|---|---------|----------|----------|---------|
| W-1 | [Name] | Missing error handling | [file:line] | High |
| W-2 | [Name] | No transaction boundary | [file:line] | Critical |
| W-3 | [Name] | Missing timeout | [file:line] | Medium |

---

## Development Principles Compliance

### SOLID Score: [X]/100

| Principle | Score | Violations | Top Offender |
|-----------|-------|-----------|-------------|
| Single Responsibility | /20 | [N] | [file] |
| Open/Closed | /20 | [N] | [file] |
| Liskov Substitution | /20 | [N] | [file] |
| Interface Segregation | /20 | [N] | [file] |
| Dependency Inversion | /20 | [N] | [file] |

### Additional Principles

| Principle | Status | Issues |
|-----------|--------|--------|
| DRY | ✅/🟡/🔴 | [duplication %] |
| KISS | ✅/🟡/🔴 | [N] functions with cognitive complexity > 15 |
| YAGNI | ✅/🟡/🔴 | [N] unused abstractions |
| 12-Factor | [N]/12 factors compliant | [violations listed] |

### Cognitive Complexity Hotspots

| File | Function | Complexity | Churn | Priority |
|------|----------|-----------|-------|---------|
| [file] | [function] | [score] | High/Med/Low | [Fix priority] |

---

## Technical Debt Register

| # | Debt Item | Location | Quadrant | Type | Impact | Effort | Priority |
|---|-----------|----------|----------|------|--------|--------|---------|
| D-1 | | | | Duplication / Principle / Workflow / AI / Legacy | | | |
| D-2 | | | | | | | |

**Total estimated debt**: ~[N] engineer-days of rework
**Debt by category**: Duplication: [N]d, Principle: [N]d, Workflow: [N]d, AI: [N]d, Legacy: [N]d

---

## Remediation Roadmap

### Track 0: Emergency (Before Next Deploy)

| Finding | Owner | Deadline | Status |
|---------|-------|---------|--------|
| [C-1] | | | |

### Track 1: Current Sprint

| Finding | Estimate | Owner | Status |
|---------|---------|-------|--------|
| [H-1] | | | |
| [H-2] | | | |

### Track 2: Next 1–2 Sprints

| Finding | Estimate | Planned Sprint |
|---------|---------|---------------|
| [M-1] | | |

### Track 3: Rolling Backlog

| Debt/Finding | Priority | Notes |
|-------------|---------|-------|
| [L-1 / D-1] | | |

**Total remediation effort estimate**: ~[N] engineer-weeks

---

## Appendix

### A: Audit Methodology

This audit was conducted using the `feature-audit` + `full-audit` methodology (v2, 2026), covering:

1. **Feature Discovery** — All features mapped from entry points, routes, jobs, and event handlers
2. **Per-Feature Audit** — Each feature audited across 7 phases:
   - Phase 1: Discovery & pre-implementation review
   - Phase 2: Impact analysis
   - Phase 3: Implementation quality and bug detection
   - Phase 4: Test strategy and coverage
   - Phase 5: Consumer experience (UX / API / CLI / observability)
   - Phase 6: OWASP Top 10 (2025) security review
   - Phase 7: Code review standards
3. **Advanced Bug Detection** — Race conditions, resource leaks, null propagation, error swallowing,
   copy-paste bugs, state machine violations, temporal coupling, boundary errors, logic inversions
4. **Duplicate & Waste Code Analysis** — Type 1-4 clone detection, dead code, speculative generality,
   feature flag graveyards, over-abstraction
5. **Workflow & Data Flow Analysis** — Complete user journey tracing, error path verification,
   async lifecycle, transaction boundaries, retry/idempotency, cascading failure analysis
6. **Development Principles Assessment** — SOLID compliance, DRY, KISS, YAGNI, 12-Factor,
   Clean Architecture, cognitive complexity scoring
7. **Cross-Cutting Analysis** — System-wide patterns, AI-generated code quality, performance
   anti-patterns, dependency graph health, duplication hotspots
8. **Technical Debt Assessment** — Churn/complexity hotspots, debt register with categories
   (Duplication/Principle/Workflow/AI/Legacy)
9. **Scoring** — Using the extended scoring matrix (Critical/High/Medium/Low/Informational)
   with new categories for bugs, duplication, principles, and workflow gaps

### B: Tools Used

| Tool | Purpose | Result Location |
|------|---------|----------------|
| [tool] | Dependency vulnerability scan | [file or finding refs] |
| [tool] | Code coverage | [file or finding refs] |
| [tool] | Static analysis | [file or finding refs] |
| [tool] | Complexity measurement | [file or finding refs] |
| [tool] | Duplication detection | [file or finding refs] |
| [tool] | Dead code detection | [file or finding refs] |
| [tool] | Circular dependency check | [file or finding refs] |

### C: Auditor Notes

[Any contextual notes about the audit process, limitations, or scope changes that occurred]

### D: Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | [Date] | Initial report |
| 1.1 | [Date] | [What changed — e.g., added resolution status for C-1] |
