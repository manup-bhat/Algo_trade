# Phase 3B: Scientific Bug Detection & Root Cause Analysis

> "Every time you encounter a bug, this means that our earlier tests have failed. We thus need
> to introduce another test that documents not only how the bug came to be, but also the result
> we actually expected." — Andreas Zeller, The Debugging Book

> "Before fixing the defect, have a complete diagnosis that shows causality (how the defect
> causes the failure) and incorrectness (how the defect is wrong)." — The Debugging Book

Finding and fixing bugs correctly — not just suppressing symptoms — requires a disciplined
investigation process using the scientific method. Rushing to a fix without understanding the
root cause means the bug will return, often in a different form.

**This file covers**: The complete experienced-developer approach to debugging any bug in any
tech stack, from initial report to verified fix.

---

## The Debugging Process — Overview

```
Bug Report → Reproduce → Hypothesize → Experiment → Diagnose → Fix → Verify → Prevent
     │            │           │             │           │        │       │         │
     ▼            ▼           ▼             ▼           ▼        ▼       ▼         ▼
  Understand   Create      Scientific    Test your   Prove     Apply   Prove    Check for
  what's wrong failing     method:       prediction  BOTH      the     fix is   same pattern
               test        "If X then Y"             causality fix     correct  elsewhere
                                                     AND
                                                     incorrectness
```

---

## Step 1: Understand the Bug Report

Before touching any code, ensure you understand:

| Question | Why It Matters |
|----------|---------------|
| **What is the expected behavior?** | Can't fix what you can't define as "correct" |
| **What is the actual behavior?** | Precise symptom, not interpretation |
| **When did it start?** | Recently? Always? After a specific deploy? |
| **Who is affected?** | All users? Specific accounts? Specific environments? |
| **How often?** | Always? Intermittent? Under specific conditions? |
| **What's the business impact?** | Determines urgency and thoroughness of fix |

### Gathering Context

```bash
# When did the behavior change? Check recent commits to the area
git log --oneline --since="2 weeks ago" -- <affected-files>

# Who last modified the affected code?
git blame <file> | grep -A 2 -B 2 <affected-line>

# Were there any related changes nearby?
git log --oneline --all -- <directory>/ | head -20
```

---

## Step 2: Reproduce the Bug — ALWAYS FIRST

> "Can't fix what you can't reproduce."

**Never skip reproduction.** A fix without a reproduction is a guess.

### Reproduction Recipe Template

```markdown
## Reproduction Steps

**Environment**: [OS, browser, Node version, DB version, etc.]
**Preconditions**: [User state, data state, config needed]
**Steps**:
1. [Exact step 1]
2. [Exact step 2]
3. [Exact step 3]
**Expected**: [What should happen]
**Actual**: [What happens instead]
**Frequency**: [Always / Sometimes / Specific conditions]
```

### If You Can't Reproduce

| Situation | Strategy |
|-----------|----------|
| Works on my machine | Compare environments systematically (versions, config, data) |
| Only in production | Check prod-specific config, data volume, timing, load |
| Intermittent | Suspect race conditions, timing, external service flakiness |
| Only for specific users | Check their data, permissions, account state, browser |
| Only after long uptime | Suspect resource leaks (memory, connections, file handles) |

### Write the Failing Test IMMEDIATELY

Before investigating further, write a test that captures the bug:

```
# Template for any language:
def test_bug_TICKET_NUMBER_short_description():
    # Arrange: Set up the conditions that trigger the bug
    input_data = <the input that causes the failure>
    
    # Act: Perform the action that fails
    result = function_under_test(input_data)
    
    # Assert: What SHOULD happen (currently fails)
    assert result == expected_correct_output
```

**This test has two purposes:**
1. Proves you understand the bug (if the test passes, you don't understand it yet)
2. Becomes the regression test (ensures the bug never returns)

---

## Step 3: The Scientific Method for Debugging

> "In debugging, the scientific method allows systematically identifying failure causes by
> gradually refining and refuting hypotheses based on experiments and observations."

### The Process

```
1. OBSERVE    → What exactly is happening? (Be precise)
2. HYPOTHESIZE → What could explain this? (Write it down!)
3. PREDICT    → If my hypothesis is correct, what else should be true?
4. EXPERIMENT → Test the prediction (add assertion, log, breakpoint)
5. CONCLUDE   → Hypothesis confirmed or refuted?
6. ITERATE    → Refine hypothesis and repeat until root cause found
```

### Hypothesis Log Template

**CRITICAL**: Write down your hypotheses. Don't keep them in your head.

```markdown
## Debug Log: [Bug Title]

| # | Hypothesis | Prediction | Experiment | Result | Conclusion |
|---|-----------|-----------|-----------|--------|-----------|
| 1 | "The cache returns stale data" | "Clearing cache fixes it" | Clear cache, retry | Still fails | ❌ Refuted |
| 2 | "Input validation is wrong" | "Invalid input gets through" | Log input at boundary | Input is valid | ❌ Refuted |
| 3 | "Race condition in async handler" | "Adding delay reproduces" | Add artificial delay | Reproduces! | ✅ Confirmed |
```

**Benefits of the log:**
- Never repeat an experiment you already tried
- Can hand off debugging to a colleague with full context
- Can pause debugging and resume later without losing progress
- Forces you to be systematic instead of random

### Good vs Bad Hypotheses

| Good Hypothesis | Bad Hypothesis |
|----------------|---------------|
| "The database query returns NULL for user IDs > 1000" | "The database is broken" |
| "The race condition occurs when request B arrives before A's transaction commits" | "It's a timing issue" |
| "The validation regex doesn't handle Unicode characters" | "The validation is wrong" |

A good hypothesis is **specific** and **testable** — it predicts an observable outcome.

---

## Step 4: Debugging Techniques — Binary Search

### Git Bisect — Find the Introducing Commit

If the bug was recently introduced, use binary search through git history:

```bash
# Start bisect
git bisect start

# Mark the current (broken) state as bad
git bisect bad

# Mark a known-good state (e.g., last week's release)
git bisect good <commit-hash-or-tag>

# Git checks out a middle commit. Test it:
# - If this commit has the bug: git bisect bad
# - If this commit works fine:   git bisect good
# - Repeat until git identifies the introducing commit

# When done:
git bisect reset
```

### Code Bisect — Narrow Within a File

When you know WHICH file but not WHICH line:
1. Comment out half the suspect code
2. Does the bug still occur?
   - Yes → the bug is in the remaining code. Comment out half of THAT.
   - No → the bug is in the code you commented out. Restore it, comment out the other half.
3. Repeat until you've isolated the exact section.

### Assertion-Based Bisect — Narrow the State

Insert assertions at key points to find where the state first becomes wrong:

```
assert correct_state_here      # Point A — passes
...code...
assert correct_state_here      # Point B — passes
...code...
assert correct_state_here      # Point C — FAILS! ← Bug is between B and C
```

---

## Step 5: The 5 Whys — Finding True Root Cause

The presenting symptom is rarely the root cause. Keep asking "Why?" until you reach it:

```
Bug: "User sees a 500 error on the checkout page"
├── Why? → The payment service throws a NullPointerException
├── Why? → The user's address object is null
├── Why? → The address lookup returns null for this user
├── Why? → The address was deleted but the user profile still references it
└── Why? → There's no cascade delete or null check when addresses are removed
         ↑ THIS is the root cause (not the NPE)
```

**Root cause indicators** — you've found it when:
- The explanation is about code/design being WRONG, not just failing
- Fixing it at this level prevents all symptoms, not just one
- It explains WHY the programmer made the mistake, not just what went wrong

---

## Step 6: Root Cause Diagnosis — Prove Before Fixing

### The Two Requirements for a Valid Diagnosis

Before writing a fix, you must have BOTH:

| Requirement | What It Means | Without It |
|-------------|--------------|-----------|
| **Causality** | You can trace exactly how this defect causes the observed failure | Your "fix" may be coincidental — works for this case but not the general problem |
| **Incorrectness** | You can explain WHY the code is wrong (not just that changing it helps) | Your "fix" may address the symptom but leave the actual defect in place |

### Diagnosis Template

```markdown
## Diagnosis

**The defect**: [What specific code is wrong and why]
**How it causes the failure**: [Trace: defect → state corruption → observable failure]
**Why it's incorrect**: [What the code SHOULD do instead, and why the current logic is wrong]
**Proof**: [The assertion/test/experiment that confirms this diagnosis]
```

### Anti-Pattern: Fixing Without Diagnosis

```
❌ "I changed line 42 and now it works" (but you don't know WHY it was wrong)
❌ "I added a null check and the crash stopped" (but WHY was it null?)
❌ "I increased the timeout and it works now" (but WHY was it timing out?)
```

These are symptom fixes. The real bug may still exist and manifest differently later.

---

## Step 7: Common Bug Patterns by Category

### Pattern Recognition — Seen This Before?

| Pattern | Typical Symptom | Root Cause | Fix Strategy |
|---------|----------------|-----------|-------------|
| **Off-by-one** | Works for some inputs, fails at boundaries | `<` vs `<=`, or `length` vs `length - 1` | Test boundary values |
| **Race condition** | Intermittent, non-reproducible | Shared state without synchronization | Add locks or make stateless |
| **Null propagation** | Crash deep in call chain | Nullable return value not checked by caller | Add null check at SOURCE, not crash site |
| **State corruption** | Wrong behavior after specific sequence | Mutation in wrong order or missing reset | Make state immutable or add guards |
| **Resource leak** | Works initially, degrades over time | Open/acquire without close/release | Use finally/with/using, add cleanup |
| **Type coercion** | Wrong results, no error | Implicit type conversion (e.g., "5" + 3) | Explicit types, strict mode |
| **Stale closure** | Uses old value instead of current | Variable captured by reference in closure | Capture by value or use ref |
| **Event order** | Works sometimes, fails on fast interactions | Events arrive in unexpected order | Add state guards or queue |
| **Encoding** | Garbled text, broken special characters | Mixed encodings (UTF-8 vs Latin-1) | Normalize to UTF-8 at boundaries |
| **Floating point** | Comparison fails for "equal" values | 0.1 + 0.2 ≠ 0.3 | Use epsilon comparison or integers |

---

## Step 8: Debugging Anti-Patterns (The Devil's Guide)

These approaches waste time and often make things worse:

### ❌ Printf Debugging Without a Hypothesis

```
# BAD: Adding random logs everywhere
print("here 1")
print("value:", x)
print("here 2")
print("what is this:", obj)
```

**Why it fails**: Generates 1000 lines of output with no idea what you're looking for.
**Instead**: Have a specific hypothesis. Log the ONE value that would prove or disprove it.

### ❌ Debugging Into Existence

Randomly changing code until the test passes. No understanding of why.
**Why it fails**: You may have fixed one case while breaking another. No regression test.
**Instead**: Diagnose first, then make a single deliberate change.

### ❌ The Obvious Fix (Fixing Symptoms)

```python
# Bug: users see error 500
# "Fix": catch the exception and return 200 instead
try:
    process_payment(user)
except Exception:
    return {"status": "ok"}  # ← THE BUG IS STILL THERE
```

**Why it fails**: The bug still exists. Now it's also invisible.
**Instead**: Find WHY the exception occurs and fix the root cause.

### ❌ "It Works on My Machine"

Giving up because you can't reproduce locally.
**Instead**: Systematically compare environments (versions, config, data, timing, load).

---

## Step 9: When You're Stuck (> 30 Minutes Without Progress)

1. **Take a break** — complex bugs are often solved after stepping away
2. **Rubber duck it** — explain the problem out loud (even to yourself)
3. **Change your approach entirely** — if logging doesn't help, try a debugger; if a debugger doesn't help, try writing assertions; if assertions don't help, try simplifying the input
4. **Reduce the problem** — create the SMALLEST possible reproduction case
5. **Ask for a second pair of eyes** — fresh perspective finds what you've been staring past
6. **Sleep on it** — literally. The brain processes problems during sleep.

### Changing Approach — Technique Rotation

| If This Isn't Working... | Try This Instead |
|--------------------------|-----------------|
| Reading the code | Running with a debugger |
| Debugging forward (from input) | Debugging backward (from failure) |
| Staring at the screen | Explaining the problem to someone |
| Adding more logs | Removing code until it works |
| Looking at the failing feature | Looking at a working similar feature |
| Narrowing down | Zooming out to understand the bigger picture |

---

## Debugging Checklist — Summary

- [ ] Bug report understood (expected vs actual, when, who, impact)
- [ ] Bug reproduced reliably (or reproduction conditions documented)
- [ ] Failing test written that captures the bug
- [ ] Hypothesis log started (written, not just mental)
- [ ] Scientific method applied (hypothesis → prediction → experiment)
- [ ] Root cause identified (not just the symptom)
- [ ] Diagnosis proven: CAUSALITY (how defect causes failure) + INCORRECTNESS (why code is wrong)
- [ ] Fix applied (single deliberate change addressing root cause)
- [ ] Failing test now passes
- [ ] No other tests broken
- [ ] Same pattern checked elsewhere in codebase
- [ ] Post-fix verification complete (see fix-verification.md)
