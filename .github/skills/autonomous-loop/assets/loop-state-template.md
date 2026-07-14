# Loop State Tracking Template

Use this mental model to track progress through the autonomous loop.
Do NOT create this as a file in the workspace — it exists only in conversation context.

---

## Current Loop State

```
GOAL: [User's stated end condition]
STATUS: [active | achieved | blocked | aborted]
ITERATION: [N / 30]
TASK TYPE: [build-app | fix-bug | implement-feature | refactor | mixed]

PROGRESS:
  - [x] Step completed (Iteration 1)
  - [x] Step completed (Iteration 2)
  - [ ] Current step (Iteration 3) ← IN PROGRESS
  - [ ] Next planned step
  - [ ] ...remaining steps

LAST ACTION: [What was just done]
LAST RESULT: [pass ✅ | fail ❌ | partial ⚠️]
NEXT ACTION: [What to do next]

BLOCKERS: [None | Description of what's blocking]
STALL COUNT: [0-3, reset on any progress]
```

---

## State Transitions

```
START → active (Iteration 1)
  ↓
active → active (each successful iteration)
  ↓
active → achieved (goal met with evidence)
  ↓ OR
active → blocked (3 consecutive stalls, report to user)
  ↓ OR
active → aborted (30 iterations reached, report to user)
```

---

## Evidence Log (Mental)

Track what constitutes "evidence" for this specific goal:

| Goal Type | Evidence Required |
|-----------|------------------|
| "Build X" | App starts, responds correctly, tests pass |
| "Fix bug Y" | Failing test now passes, no regressions |
| "Add feature Z" | Feature works e2e, tests pass, integrated |
| "Refactor W" | All tests still pass, code is cleaner |
| "All tests pass" | `test` command exits 0, all green |
| "Make it work" | App runs without errors, does what user described |
| "Deploy" | Build succeeds, deployable artifact created |

---

## Decision Points

At each iteration, ask:

1. Am I making progress? (Compare to last iteration)
   - YES → Continue with next step
   - NO → Change approach (don't repeat same action)

2. Is this the right approach?
   - YES → Continue current strategy
   - NO → Pivot (re-analyze, choose different path)

3. Am I scope-creeping?
   - NO → Good, stay focused on stated goal
   - YES → Stop. Go back to the user's original request.

4. Am I optimizing prematurely?
   - NO → Good, keep building
   - YES → Stop. Make it work first, optimize only if asked.

---

## When to Load Which Reference

```
IF user says "build" or "create" or "new project" or "from scratch":
  → Load references/build-app.md

IF user says "fix" or "bug" or "error" or "broken" or "crash":
  → Load references/fix-bug.md

IF user says "add" or "implement" or "feature" or "support":
  → Load references/implement-feature.md

IF user says "refactor" or "clean" or "reorganize" or "simplify":
  → Load references/refactor.md

IF task requires advanced judgment or debugging:
  → Load references/expert-practices.md

IF ambiguous:
  → Use Core Loop Protocol from SKILL.md directly
```
