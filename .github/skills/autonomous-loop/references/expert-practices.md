# Expert Developer Practices — Autonomous Loop Reference

Advanced patterns and techniques that experienced developers use. Load this reference
when the task requires professional-grade engineering judgment.

---

## Scientific Debugging

When something isn't working and the cause isn't obvious:

### The Method
1. **Observe** — Collect facts (error messages, logs, behavior)
2. **Hypothesize** — Form a testable theory about the cause
3. **Predict** — If hypothesis X is true, then Y should happen when I do Z
4. **Experiment** — Do Z and observe
5. **Conclude** — Was prediction correct? If yes, root cause found. If no, new hypothesis.

### Hypothesis Log

Track your debugging session:
```
Hypothesis 1: The API returns 500 because the database connection is stale
  Test: Run a simple query directly → succeeds
  Result: DISPROVEN — DB connection is fine

Hypothesis 2: The API returns 500 because input validation throws on empty arrays
  Test: Send request with empty items array → 500! Send with non-empty → 200
  Result: CONFIRMED — Empty array hits a code path that throws

Fix: Add guard for empty array input
```

### Binary Search Debugging

When the bug is somewhere in a large code path:
1. Find the midpoint of execution
2. Log the state at that point
3. Is the state correct or already wrong?
4. If correct → bug is in the second half
5. If wrong → bug is in the first half
6. Repeat until narrowed to exact cause

---

## Test-Driven Development (TDD)

### Red-Green-Refactor Cycle

```
┌─── RED: Write a failing test ─────────┐
│                                        │
│    ┌─── GREEN: Minimal code to pass ─┐ │
│    │                                  │ │
│    │    ┌─── REFACTOR: Clean up ────┐ │ │
│    │    │    (tests still pass)      │ │ │
│    │    └────────────────────────────┘ │ │
│    └────────────────────────────────────┘ │
└────────────────────────────────────────────┘
```

### When to Use TDD in the Loop

- **Always** for bug fixes (failing test first)
- **Usually** for new features (write test for desired behavior)
- **Sometimes** for exploratory code (spike first, test after)
- **Never skip** if the user said "with tests" or "complete"

### Writing Good Tests

```
Good test:
- Tests ONE behavior
- Has a clear name describing what's tested
- Follows Arrange → Act → Assert
- Can fail for only one reason
- Doesn't depend on other tests
- Runs fast (<100ms)

Bad test:
- Tests multiple things
- Named "test1", "testFunction"
- Has complex setup unrelated to what's tested
- Depends on execution order
- Hits the network or file system unnecessarily
```

---

## Architecture Decision Making

### When Adding to an Existing Codebase

**Rule: Follow the existing patterns.** Even if you prefer a different approach,
consistency is more valuable than individual preference.

### When Building from Scratch

**Decision framework:**
| Question | If YES | If NO |
|----------|--------|-------|
| Will this have >5 users? | Add auth, input validation | Skip auth for now |
| Will data persist across restarts? | Use a database | Use in-memory |
| Is the domain complex? | Separate business logic from I/O | Simple procedural is fine |
| Will multiple devs work on this? | Add types, tests, docs | Lighter approach OK |
| Is this a prototype? | Optimize for speed of implementation | Optimize for maintainability |

### SOLID Principles (Applied Pragmatically)

- **S** (Single Responsibility): Each function/class does ONE thing well
- **O** (Open/Closed): Extend through composition, not modification
- **L** (Liskov): Subtypes must be usable wherever parents are used
- **I** (Interface Segregation): Don't force implementation of unused methods
- **D** (Dependency Inversion): Depend on abstractions at boundaries

**Don't over-apply.** SOLID is a guide, not a religion. A 20-line script
doesn't need dependency injection.

---

## Error Handling Patterns

### Where to Handle Errors

| Layer | Error Handling Responsibility |
|-------|------------------------------|
| System boundary (API route, CLI command) | Catch all, return proper error format |
| Business logic | Throw/raise domain errors with context |
| Data layer | Throw/raise on constraint violations, connection issues |
| Utility functions | Don't catch — let errors propagate |

### Error Handling Rules

1. **Handle errors at the layer that can DO something about them**
2. **Never silently swallow errors** (`catch {}` with no action)
3. **Add context when re-throwing** (`throw new Error("Creating user failed: " + e.message)`)
4. **Use typed errors** for different failure modes
5. **Return errors as values** when the caller needs to decide (Result types)

### What NOT to Handle

Don't add error handling for:
- Programmer errors (wrong types, missing arguments) — these should crash loudly
- Impossible states (if TypeScript guarantees it can't be null, don't check for null)
- Hypothetical failures (if the config file always exists, don't handle FileNotFound)

---

## Performance Awareness

### When to Optimize (Almost Never in the Loop)

**Rule:** Make it work, make it right, THEN make it fast.

Only optimize when:
- There's a measured performance problem
- The user specifically asked for performance
- The naive approach would be O(n²) or worse on expected data sizes

### Common Performance Pitfalls

| Pattern | Problem | Fix |
|---------|---------|-----|
| N+1 queries | 100 items = 101 DB calls | Join/include in one query |
| Unbounded arrays | Loading 1M records into memory | Pagination/streaming |
| Sync in async | Blocking event loop | Use async I/O |
| Re-computing | Same calculation in every render/request | Memoize/cache |
| String concatenation in loop | O(n²) string building | Use StringBuilder/join |

---

## Code Review Mindset

### Before Declaring Anything "Done"

Read your own code as if reviewing a colleague's PR:

1. **Does this make sense to someone seeing it for the first time?**
2. **Are the names clear?** (Would I understand `processData` in 6 months?)
3. **Is there unnecessary complexity?** (Can any of this be simpler?)
4. **Are there missing error cases?** (What if X is null/empty/huge?)
5. **Does it follow the project's patterns?** (Would this look foreign in the codebase?)

### The "Newspaper Test"

If your code appeared in a technical article, would readers:
- Understand what it does from the names alone?
- See a clear flow from input to output?
- Notice no dead code, no commented-out blocks, no TODOs?

---

## Working with Existing Codebases

### Before Modifying

1. **Read first**: Understand the file before editing it
2. **Find the pattern**: How are similar things done nearby?
3. **Check imports**: What utilities/helpers already exist?
4. **Check tests**: How is this area tested? Follow the same approach
5. **Check git blame**: Who wrote this? When? Why? (Comments/commit messages)

### Modifying Safely

1. **Understand the blast radius**: What else uses this code?
2. **Make changes as small as possible**: One concern per edit
3. **Verify after each change**: Don't stack 5 changes then test once
4. **Match the style**: Even if you'd prefer different style, be consistent

---

## Async/Concurrent Programming

### Rules for Async Code

1. **Never mix sync and async** — if one function is async, callers must await
2. **Handle rejection/errors** — every Promise/async call needs error handling
3. **Avoid shared mutable state** — race conditions are silent killers
4. **Limit concurrency** — don't fire 1000 requests simultaneously
5. **Cancel when appropriate** — unmounted components, abandoned requests

### Common Async Bugs

| Bug | Cause | Fix |
|-----|-------|-----|
| Stale data | Using value from before await | Re-read after await |
| Race condition | Two operations read-modify-write | Mutex/lock/queue |
| Unhandled rejection | Missing .catch or try/catch | Always handle async errors |
| Memory leak | Event listener not cleaned up | Cleanup in unmount/dispose |
| Deadlock | Awaiting something that awaits you | Break the cycle |

---

## Security Awareness (Always Apply)

### OWASP Top Risks to Check

Every time you write code that:
- Accepts user input → **validate and sanitize**
- Queries a database → **use parameterized queries** (never string concat)
- Returns data → **don't leak internal details** (stack traces, DB schema)
- Checks permissions → **deny by default**, whitelist allowed actions
- Stores secrets → **environment variables**, never in code
- Renders HTML → **escape output** to prevent XSS
- Handles files → **validate paths** to prevent path traversal

### Security Defaults

```
✅ ALWAYS DO:
- Validate input at system boundaries
- Use parameterized queries
- Hash passwords (bcrypt/argon2, never MD5/SHA)
- Use HTTPS for all external calls
- Set security headers (CORS, CSP, HSTS)
- Use environment variables for secrets

❌ NEVER DO:
- Log passwords or tokens
- Trust client-side validation alone
- Use eval() or exec() with user input
- Hardcode API keys or passwords
- Expose stack traces in production responses
- Skip authentication on sensitive endpoints
```

---

## When to Ask vs When to Act

### Just Act (Don't Ask)
- The task is clear and you know how to do it
- You're fixing an obvious bug
- You're implementing something the user explicitly requested
- The next step is unambiguous

### Pause and Report (Rare)
- The task requires a destructive action (deleting data, force push)
- You've hit the 30-iteration cap
- You've stalled 3 times on the same issue
- The requirements are genuinely ambiguous (two valid interpretations)
- Security concern (the user asked for something unsafe)

---

## Iteration Efficiency

### Minimize Wasted Iterations

- Don't read files you've already read (carry forward context)
- Don't search for things you've already found
- Don't verify things that can't have broken (unchanged code)
- Batch related micro-changes into one iteration when safe
- Use type-checker output to find ALL errors at once, fix them in one edit

### Maximize Progress Per Iteration

- Each iteration should produce a measurable artifact (file, passing test, working feature)
- If an iteration would only produce "understanding", combine it with the first action
- If an iteration would only produce "planning", skip to the first implementation action

### Know When to Parallelize

These can happen in the same iteration:
- Create file + write initial content
- Fix error + verify fix
- Install dep + create config file

These must be separate iterations:
- Write code → then verify it compiles
- Change behavior → then update tests
- Modify shared code → then check all consumers
