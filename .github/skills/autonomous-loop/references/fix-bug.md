# Fix Bug Workflow — Autonomous Loop Reference

When the user reports a **bug, error, crash, or broken behavior**, follow this diagnostic
and repair protocol within the autonomous loop.

---

## The Bug-Fix Loop

```
┌─────────────────────────────────────────────────────────┐
│  1. REPRODUCE  — Confirm the bug exists (failing test)  │
│  2. ISOLATE    — Narrow to root cause (not symptoms)    │
│  3. FIX        — Minimal, targeted repair               │
│  4. VERIFY     — Failing test now passes                │
│  5. REGRESS    — All other tests still pass             │
│  6. ASSESS     — More bugs? Loop. All green? Done.      │
└─────────────────────────────────────────────────────────┘
```

---

## Phase 1: Reproduce (Iteration 1–2)

### Gather Evidence

Before touching code:
1. Read the error message completely (stack trace, error code, line number)
2. Identify the exact file and line where the error occurs
3. Understand the expected behavior vs actual behavior

### Write a Failing Test

**This is the most important step.** Always write a test that:
- Triggers the exact bug described
- Fails RIGHT NOW with the same error
- Will pass ONLY when the bug is truly fixed

```
# Pseudo-pattern for any language:
def test_the_reported_bug():
    # Setup: create the conditions that trigger the bug
    # Action: perform the operation that fails
    # Assert: verify the CORRECT behavior (currently fails)
```

**If you can't write a test** (UI bug, environment issue):
- Create a minimal reproduction script
- Document the exact steps to trigger
- Use the script as your verification after fix

### Verify Reproduction

Run the test. It MUST fail. If it passes, you've misunderstood the bug.
Go back and re-read the error report.

---

## Phase 2: Isolate Root Cause (Iterations 2–5)

### Scientific Debugging Method

1. **Observe**: What exactly happens? (error message, incorrect output, crash)
2. **Hypothesize**: What could cause this? (list 2-3 likely causes)
3. **Test hypothesis**: Check each one systematically
4. **Conclude**: Identify the ACTUAL root cause (not just a symptom)

### Isolation Techniques

**Binary Search Debugging:**
- If the bug is in a long function, add a checkpoint halfway
- Does the bug occur before or after the checkpoint?
- Repeat until you've narrowed to 5-10 lines

**Trace Data Flow:**
- What value enters the buggy function?
- What transformations does it undergo?
- At which transformation does it become incorrect?

**Check Recent Changes:**
- What was the last change to the affected file?
- Did the bug exist before that change?
- Is there a git blame showing when the problematic line was introduced?

### Common Root Causes (Check These First)

| Symptom | Likely Root Cause |
|---------|------------------|
| `undefined is not a function` | Wrong import, missing export, typo in method name |
| `Cannot read property of null` | Missing null check, async race condition |
| `Type error` / wrong type | Incorrect type assertion, missing conversion |
| `Connection refused` | Wrong port, service not running, env var missing |
| `404 Not Found` | Wrong route path, missing handler registration |
| Test passes locally, fails in CI | Environment difference, timing issue, missing dep |
| Works first time, fails on second | State mutation, missing cleanup, stale cache |
| Off-by-one | Loop boundary, array index, string slice |
| Silent failure (no error, wrong result) | Logic error, wrong variable, inverted condition |

### Identify the Single Line

Your goal is to identify the **exact line(s)** that contain the bug.
Not the file. Not the function. The LINE.

---

## Phase 3: Implement Fix (Iteration 3–6)

### Minimal Fix Principle

The fix should:
- Change as few lines as possible
- Fix the root cause (not just suppress the symptom)
- Not introduce new behavior beyond fixing the bug
- Not refactor or "improve" surrounding code (that's a separate task)

### Fix Patterns

**Wrong logic:**
```
# Before (bug): inverted condition
if (user.isAdmin) { denyAccess(); }

# After (fix): correct condition
if (!user.isAdmin) { denyAccess(); }
```

**Missing null check:**
```
# Before (bug): crashes on null
const name = user.profile.name;

# After (fix): safe access
const name = user.profile?.name ?? 'Unknown';
```

**Wrong type / missing conversion:**
```
# Before (bug): string concatenation instead of addition
const total = price + tax; // both are strings!

# After (fix): explicit conversion
const total = Number(price) + Number(tax);
```

**Race condition:**
```
# Before (bug): uses value before it's set
const data = fetchData();
processData(data); // data is a Promise!

# After (fix): await the async operation
const data = await fetchData();
processData(data);
```

### What NOT to Do

❌ Add `try/catch` that swallows the error silently
❌ Add `|| defaultValue` that hides the real problem
❌ Disable the failing test
❌ Add `@ts-ignore` or `# type: ignore`
❌ Change the test expectations to match the broken behavior

---

## Phase 4: Verify Fix (Iteration 4–7)

### Run the Failing Test

The test you wrote in Phase 1 must now PASS.

If it still fails:
- Your fix is incomplete
- Go back to Phase 3 and adjust
- If it fails differently, you may have introduced a new bug

### Run All Tests

All pre-existing tests must still pass. If any fail:
- Your fix introduced a regression
- The fix is too broad or touches shared code incorrectly
- Adjust the fix to be more targeted

### Run Type Checker and Linter

- No new type errors introduced
- No new lint warnings
- Build still succeeds

---

## Phase 5: Regression Check (Iteration 5–8)

### Verify Adjacent Functionality

Test the features that are NEAR the bug:
- Same module
- Same API endpoint
- Same user flow
- Functions that call the fixed code

### Edge Cases

After fixing, consider:
- Does the fix work for empty input?
- Does the fix work for very large input?
- Does the fix work at system boundaries (null, 0, max_int)?
- Does the fix work in concurrent scenarios?

---

## Multi-Bug Loop

If the user reports multiple bugs, or if fixing one reveals another:

```
FOR each bug (prioritized by severity):
  1. Reproduce (failing test)
  2. Isolate (root cause)
  3. Fix (minimal change)
  4. Verify (test passes)
  5. Regress (all tests pass)
NEXT bug
```

**Priority order:**
1. Crashes / data loss (P0)
2. Broken core functionality (P1)
3. Incorrect behavior (P2)
4. Performance issues (P3)
5. Cosmetic issues (P4)

---

## When You're Stuck

If you can't find the root cause after 3 iterations of hypothesize-test:

1. **Add logging**: Insert console.log/print at key points to trace execution
2. **Simplify**: Remove complexity until the bug disappears, then add back piece by piece
3. **Check assumptions**: Verify that input values are what you think they are
4. **Read the docs**: The API might not work the way you assume
5. **Fresh perspective**: Delete your current hypothesis and start from the error message again

---

## Quality Checklist (Before Declaring Bug Fixed)

- [ ] Failing test written that reproduces the exact bug
- [ ] Root cause identified (not just symptoms treated)
- [ ] Fix is minimal (changes only what's necessary)
- [ ] Originally failing test now passes
- [ ] All other tests still pass
- [ ] No new type errors or lint warnings
- [ ] Build succeeds
- [ ] Fix doesn't introduce new edge cases
- [ ] The same class of bug can't happen elsewhere (quick scan)
