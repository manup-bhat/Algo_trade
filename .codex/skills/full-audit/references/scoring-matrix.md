# Scoring Matrix — Severity Definitions for Audit Findings

Consistent, calibrated severity scores allow findings to be prioritized correctly across
the entire codebase, regardless of which auditor identified them.

This matrix applies to all finding types: security, quality, testing, observability, and UX.

---

## Severity Levels

### Critical

**Definition**: An active or near-immediate risk of harm to users, data, or system availability.
No waiting period acceptable. Requires immediate response regardless of business context.

**Characteristics**:
- Exploitable without authentication or with minimal user interaction
- Leads directly to data breach, authentication bypass, or system compromise
- OR: The application is non-functional for a large portion of users

**Security examples**:
- SQL injection with confirmed data exfiltration path
- Authentication bypass (any user can act as any other user)
- Exposed credentials in source code or logs
- Remote code execution vector
- Unprotected admin functionality accessible to all

**Quality examples**:
- Data loss bug (records permanently deleted incorrectly, migrations destroying data)
- Corruption of financial or transactional records
- Race condition causing double-charge or duplicate transaction

**Response**: Fix before next deploy. Escalate immediately to team lead/security.

---

### High

**Definition**: A significant risk that is not yet actively exploited but is easily exploitable,
or a quality issue that regularly causes user-facing failures.

**Characteristics**:
- Requires attacker account, moderate effort, or specific conditions to exploit
- Causes material harm to a subset of users or a specific workflow
- OR: Reduces trust in the system significantly

**Security examples**:
- Insecure Direct Object Reference (IDOR) — user can access other users' records by changing an ID
- Broken access control for privileged actions
- Stored XSS in fields rendered to other users
- Missing CSRF protection on sensitive mutation endpoints
- Sensitive data returned in API responses unnecessarily (tokens, hashed passwords)

**Quality examples**:
- Critical user journey has zero test coverage
- Error swallowed silently causing incorrect state
- Unchecked null access causing 500 errors in production
- Non-idempotent operation retried without protection

**Response**: Fix within current sprint. Do not ship new features to the same area until resolved.

---

### Medium

**Definition**: A risk or quality issue that could cause harm under specific conditions, or
reduces maintainability / observability significantly.

**Characteristics**:
- Requires specific conditions, specific data, or chained with other issues to exploit
- Degrades the consumer experience but does not prevent core functionality
- Reduces confidence in the codebase for future maintainers

**Security examples**:
- Reflected XSS (requires user to visit crafted URL)
- Missing rate limiting on non-critical endpoints
- Overly verbose error messages (stack traces visible in staging but not production)
- Outdated dependency with known CVE but no confirmed exploit path
- Insecure password policy (weak minimum length)

**Quality examples**:
- Feature works but has no tests for the error path
- Business logic duplicated in 3+ places, diverged from each other
- Cyclomatic complexity > 20 in a high-churn function
- Missing structured logging for a critical operation
- Feature flag never removed after full rollout (3+ months stale)

**Response**: Fix within next sprint or add to backlog with priority label.

---

### Low

**Definition**: A minor issue, code quality concern, or deviation from best practices
that has no direct impact on security or correctness.

**Characteristics**:
- No realistic harm path
- Could become a problem at scale or if another issue is introduced

**Security examples**:
- Missing `Referrer-Policy` header on a non-sensitive endpoint
- Security header present but set to a permissive value
- Verbose endpoint that returns more fields than strictly necessary

**Quality examples**:
- Inconsistent naming convention (camelCase vs snake_case in same file)
- TODO comment without a linked issue
- Function with 4 parameters that could use a params object
- Slightly misleading variable name

**Response**: Fix opportunistically when touching the file, or batch into a tech debt sprint.

---

### Informational

**Definition**: An observation, suggestion, or note that is not a problem today but may
be worth considering for future improvement.

**Examples**:
- "This algorithm works now but may not scale past 10,000 records — monitor"
- "OpenAPI docs are present but no request/response examples provided"
- "Consider adding contract tests when this API gains a second consumer"
- "This module has grown complex — consider splitting if it continues to grow"

**Response**: Document for awareness. No action required.

---

## Severity Decision Guide

Use this flowchart when unsure:

```
Is there a confirmed or near-certain path to data breach, auth bypass, or data loss?
  → YES: Critical

Is there a high-likelihood path to user harm, security bypass, or regular production failure?
  → YES: High

Could this cause harm under specific conditions OR does it significantly reduce confidence?
  → YES: Medium

Is it a style/quality concern with no direct harm path?
  → YES: Low

Is it purely an observation or future consideration?
  → YES: Informational
```

---

## Severity by Finding Type Quick Reference

| Finding Type | Critical | High | Medium | Low |
|-------------|---------|------|--------|-----|
| Auth bypass | ✓ | | | |
| IDOR / access control | | ✓ | | |
| SQL / command injection | ✓ | | | |
| XSS (stored) | ✓ | | | |
| XSS (reflected) | | | ✓ | |
| Exposed secret in code | ✓ | | | |
| Exposed secret in logs | | ✓ | | |
| No auth on endpoint | ✓ or ✓ | | | |
| Missing rate limiting (critical action) | | ✓ | | |
| Missing rate limiting (non-critical) | | | ✓ | |
| CVE (confirmed exploitable) | ✓ | | | |
| CVE (unconfirmed exploit path) | | | ✓ | |
| Zero test coverage on critical path | | ✓ | | |
| Missing error-path tests | | | ✓ | |
| Silent error swallowing | | ✓ | | |
| Missing structured logs | | | ✓ | |
| Naming inconsistency | | | | ✓ |
| TODO without issue | | | | ✓ |

---

## CVSS Mapping (Security Findings)

For security findings that need a formal CVSS score (compliance, audit reports):

| Severity | CVSS Range |
|---------|-----------|
| Critical | 9.0 – 10.0 |
| High | 7.0 – 8.9 |
| Medium | 4.0 – 6.9 |
| Low | 0.1 – 3.9 |
| Informational | 0.0 |

Use the [CVSS Calculator](https://www.first.org/cvss/calculator/3.1) for precise scoring on High/Critical security findings.

---

## Finding Record Format

Standardize all findings using this format for consistent tracking and reporting:

```markdown
### Finding #[N]: [Short Title]

| Field | Value |
|-------|-------|
| Severity | Critical / High / Medium / Low / Informational |
| Category | Security / Quality / Testing / Observability / UX / Docs / Duplication / Principles / Workflow / Bug |
| Feature | [Feature name or "Cross-cutting"] |
| File / Location | [file:line or description] |
| CVSS (if security) | [score] / [vector string] |
| Principle Violated | [SRP / OCP / LSP / ISP / DIP / DRY / KISS / YAGNI / N/A] |

**Description**:
[What is the issue? What is the impact?]

**Evidence**:
[Code snippet, log excerpt, test output, screenshot — whatever confirms the finding]

**Recommendation**:
[What should be done to fix or mitigate it?]

**References**:
[OWASP link, CVE number, internal doc, or other context]
```

---

## Extended Severity Matrix — New Finding Categories

### Duplication Severity

| Severity | Condition |
|----------|-----------|
| **High** | Same business logic in 4+ places; divergence already causing bugs |
| **Medium** | Same logic in 2-3 places; no bugs yet but maintenance risk |
| **Low** | Duplicate boilerplate/setup code; low divergence risk |
| **Informational** | Near-duplicate test setup; acceptable for test readability |

### Principle Violation Severity

| Severity | Condition |
|----------|-----------|
| **High** | SOLID violation causing bugs or preventing feature development |
| **High** | DIP violation making feature untestable (no mocking possible) |
| **Medium** | SRP violation: file > 500 lines, growing with each sprint |
| **Medium** | OCP violation: switch statement growing with each new feature |
| **Low** | Minor DRY violation: 2 copies, no divergence yet |
| **Low** | KISS violation: over-engineered but working correctly |
| **Informational** | YAGNI: unused abstraction but not causing harm |

### Workflow Gap Severity

| Severity | Condition |
|----------|-----------|
| **Critical** | Missing error handling on payment/financial operations |
| **Critical** | Transaction boundary missing — partial writes possible |
| **High** | Missing error handling on critical user journey (data loss risk) |
| **High** | Fire-and-forget async without monitoring (silent failures) |
| **Medium** | Non-critical error path returns generic error to user |
| **Medium** | Missing timeout on external service call |
| **Low** | Minor UX gap: error message unclear but operation is safe |

### Bug Detection Severity

| Severity | Condition |
|----------|-----------|
| **Critical** | Race condition in auth/payment/data integrity path |
| **Critical** | Resource leak in hot path (will cause outage) |
| **High** | Null propagation crash on common user flow |
| **High** | Error swallowing hiding data corruption |
| **Medium** | Copy-paste bug in non-critical path |
| **Medium** | State machine allowing invalid but non-harmful transition |
| **Low** | Logic inversion in logging (wrong level used) |
| **Low** | Off-by-one in non-critical display logic |

### Reusability Score (Per Module)

| Score | Rating | Condition |
|-------|--------|-----------|
| 90-100 | Excellent | Clear API, well-tested, documented, no coupling to infrastructure |
| 70-89 | Good | Reusable with minor adaptation, few external dependencies |
| 50-69 | Fair | Reusable but has unnecessary coupling or complexity |
| 30-49 | Poor | Tightly coupled, would require significant refactoring to reuse |
| 0-29 | Not reusable | God class, circular deps, untested, hardcoded config |
