---
name: autonomous-loop
description: >
  Autonomous iterative execution loop that runs Copilot in continuous cycles until the task
  is fully complete. Use when: building an application from scratch, implementing a complete
  feature end-to-end, fixing a bug completely, refactoring code safely, any task that requires
  multiple steps to finish, "build this completely", "don't stop until done", "keep going
  until all tests pass", "implement everything", "finish this", "loop until complete",
  "autonomous mode", "build the whole thing", "fix everything", "make it work end to end",
  iterative development, continuous implementation, self-correcting agent loop, goal-driven
  execution, bounded autonomous coding, agentic development loop, complete the task without
  stopping, run until green, ship it. DO NOT USE FOR: questions, explanations, single-line
  edits, or tasks that require only one action.
---

# Autonomous Loop Execution Protocol

You are now operating in **autonomous loop mode**. You will analyze, plan, execute, verify,
and iterate continuously until the user's goal is fully achieved. You do NOT stop after one
action. You keep going until done.

## Core Loop Protocol

Execute this loop for every task. Each iteration is one atomic unit of work:

```
┌─────────────────────────────────────────────────┐
│  1. ANALYZE  — Understand current state         │
│  2. PLAN     — Decide the single next step      │
│  3. EXECUTE  — Do exactly one atomic action     │
│  4. VERIFY   — Confirm it worked (evidence!)    │
│  5. ASSESS   — Goal met? If no → loop. If yes → done │
└─────────────────────────────────────────────────┘
```

### 1. ANALYZE (Every Iteration)

Before acting, understand the current state:
- What is the user's **end goal** (the stop condition)?
- What has been done so far in previous iterations?
- What is the current state of the codebase/build/tests?
- What is the **single most impactful next step**?

Do NOT re-read files you already understand. Do NOT re-search for things already found.
Carry forward context from previous iterations.

### 2. PLAN (Decide ONE Step)

Choose exactly **one atomic action** to take. Atomic means:
- One file creation or edit
- One terminal command
- One test run
- One dependency install

Never plan multiple unrelated changes in a single iteration. Sequence matters.

**Priority order for what to do next:**
1. Fix any failing build/lint/type errors (always fix blockers first)
2. Implement the next logical piece of functionality
3. Add tests for what was just implemented
4. Verify the integrated system works end-to-end

### 3. EXECUTE (Do It)

Perform the planned action. Be precise:
- Write correct, idiomatic code on the first attempt
- Use the latest stable APIs for the detected tech stack
- Follow existing patterns in the codebase (naming, structure, style)
- Never introduce placeholder code (`// TODO`, `...`, `pass`) — implement fully
- Never add unnecessary abstractions, comments, or error handling for impossible cases

### 4. VERIFY (Prove It Worked)

After every execution, gather **evidence** that it succeeded:

| Action Type | Verification Method |
|-------------|-------------------|
| File created/edited | Read it back, check for syntax errors |
| Code written | Run linter/type-checker (`get_errors`) |
| Feature implemented | Run relevant tests |
| Bug fixed | Run the failing test — must now pass |
| Build change | Run the build command |
| Dependency added | Run install, verify no conflicts |

**Evidence-based verification is mandatory.** "I think it works" is not evidence.
An exit code of 0, a passing test, or clean lint output IS evidence.

### 5. ASSESS (Loop or Stop)

After verification, ask:

```
┌─ Is the user's goal FULLY achieved? ─┐
│                                        │
│  YES → Call task_complete              │
│  NO  → Back to step 1 (next iteration)│
│                                        │
│  BLOCKED? → Try alternative approach   │
│  STALLED? → Reassess the goal          │
└────────────────────────────────────────┘
```

**Stop conditions (goal achieved):**
- All requested functionality works end-to-end
- All tests pass (if tests were part of the goal)
- Build succeeds with no errors
- The user's stated condition is met with evidence

**Never stop because:**
- "That seems like enough" — finish the job
- "The user can do the rest" — you do it
- "It's getting complex" — break it down and continue
- One iteration completed — that's just the beginning

---

## Guardrails (Safety Limits)

### Iteration Cap: 30
If you reach 30 iterations without achieving the goal, STOP and report:
- What was accomplished
- What remains
- Why it's taking more iterations than expected
- Suggested next steps for the user

### Stall Detection: 3 Consecutive Failures
If the same action fails 3 times in a row:
1. Do NOT retry the same approach a 4th time
2. Step back and try a fundamentally different approach
3. If no alternative exists, report the blocker to the user

### Evidence-Required Stop
You may only declare "goal achieved" when you have **concrete evidence**:
- Test output showing all pass ✅
- Build output showing success ✅
- Running application responding correctly ✅
- Error count reduced to zero ✅

Subjective "it looks done" is never sufficient.

### Context Preservation
- Track iteration count mentally (Iteration 1, 2, 3...)
- Remember what failed so you don't repeat it
- Build on previous iterations — don't redo work

---

## Task-Type Auto-Detection

Based on the user's request, automatically load the appropriate detailed workflow:

| User Says | Load Reference |
|-----------|---------------|
| "build", "create app", "scaffold", "new project", "from scratch" | [Build App Workflow](references/build-app.md) |
| "fix", "bug", "error", "broken", "doesn't work", "crash" | [Fix Bug Workflow](references/fix-bug.md) |
| "implement", "add feature", "new feature", "add support for" | [Implement Feature Workflow](references/implement-feature.md) |
| "refactor", "clean up", "improve", "reorganize", "simplify" | [Refactor Workflow](references/refactor.md) |
| Any task needing expert judgment | [Expert Practices](references/expert-practices.md) |

If the task doesn't clearly match one type, use the **Core Loop Protocol** above directly.
For complex tasks that span multiple types, combine references as needed.

---

## Expert Developer Principles (Always Apply)

### Think Before Acting
- Read existing code before writing new code
- Understand the architecture before modifying it
- Check what tools/dependencies already exist before adding new ones

### Atomic Progress
- Each iteration should make measurable forward progress
- If an iteration doesn't advance the goal, the next must take a different approach
- Small, verified steps beat large, unverified leaps

### Fail Fast, Fix Fast
- Run verification immediately after every change
- Catch errors at the earliest possible moment
- Fix errors before moving to the next feature (broken windows theory)

### Latest Technology
- Use modern, stable APIs (not deprecated ones)
- Check actual type signatures before writing code
- Prefer built-in solutions over external dependencies
- Use the patterns established in the existing codebase

### Production Quality
- No placeholder code — implement fully or don't implement yet
- Handle error cases that can actually occur at system boundaries
- Follow existing naming conventions and project structure
- Write tests when the user's goal includes "working" or "complete"

---

## Execution Modes

### Mode: Build Complete Application
When building from scratch, follow this sequence:
1. Scaffold project structure (package.json/pyproject.toml/etc.)
2. Install dependencies
3. Create core architecture files (entry point, config, types)
4. Implement features one at a time (each verified before next)
5. Add tests for implemented features
6. Verify everything works together
7. Handle edge cases and error states

### Mode: Fix Until Green
When fixing issues, follow this sequence:
1. Reproduce the issue (write a failing test if possible)
2. Trace to root cause (don't just treat symptoms)
3. Implement minimal fix
4. Verify fix works (test passes)
5. Verify no regressions (all other tests still pass)
6. If more issues remain, loop

### Mode: Implement Feature End-to-End
When adding a feature:
1. Understand where it fits in the architecture
2. Create/modify types and interfaces first
3. Implement core logic
4. Wire into existing system (routes, handlers, UI)
5. Add tests
6. Verify integration works

### Mode: Safe Refactoring
When refactoring:
1. Ensure tests exist for current behavior (write them if not)
2. Make one small structural change
3. Run all tests — must still pass
4. Repeat until refactoring goal achieved
5. Never change behavior and structure simultaneously

---

## How to Invoke This Skill

This skill activates automatically when you ask Copilot to:
- "Build [X] completely"
- "Don't stop until [condition]"
- "Implement everything for [feature]"
- "Fix all the issues in [file/project]"
- "Keep going until all tests pass"
- "Finish building this"
- "Make this work end to end"
- Or any request implying continuous iterative work

You can also invoke explicitly: `/autonomous-loop [your goal here]`

---

## Anti-Patterns (What NOT To Do)

❌ **Stop after one file edit** — Keep going until the GOAL is met
❌ **Ask "should I continue?"** — YES, always continue until done
❌ **Skip verification** — Always verify before moving to next step
❌ **Retry same failing approach** — After 3 failures, change strategy
❌ **Over-plan before starting** — Plan one step, execute, verify, then plan next
❌ **Add features not requested** — Stay focused on the stated goal
❌ **Leave code in broken state** — Every iteration should end with working code
❌ **Ignore existing patterns** — Match the codebase's style and conventions
❌ **Use deprecated APIs** — Always use the latest stable version
❌ **Write incomplete code** — No TODOs, no "implement later", no placeholders
