# Phase 8: Fix Verification & Regression Prevention

> "After having successfully validated the fix, we still have some homework to make."
> — The Debugging Book

A fix is not complete when the code compiles and the test passes. A properly verified fix
proves it addresses the root cause, doesn't break anything else, and prevents the same
class of bugs from occurring again.

---

## The 7-Point Fix Verification Checklist

Every fix — whether a bug fix, improvement, or refactor — must pass ALL of these:

### 1. Causality Proven

> "Does your fix directly address the identified root cause?"

| ✅ Good Fix | ❌ Bad Fix |
|------------|-----------|
| "The condition was `>` instead of `>=`, causing off-by-one at boundary" | "I added a special case for the boundary value" |
| "The lock wasn't acquired before shared state mutation" | "I added a retry that usually avoids the race" |
| "The query didn't filter by tenant_id, returning other users' data" | "I added a UI check to hide data that shouldn't be shown" |

**Test**: Can you explain in one sentence HOW the old code was wrong and WHY the new code is right?

---

### 2. Incorrectness Proven

> "Can you explain WHY the old code was incorrect, not just that the new code works?"

This prevents "accidental fixes" — changes that appear to work but don't address the real problem.

**Verification approach**:
1. Read the old code and explain its logic
2. Identify the specific logical error (not just "it didn't work")
3. Explain why the new code is correct for ALL cases, not just the failing one
4. Verify the fix handles the general case, not just the specific reproducing input

---

### 3. Regression Test Exists

> "A test that FAILS without the fix and PASSES with the fix."

**The regression test must**:
- Use the exact input/conditions that triggered the original bug
- Assert the CORRECT behavior (not just "no crash")
- Be part of the permanent test suite (never deleted)
- Be named to indicate what bug it prevents (e.g., `test_bug_1234_unicode_in_search`)

**Verification procedure**:
```bash
# 1. Stash your fix
git stash

# 2. Run the regression test — it MUST FAIL
npm test -- --testPathPattern="test_bug_1234"  # or your equivalent

# 3. Restore your fix
git stash pop

# 4. Run the regression test — it MUST PASS
npm test -- --testPathPattern="test_bug_1234"

# 5. Run the full test suite — NOTHING ELSE should break
npm test
```

If the test passes WITHOUT your fix → your test doesn't actually test the bug. Rewrite it.

---

### 4. Same-Pattern Check

> "After finding one instance of a bug pattern, check if it exists elsewhere."

**The same programmer, the same pattern, the same assumption** → often the same bug exists in multiple places.

```bash
# Find all instances of the same code pattern
grep -rn "<the-pattern-that-was-wrong>" ./src | grep -v test

# Examples:
# If bug was: using == instead of === for comparison
grep -rn "== " ./src --include="*.ts" | grep -v "===\|!==\|test\|spec"

# If bug was: missing null check after .find()
grep -rn "\.find(" ./src | grep -v "if\|?\.\|!= null\|test"

# If bug was: missing await on async call
grep -rn "async " ./src | grep -v "await\|test\|spec"
```

**Document what you found**: If the same pattern exists elsewhere, either fix all instances now or file tickets for each.

---

### 5. No New Edge Cases Introduced

> "Does your fix work for ALL inputs, or just the one that was failing?"

Check that your fix handles:
- [ ] The original failing input (obviously)
- [ ] The inputs that were previously working (no regression)
- [ ] Boundary values (empty, null, max, min, zero)
- [ ] Concurrent access (if applicable)
- [ ] The "opposite" of the failing case

**Example**: If the bug was "crash on empty string input", verify your fix also handles:
- null/undefined input
- Very long string input
- String with special characters
- String with only whitespace

---

### 6. Defensive Assertions Added

> "Add assertions at the bug site that will catch future violations early."

At the location where the bug existed, add an assertion that makes the ASSUMPTION explicit:

```javascript
// Before (the bug site):
function processOrder(order) {
  // Bug was: order.items could be undefined
  const total = order.items.reduce((sum, item) => sum + item.price, 0);
}

// After (with defensive assertion):
function processOrder(order) {
  assert(order.items != null, "processOrder requires order.items to be defined");
  const total = order.items.reduce((sum, item) => sum + item.price, 0);
}
```

**The assertion serves three purposes**:
1. Catches the bug immediately if the precondition is violated again
2. Documents the assumption for future developers
3. Fails loudly instead of silently corrupting data

---

### 7. Documentation Updated

> "If the fix changes behavior that users or developers rely on, update the docs."

Check and update:
- [ ] API documentation (if response format/behavior changed)
- [ ] README or setup guides (if configuration changed)
- [ ] Inline comments (remove outdated comments, add explanation of the fix)
- [ ] CHANGELOG (if user-visible behavior changed)
- [ ] Error messages (if the user-facing error was misleading)

---

## Post-Fix Homework

After the fix is verified and merged, do this additional work:

### Check for Further Defect Occurrences

```bash
# Was this a one-off, or part of a pattern?
# Check: same file, same function, same developer, same time period

# Other code by the same author around the same time
git log --author="<developer>" --since="<around-bug-date>" --oneline

# Same type of error in similar files
grep -rn "<error-pattern>" ./src | grep -v test
```

### Consider Prevention Mechanisms

| If the bug was... | Consider adding... |
|-------------------|-------------------|
| Type confusion | Stricter TypeScript/mypy types, runtime validation |
| Missing null check | Non-nullable types, lint rule for `.find()` usage |
| Race condition | Lint rule for shared state access, architectural review |
| Missing validation | Schema validation at boundaries (Zod, Pydantic, etc.) |
| Wrong assumption | Assertion or invariant check in the code |
| Outdated dependency | Automated dependency update (Dependabot, Renovate) |

### Update Testing Strategy

If the bug escaped all existing tests, ask:
- What kind of test would have caught this?
- Is there a gap in the test pyramid for this area?
- Should this type of check be automated (lint rule, type check, CI gate)?

---

## Fix Quality Tiers

Not all fixes are equal. Rate your fix:

| Tier | Quality | Characteristics |
|------|---------|----------------|
| **Tier 1: Excellent** | Root cause fixed + same pattern fixed everywhere + prevention mechanism added + regression test + assertions | The bug and its entire class are eliminated |
| **Tier 2: Good** | Root cause fixed + regression test + same-pattern check done | The bug won't recur, and you looked for siblings |
| **Tier 3: Acceptable** | Root cause fixed + regression test | The specific bug is fixed and tested |
| **Tier 4: Minimum** | Bug fixed but no regression test | Risky — may recur. Add test before merging. |
| **Tier 5: Unacceptable** | Symptom fixed, root cause unknown | Will recur. Go back to diagnosis phase. |

**Target**: Tier 2 for most bugs, Tier 1 for critical/recurring bugs.

---

## Ship/Show/Ask for Bug Fixes

| Fix Type | Recommended Flow |
|----------|-----------------|
| Typo / obvious one-liner | **Ship** — merge directly |
| Known pattern, clear root cause, has test | **Show** — open PR, merge immediately, invite async review |
| Complex fix, multiple files, tricky logic | **Ask** — open PR, wait for review |
| Security fix, data integrity, financial | **Ask** — require 2 reviewers, security review |
| You're unsure the fix is correct | **Ask** — explain your diagnosis in the PR, ask for validation |

---

## Fix Verification Summary Template

Use this when documenting your fix in the PR description:

```markdown
## Bug Fix: [Title]

### Root Cause
[One paragraph explaining WHAT was wrong and WHY]

### Fix
[One paragraph explaining what you changed and why it's correct]

### Verification
- [x] Regression test added: `test_name_here`
- [x] Test fails without fix, passes with fix
- [x] Full test suite passes
- [x] Same pattern checked elsewhere: [N instances found / fixed / ticketed]
- [x] No new edge cases introduced
- [ ] Defensive assertion added at bug site
- [ ] Documentation updated

### Risk Assessment
- Blast radius: [Low/Medium/High — how many things could this affect?]
- Confidence: [High/Medium/Low — how sure are you this is correct?]
- Rollback plan: [How to undo if something goes wrong]
```
