# Phase 0: Feature Planning & Technical Design

> "Weeks of coding can save you hours of planning." — Every experienced developer

This phase happens BEFORE you read existing code, BEFORE you analyze impact, and BEFORE you
write a single line. It ensures you solve the RIGHT problem with the RIGHT approach.

**When to use Phase 0**: New features, significant changes, uncertain requirements, or any
time the approach isn't immediately obvious.

**When to skip**: Small bug fixes, trivial refactors, or changes where the approach is
already well-understood.

---

## Step 1: Requirements Clarification

Before designing anything, answer these questions with precision:

### The Five W's of Features

| Question | What You Need | Red Flag If Missing |
|----------|--------------|-------------------|
| **WHO** needs this? | Specific user persona or system | "Everyone" = nobody designed for |
| **WHAT** exactly should it do? | Precise behavior description | Vague = will be built wrong |
| **WHY** is it needed? | Business value / user problem solved | No "why" = maybe shouldn't be built |
| **WHEN** is it needed? | Timeline constraints, dependencies | "ASAP" with no priority = scope creep |
| **WHERE** does it live? | Which system, service, layer | Unclear = architecture problems |

### Requirement Precision Test

For each requirement, apply this test:

```
"Can two different developers read this requirement and build the SAME thing?"
```

If no → the requirement is too vague. Ask clarifying questions until the answer is yes.

### Edge Cases to Identify Up Front

- What happens with empty/null/zero input?
- What happens with maximum/overflow input?
- What happens when an external service is down?
- What happens when two users do this simultaneously?
- What happens if the user cancels mid-flow?
- What happens if this is called 1000x per second?

---

## Step 2: Scope Definition

### In Scope vs Out of Scope

Explicitly define what you WILL and WILL NOT build:

```markdown
## Scope

### In Scope (this PR/sprint)
- [Specific deliverable 1]
- [Specific deliverable 2]

### Explicitly Out of Scope (future work)
- [Thing users might expect but we're not building now]
- [Optimization that isn't needed yet]

### MVP vs Full
- MVP: [Minimum that delivers value]
- Full: [Complete vision with all nice-to-haves]
- Building: [MVP / Full] because [reason]
```

### The YAGNI Test

For every piece of scope, ask:
- "Do we KNOW we need this, or do we THINK we might need it someday?"
- If "think" → cut it. Build it when you actually need it.
- If "know" → keep it. But verify: who asked for it? When will it be used?

---

## Step 3: Technical Design

### Approach Options

For any non-trivial feature, identify at least 2 approaches:

```markdown
## Design Options

### Option A: [Name]
- **Approach**: [How it works]
- **Pros**: [Why this is good]
- **Cons**: [Why this might be bad]
- **Effort**: [S/M/L]
- **Risk**: [What could go wrong]

### Option B: [Name]
- **Approach**: [How it works]
- **Pros**: [Why this is good]
- **Cons**: [Why this might be bad]
- **Effort**: [S/M/L]
- **Risk**: [What could go wrong]

### Decision: [A/B] because [reason]
```

### Design Decision Criteria

Rank these by importance for YOUR specific feature:

| Criterion | When It's #1 Priority |
|-----------|----------------------|
| **Simplicity** | Default for most features. Simplest correct solution wins. |
| **Performance** | Hot path, user-facing latency, high throughput requirement |
| **Extensibility** | Known upcoming variations (not hypothetical ones) |
| **Consistency** | Feature touches existing patterns that should match |
| **Time to market** | Competitive pressure, deadline-driven |
| **Reliability** | Financial, health, safety, or compliance-critical |

### Architecture Decision Record (ADR) Template

For significant decisions, document them:

```markdown
## ADR: [Decision Title]

**Status**: Proposed / Accepted / Deprecated
**Date**: [YYYY-MM-DD]
**Context**: [What situation led to this decision?]
**Decision**: [What did we decide?]
**Consequences**: [What are the trade-offs?]
**Alternatives considered**: [What else could we have done?]
```

---

## Step 4: Dependency Mapping

### What This Feature Depends On

| Dependency | Type | Risk |
|-----------|------|------|
| [Service/API/Library] | External / Internal | What if it's down/slow/changed? |
| [Team/person] | Human | Availability, review, approval |
| [Data/schema] | Technical | Migration needed? Compatible? |

### What Will Depend On This Feature

| Future Consumer | How They'll Use It | Implication |
|----------------|-------------------|------------|
| [Other feature/team] | [Read/Write/Subscribe] | [Design for their needs too?] |

### Blockers and Unblocking

- Are there technical blockers? (Missing API, pending migration, undeployed dependency)
- Are there human blockers? (Pending design review, awaiting requirement clarification)
- What can you start on NOW while blockers are being resolved?

---

## Step 5: Risk Identification

### What Could Go Wrong

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|-----------|
| [e.g., API is too slow for use case] | Medium | High | Prototype the slow path first |
| [e.g., Requirement changes mid-sprint] | High | Medium | Build MVP first, get early feedback |
| [e.g., Integration with service X fails] | Low | High | Build adapter layer, mock service |
| [e.g., Performance doesn't meet SLA] | Medium | High | Load test before merging |

### Risk Mitigation Strategy

- **High probability + High impact**: Address FIRST. Build a proof-of-concept for the risky part.
- **Low probability + High impact**: Have a fallback plan. Know what you'll do if it happens.
- **High probability + Low impact**: Accept and monitor. Don't over-engineer prevention.
- **Low probability + Low impact**: Ignore. Not worth thinking about.

---

## Step 6: Acceptance Criteria

### Definition of Done

Every feature needs explicit acceptance criteria. Use this format:

```markdown
## Acceptance Criteria

### Functional
- [ ] Given [precondition], when [action], then [expected result]
- [ ] Given [precondition], when [action], then [expected result]
- [ ] Edge case: [scenario] → [expected behavior]

### Non-Functional
- [ ] Response time < [X]ms for [operation]
- [ ] Works on [browsers/devices/screen sizes]
- [ ] Accessible via keyboard and screen reader

### Quality
- [ ] Unit tests cover all logic paths
- [ ] Integration test covers the happy path
- [ ] No new linting errors or type errors
- [ ] PR reviewed and approved

### Operations
- [ ] Feature flag in place (if applicable)
- [ ] Monitoring/alerting configured
- [ ] Rollback plan documented
```

---

## Step 7: Implementation Order

### Build for Fastest Feedback

The experienced developer builds in this order:

1. **The riskiest/hardest part first** — Fail fast. If this part doesn't work, better to know on day 1.
2. **The thinnest vertical slice** — End-to-end but minimal. Proves the architecture works.
3. **The happy path** — Core functionality working before edge cases.
4. **Error handling and edge cases** — Harden after the foundation works.
5. **Polish and optimization** — Last, because requirements might change.

### Anti-Pattern: Building Bottom-Up

Don't build the database layer → service layer → API → UI in sequence.
Instead: build a thin slice through ALL layers first. Then widen.

```
DON'T:  DB ━━━━━━━━━━━━━━━┓
        Service ━━━━━━━━━━━┫  (can't demo until all layers done)
        API ━━━━━━━━━━━━━━━┫
        UI ━━━━━━━━━━━━━━━━┛

DO:     ┃ Slice 1 (thin, all layers) → Demo/Feedback → Slice 2 → Slice 3
```

---

## Step 8: Ship/Show/Ask Decision

Before starting, decide how this change will flow:

| Category | When to Use | Process |
|----------|------------|---------|
| **Ship** | Established pattern, low risk, small change | Merge directly, no review wait |
| **Show** | New pattern, medium risk, learning opportunity | Open PR, merge immediately, get async feedback |
| **Ask** | Uncertain approach, high risk, needs discussion | Open PR, wait for review before merging |

**Factors that push toward "Ask"**:
- Touching auth/payment/data integrity
- New architectural pattern
- Cross-team impact
- You're unsure about the approach
- Large blast radius (many files/features affected)

**Factors that push toward "Ship"**:
- Bug fix using established pattern
- Documentation update
- Configuration change
- Test addition with no behavior change
- You've done this exact pattern 10 times before

---

## Planning Output Template

After completing Phase 0, you should have:

```markdown
## Feature Plan: [Feature Name]

### Requirements
[1-3 sentence description of what this does and for whom]

### Scope
- In: [bulleted list]
- Out: [bulleted list]

### Technical Approach
[Selected approach + brief justification]

### Key Risks
1. [Risk 1] → [Mitigation]
2. [Risk 2] → [Mitigation]

### Acceptance Criteria
- [ ] [Criterion 1]
- [ ] [Criterion 2]

### Implementation Order
1. [First thing to build]
2. [Second thing]
3. [Third thing]

### Estimated Effort
[S/M/L with brief justification]

### Ship/Show/Ask
[Decision + reason]
```
