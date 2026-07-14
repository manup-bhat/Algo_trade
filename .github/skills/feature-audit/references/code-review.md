# Phase 7: Code Review & Ship Standards

Based on Google Engineering Practices, GitHub Staff Engineer philosophy (Sarah Vessels, 2024),
and roadmap.sh Code Review Best Practices.

> "Code review's importance for product quality can't be overstated, especially in the age
> of AI code generation. Many times in my career, a bug has been caught or an incident
> avoided simply by having that second set of eyes."
> — Sarah Vessels, GitHub Staff Software Engineer

---

## Before Requesting Review: Self-Review Protocol

**Review your own code before asking others.** This single habit eliminates a category of
avoidable review feedback and makes you a better developer.

### Self-Review Checklist (Author)

#### Before Coding (Pre-Development)
- [ ] Requirements and context understood; questions asked before starting
- [ ] Impact analysis complete — all affected files identified
- [ ] Approach discussed with team for large or ambiguous changes

#### During Development
- [ ] Code follows project coding standards and style guide consistently
- [ ] Design is consistent with overall project architecture
- [ ] Consider impact on other parts of the system at every step
- [ ] Tests written alongside (or before) production code

#### Post-Development, Before Submitting
- [ ] Re-read your entire diff as if you're the reviewer
- [ ] Every comment you'd leave on someone else's code — address it now
- [ ] All tests pass locally (unit + integration + lint)
- [ ] No debug code, `console.log`, `print()`, or commented-out code committed
- [ ] No new `TODO` or `FIXME` without a linked tracking issue
- [ ] PR description written: WHAT changed, WHY, how to test it
- [ ] Screenshots or demo included for visual/UI changes
- [ ] Breaking changes documented in the description
- [ ] PR is as small as possible — one logical change per PR

---

## Writing Good PR Descriptions

A PR description is not "see JIRA-1234." It is the author's explanation to reviewers (and future git blame readers).

```markdown
## What

Adds a 10% discount for orders over $500 for premium customers.

## Why

Premium customers asked for this in user research (TICKET-1234).
Discount threshold is intentionally conservative — data shows only 3% of orders
qualify, so revenue impact is minimal relative to retention benefit.

## How

- Added `calculateDiscount(order, customer)` in `OrderPricingService`
- Updated `OrderController.create()` to apply discount before total calculation
- Discount is logged in `order_discounts` table for analytics

## Testing

- Unit tests for `calculateDiscount()` covering all threshold cases
- Integration test for full order creation flow with discount
- Run: `npm test -- --testPathPattern=OrderPricing`

## Screenshots

[Include before/after screenshots for UI changes]

## Breaking Changes / Migration Required

None — purely additive feature behind existing order creation flow.
```

---

## Google Engineering Practices: What Reviewers Look For

Adapted from https://google.github.io/eng-practices/review/reviewer/looking-for.html

### Design
- Does the change make sense for the overall system?
- Is this the right place in the codebase for this logic?
- Does it integrate well with the rest of the system?
- Is this the right time to add this functionality?

### Functionality
- Does the code behave as the developer intended?
- Is what the developer intended actually good for users?
- Have edge cases been considered? (null input, concurrent users, slow network)
- Are there any race conditions or concurrency problems?

### Complexity
- Could the code be made simpler?
- Would another developer understand this quickly?
- Is the developer solving a problem that exists now — not a speculative future problem?
- Is there over-engineering? ("Made it generic just in case")

### Tests
- Are there unit, integration, or E2E tests appropriate for the change?
- Are the tests correct? Will they actually fail when the code breaks?
- Are tests well-designed? Not testing implementation details?
- Do tests cover edge cases, not just happy paths?
- Are tests code that will be maintained — treated with the same care as production code?

### Naming
- Are all names clear and self-documenting?
- Are names long enough to communicate fully, but not awkwardly long?
- Do boolean names start with `is`, `has`, `can`, `should`?

### Comments
- Are comments clear and useful?
- Do comments explain WHY, not WHAT?
- Are there comments that are now wrong or obsolete (from old behavior)?
- Are there `TODO`s that can finally be resolved?

### Style
- Does the code follow the project's style guide?
- Is it consistent with the surrounding code?
- Style-only changes should be in a separate PR, not mixed with functional changes

### Documentation
- If behavior changed, is the documentation updated?
- If an API changed, are API docs (OpenAPI/Swagger) updated?
- If the README referenced the feature, is it still accurate?
- If something was deprecated or deleted, is the documentation removed or updated?

---

## GitHub Staff Engineer Review Philosophy

Adapted from Sarah Vessels' approach:

### Ask Questions, Not Demands

> "I treat the author's understanding of the particulars as better than mine."

```
// Less good:
"This is wrong."

// Better:
"I'm not sure I follow the logic here — what happens if `userId` is null 
on line 42? Does the caller guarantee it's always set?"
```

### Challenge Assumptions

- What is the shape of the data you're working with?
- Does data exist that doesn't match that shape?
- Will this perform well at scale? (What happens with 10,000 records?)
- Is the code resource-intensive? Is that acceptable?

**Best response from an author**: A test that verifies the edge case.
**Second-best response**: Empirical data (query result, monitoring graph, benchmark).

### Offer Affirmations

> "Code reviews often just focus on mistakes, but they should offer encouragement."

Comment on things done well:
- "Looks like this matches the pattern used in other classes in this module — nice consistency."
- "Thanks for adding a test for this edge case!"
- "This is much cleaner than the previous version."

### Be Precise and Specific

```
// Vague and unhelpful:
"I don't like this."

// Clear and actionable:
"This method is doing three things (validation, persistence, and sending an email). 
It would be easier to test and maintain if each responsibility was in its own method.
Could we split this along those lines?"
```

### Distinguish Priority Levels

Use clear prefixes so the author knows what's blocking vs. optional:
- **Blocker**: Must be addressed before merge (correctness, security, breaking change)
- **Nit**: Minor style or preference. "Nit: `userList` could be `users` per project naming conventions."
- **Optional**: Suggestion worth considering but not required: "Optional: would be great to add a test for the empty case here."

---

## When to Approve vs. Request Changes

### Approve (with optional suggestions)

> "If suggestions' absence isn't going to make someone's day worse, let the author decide."

Approve when:
- The code is correct and won't break production or negatively impact users
- There are no security issues
- Your remaining comments are style preferences or nice-to-haves
- The author is trusted and the area of code is well-tested

### Request Changes

Use "Request Changes" sparingly. Reserve it for:
- Immediate security vulnerabilities you're worried will be merged before seen
- Clear correctness bugs that will affect users
- Missing tests on critical logic

For everything else: **approve with comments** and trust the author to address non-blockers.

---

## Draft PR Discipline

- Open PRs as **Draft** while:
  - CI is still failing
  - You're still writing code
  - You haven't done your self-review yet
  - You're resolving merge conflicts or addressing feedback

- Mark **Ready for Review** only when:
  - CI is fully green
  - Self-review is complete
  - You're done making changes

- Move **back to Draft** when addressing review feedback that requires significant rework

---

## Handling AI-Generated Code in Reviews

AI tools (GitHub Copilot, Cursor, Claude) can produce code that looks correct but has subtle issues.

**Extra scrutiny for AI-generated code**:
- [ ] Does the logic actually match the requirement? (AI often generates plausible-but-wrong logic)
- [ ] Are there security implications the AI might have missed? (Injection, access control)
- [ ] Are the tests generated by AI actually meaningful assertions, or do they just pass?
- [ ] Is the code using APIs correctly? (AI can confidently use deprecated or nonexistent APIs)
- [ ] Does the code fit the patterns of this codebase, or is it generic boilerplate?

> "As the human reviewer at the helm, you are the last line of defense and should review all code with an equal level of diligence." — GitHub Blog

---

## Navigating a Large PR

When reviewing a large change (Google Engineering Practices — CL Navigation):

1. **Broad view first**: Read the PR description. Does this change make sense? Is the approach sound?
2. **Find the main file**: The file with the most logical changes. Review it first to understand the core change.
3. **Send design feedback immediately**: If the design is fundamentally wrong, say so now — before reviewing every other file. (Saves everyone time.)
4. **Then review the rest**: Go through remaining files logically. Tests first can help — they tell you what the change is supposed to do.

**If the PR is too large to review effectively**: Ask the author to split it. Smaller PRs are reviewed better, merged faster, and easier to revert.

---

## Post-Merge Responsibility

The review doesn't end at merge.

- **Monitor the deployment**: Watch error rates, performance metrics, and logs after deploying
- **Be available**: If your PR caused an incident, be ready to roll back or hotfix immediately
- **Welcome post-merge reviews**: If someone reviews after merge and finds something — that's valuable. Address it in a follow-up PR.
- **Follow through on promises**: If you said "I'll address X in a follow-up PR", do it and link back to the original review comment.
