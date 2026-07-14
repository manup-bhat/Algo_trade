# Experienced Developer Practices

> "The difference between a junior and senior developer isn't what they know — it's what
> they DON'T do. Seniors avoid problems juniors create." — Common engineering wisdom

This reference contains the cross-cutting practices that experienced software developers
apply regardless of phase, language, or framework. These are the habits that:
- Prevent bugs before they're written
- Speed up debugging when bugs occur
- Produce code that others can maintain
- Avoid wasting time on the wrong approach

---

## Practice 1: Read Before Write

> "Spend 2× the time reading existing code compared to writing new code."

**What seniors do differently**:
- Read the ENTIRE function/module before changing one line
- Understand WHY the code is the way it is (git blame, commit messages)
- Look for patterns already established in the codebase and FOLLOW them
- Check if what they're about to build already exists somewhere

**The cost of not reading first**:
- Duplicate an existing utility (now there are two sources of truth)
- Break an assumption the original author relied on
- Conflict with a pattern used everywhere else in the codebase
- Reinvent a solution that was already tried and reverted (check git history!)

**Practical approach**:
```
Before writing ANY code:
1. Read the file you're about to modify (all of it, not just the function)
2. Read the test file for this module (understand existing test patterns)
3. Search for similar patterns in the codebase (don't reinvent)
4. Check git history for the area (understand how it evolved)
5. THEN start coding
```

---

## Practice 2: Smallest Possible Change

> "The best code change is the smallest one that achieves the goal."

**Why small changes win**:
- Easier to review (reviewers catch more in 100 lines than 1000)
- Easier to revert if something goes wrong
- Easier to understand in git history later
- Less risk of unintended side effects
- Faster to ship (less review time, less test time)

**Research backs this up** (SmartBear study):
- Reviewers catch significantly fewer defects when reviewing > 400 LOC
- Elite teams (LinearB data) average < 225 LOC per PR

**How to shrink a change**:
1. **Separate refactoring from features** — NEVER combine them in one PR
2. **Separate mechanical changes from logical changes** — rename in one PR, new logic in another
3. **Ship in vertical slices** — small end-to-end changes, not layer-by-layer
4. **Use feature flags** — ship incomplete features behind a flag
5. **Ask "what can I remove from this PR?"** — defer anything not strictly necessary

---

## Practice 3: One Logical Change Per Commit

> "Each commit should be atomic: reviewable, revertable, and understandable in isolation."

**What belongs in one commit**:
- A single bug fix + its test
- A single refactoring (rename, extract, move)
- A single feature addition + its test
- A single configuration change

**What does NOT belong in one commit**:
- A bug fix + an unrelated refactoring
- A feature + fixing a style issue in another file
- Multiple unrelated bug fixes
- Code changes + whitespace formatting changes

**Why this matters**:
- `git bisect` works correctly (each commit is a single state change)
- `git revert` removes exactly one logical change
- `git blame` shows WHY each line changed
- Code review can assess each change independently

---

## Practice 4: Write the Test First (for Bugs)

> "TDD for bug fixes: failing test → fix → test passes."

**The sequence**:
1. **Write a test that captures the exact bug** (this test MUST fail)
2. **Verify the test fails** (if it passes, you don't understand the bug)
3. **Make the smallest change that makes it pass**
4. **Verify no other tests break**
5. **The test stays permanently as a regression guard**

**Why this order matters**:
- Forces you to UNDERSTAND the bug before fixing it
- Proves your fix actually addresses the bug (not something else)
- Creates a regression test automatically
- Prevents "I thought I fixed it but actually just masked it"

---

## Practice 5: Binary Search for Root Cause

> "Don't linearly scan through code looking for bugs. Divide and conquer."

**Techniques**:

| Technique | When to Use | How |
|-----------|------------|-----|
| **git bisect** | Bug recently introduced | Binary search through commits |
| **Comment-out bisect** | Know the file, not the line | Remove half the code, check if bug persists |
| **Assert bisect** | Know the flow, not where state corrupts | Add assertions at midpoints in the data flow |
| **Input bisect** | Bug depends on input data | Halve the input until you find minimum reproducing case |
| **Layer bisect** | Don't know which layer is wrong | Test each layer in isolation (API? Service? DB?) |

**The key insight**: Binary search finds the answer in O(log n) steps.
Linear scanning takes O(n) steps. For a 1000-line file:
- Linear: up to 1000 checks
- Binary: maximum 10 checks

---

## Practice 6: Time-Box Debugging

> "Stuck for more than 30 minutes? Change your approach entirely."

**The 30-minute rule**:
- Set a timer when you start investigating
- If you haven't made progress in 30 minutes, STOP
- Do something fundamentally different:

| Instead of... | Try... |
|---------------|--------|
| Staring at code | Explaining the problem to someone (rubber duck) |
| Adding more logs | Using a debugger with breakpoints |
| Looking at the failing code | Looking at WORKING similar code |
| Debugging forward (from cause) | Debugging backward (from failure) |
| Narrowing focus | Zooming out to the bigger picture |
| Working alone | Asking a colleague for a fresh pair of eyes |
| Continuing to work | Taking a 15-minute walk (seriously) |

**Why breaks work**: Your brain continues processing the problem subconsciously.
Many experienced developers report solving their hardest bugs after sleeping on them,
taking a shower, or going for a walk.

---

## Practice 7: Rubber Duck Debugging

> "Explain the problem out loud. You'll often find the answer mid-sentence."

**How it works**:
1. Get a rubber duck (or any object/person)
2. Explain the problem from the BEGINNING, step by step
3. Describe what you EXPECT to happen vs what ACTUALLY happens
4. Explain WHY you think the code should work
5. Often, while explaining step 3 or 4, you'll realize your assumption is wrong

**Why it works**:
- Forces you to slow down and think linearly
- Makes implicit assumptions explicit
- Often reveals the gap between what you THINK the code does and what it ACTUALLY does
- Different cognitive mode (explaining vs. scanning)

**Variation**: Write a detailed bug report as if explaining to a colleague. The act of writing often reveals the answer.

---

## Practice 8: Future-Proof the Fix

> "Fix the CLASS of bugs, not just the INSTANCE."

**After fixing any bug, ask**:
1. "Is this a one-off mistake, or could this happen elsewhere?"
2. "Can I add a lint rule / type check / assertion that prevents this class of bug?"
3. "Should I add documentation explaining WHY this code is the way it is?"
4. "Is there a design change that makes this bug IMPOSSIBLE instead of just unlikely?"

**Examples of class-level fixes**:

| Instance Fix | Class Fix |
|-------------|-----------|
| Add null check for this variable | Use non-nullable types for this entire domain |
| Add validation for this endpoint | Add validation middleware for ALL endpoints |
| Fix race condition in this handler | Redesign to eliminate shared mutable state |
| Add missing await here | Add lint rule: no floating promises in codebase |
| Escape user input here | Use parameterized queries everywhere (remove the option to forget) |

---

## Practice 9: Boy Scout Rule

> "Always leave the code cleaner than you found it."

**One small improvement per touch**:
- Rename one confusing variable
- Add one missing type annotation
- Remove one dead code block
- Extract one duplicated expression
- Fix one misleading comment

**What NOT to do**:
- Don't refactor the whole file when you're fixing a bug (separate PR)
- Don't fix style issues in files you're not otherwise changing
- Don't add unrelated improvements to a feature PR (clutters the diff)

**The compound effect**: If every developer improves one small thing per touch,
the codebase improves continuously without dedicated refactoring sprints.

---

## Practice 10: Measure Twice, Cut Once

> "Validate your approach BEFORE implementing. Ask: is there a simpler way?"

**Before writing any non-trivial code, verify**:
1. "Am I solving the right problem?" (Re-read the requirement)
2. "Is there an existing solution in the codebase?" (Search first)
3. "Is there a library that does this?" (Don't reinvent)
4. "What's the simplest approach that works?" (KISS)
5. "Will I need to throw this away when requirements change?" (YAGNI check)
6. "Can a colleague understand this in 30 seconds?" (Cognitive complexity)

**Signs you should stop and reconsider**:
- The solution is getting more complex than the problem
- You're fighting the framework instead of working with it
- You need to add more than 3 new files for what should be simple
- You can't explain your approach in one sentence
- You've been working on it for hours without committing anything

---

## Practice 11: Ship/Show/Ask Decision Framework

> "Not every change needs the same level of review."

**From Martin Fowler's Ship/Show/Ask**:

| Decision | When | Action |
|----------|------|--------|
| **Ship** | Established pattern, low risk, you've done this before | Merge directly to main |
| **Show** | New pattern, want feedback, educational for team | Open PR, merge immediately, get async feedback |
| **Ask** | Uncertain, high risk, cross-team impact | Open PR, wait for review before merging |

**Decision criteria**:

| Factor | → Ship | → Ask |
|--------|--------|-------|
| Risk of change | Low (config, docs, known pattern) | High (auth, payments, data schema) |
| Your confidence | "I've done this 100 times" | "I'm not sure this is right" |
| Blast radius | One file, one feature | Many files, many consumers |
| Reversibility | Easy to revert, no side effects | Hard to undo (migrations, emails sent) |
| Team norm | Team ships fast, trusts members | New team, building trust |

---

## Practice 12: Cognitive Load Management

> "If you can't hold the entire context in your head, the code is too complex."

**Signs of excessive cognitive load**:
- You need to scroll back and forth to understand a function
- You need to hold more than 3 things in working memory simultaneously
- You need to read code from 5+ files to understand one operation
- Variable names require mental translation ("what does `tmp2` mean here?")

**Remedies**:
- Extract method: name sub-operations so you can think at a higher level
- Replace comment with well-named function
- Flatten nesting: early returns instead of nested if-else
- Inline unnecessary abstractions: if a function has one caller, consider inlining
- Reduce parameter count: 4+ parameters → use a params object

**The 30-Second Rule**: Can a developer new to this code understand what a function does
within 30 seconds of reading it? If not, it's too complex.

---

## Quick Reference Card

| # | Practice | One-Line Rule |
|---|----------|---------------|
| 1 | Read Before Write | Spend 2× time reading vs writing |
| 2 | Smallest Change | Best PR is the smallest correct one |
| 3 | Atomic Commits | One logical change per commit |
| 4 | Test First (Bugs) | Failing test → fix → passes |
| 5 | Binary Search | Divide and conquer, not linear scan |
| 6 | Time-Box | 30 min stuck → change approach |
| 7 | Rubber Duck | Explain the problem out loud |
| 8 | Future-Proof | Fix the class, not just the instance |
| 9 | Boy Scout | One small improvement per touch |
| 10 | Measure Twice | Validate approach before implementing |
| 11 | Ship/Show/Ask | Match review level to risk level |
| 12 | Cognitive Load | If it takes > 30 sec to understand, simplify |
