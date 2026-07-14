# Advanced Bug Detection — Deep Scan for Hidden Defects

> "The best bug is the one you never ship. The second best is the one you find before
> your users do." — Every experienced developer

This reference covers systematic detection of bugs that typical code reviews and
per-feature audits miss. These are the bugs that cause production incidents, data
corruption, and intermittent failures that are notoriously hard to reproduce.

---

## Bug Detection Philosophy

**Why per-feature audits miss these bugs**:
- Race conditions only manifest under specific timing
- Resource leaks accumulate slowly until system failure
- Null propagation paths cross feature boundaries
- Copy-paste bugs look correct at first glance
- State machine violations require understanding the full lifecycle

**The experienced developer's approach**:
1. Assume every piece of code has bugs until proven otherwise
2. Focus on boundaries (where data crosses modules, services, layers)
3. Think about what happens when things go wrong, not just when they go right
4. Look for patterns of bugs, not individual bugs — a pattern indicates systemic issues
5. Use the "what if" technique: what if this is null? what if this fails? what if two threads hit this simultaneously?

---

## Category 1: Race Conditions & Concurrency Bugs

### What to Look For

Race conditions occur when the correctness of code depends on the relative timing of
multiple operations. They are the #1 cause of intermittent production failures.

**Patterns that indicate race condition risk**:

```bash
# Find shared mutable state (JavaScript/TypeScript)
grep -rn "let \|var " ./src | grep -v "const\|test\|spec" | head -30

# Find global/module-level mutable variables (Python)
grep -rn "^[a-zA-Z_].*= " ./src --include="*.py" | grep -v "def \|class \|import\|#\|test"

# Find concurrent access patterns (any language)
grep -rn "async\|await\|Promise\|Thread\|Lock\|Mutex\|concurrent\|parallel\|goroutine\|spawn" ./src | head -40

# Find check-then-act patterns (classic race condition)
grep -rn "if.*exists\|if.*find\|if.*get" ./src | grep -v "test\|spec" | head -20
```

**Red flags — High probability of race condition**:

| Pattern | Risk | Example |
|---------|------|---------|
| Check-then-act without lock | Critical | `if (!exists(key)) { create(key) }` |
| Read-modify-write without atomicity | Critical | `counter = getCounter(); counter++; setCounter(counter)` |
| Shared mutable state across async operations | High | Module-level `let cache = {}` accessed by multiple requests |
| Multiple awaits on shared resource | High | Two `await db.update()` calls on same record |
| Event handlers modifying shared state | High | WebSocket handlers updating global state |
| Lazy initialization without synchronization | Medium | `if (!instance) { instance = new Thing() }` |

**Detection approach**:
1. Identify all shared mutable state (module-level variables, class properties, database records)
2. Find all code paths that read AND write to that state
3. Determine if multiple concurrent executions could interleave those operations
4. Check if synchronization mechanisms (locks, transactions, atomic operations) are in place

### Specific Patterns

**Double-checked locking (broken in many languages)**:
```
# Pattern: check → do something → check again → assume still true
# Bug: state can change between first check and action
```

**Lost update**:
```
# Thread A reads balance: $100
# Thread B reads balance: $100
# Thread A writes balance: $100 + $50 = $150
# Thread B writes balance: $100 + $30 = $130  ← Thread A's update is lost
```

**Deadlock detection**:
```bash
# Find nested lock acquisitions (potential deadlock)
grep -rn "lock\|acquire\|synchronized" ./src | grep -v "test" | head -30

# Find multiple await in sequence on related resources
grep -rn "await.*await" ./src --include="*.ts" --include="*.js"
```

---

## Category 2: Resource Leaks

### What to Look For

Resource leaks happen when resources (connections, file handles, memory, sockets, event listeners)
are acquired but never released. They cause slow degradation until system failure.

**Detection patterns**:

```bash
# Find resource acquisition without corresponding release
# Database connections
grep -rn "createConnection\|getConnection\|connect(\|pool\.acquire" ./src | grep -v "close\|release\|end\|dispose\|test"

# File handles
grep -rn "open(\|createReadStream\|createWriteStream\|fs\.\(open\|read\|write\)" ./src | grep -v "close\|test"

# Event listeners (memory leak in long-running processes)
grep -rn "addEventListener\|\.on(\|addListener\|subscribe" ./src | grep -v "removeEventListener\|\.off(\|removeListener\|unsubscribe\|test"

# Timers (setInterval without clearInterval)
grep -rn "setInterval\|setTimeout" ./src | grep -v "clearInterval\|clearTimeout\|test"

# Python context managers NOT used (should use `with`)
grep -rn "\.open(\|\.connect(" ./src --include="*.py" | grep -v "with \|test"
```

**Red flags**:

| Pattern | Risk | Fix |
|---------|------|-----|
| DB connection in try without finally/close | High | Use connection pooling or `finally { conn.close() }` |
| Event listener added in loop without removal | High | Store reference, remove in cleanup |
| setInterval without clearInterval reference | Medium | Store interval ID, clear on cleanup |
| File opened without explicit close | Medium | Use `with` (Python), `using` (C#), try-with-resources (Java) |
| Subscriptions without unsubscribe | High | Clean up in component unmount/destroy |

**Validation approach**:
1. For every `open`/`acquire`/`create`/`subscribe`, find the matching `close`/`release`/`destroy`/`unsubscribe`
2. Verify the cleanup happens in ALL code paths (including error paths)
3. Check that cleanup happens in `finally` blocks, not just happy-path code
4. Look for cleanup in lifecycle hooks (componentWillUnmount, __del__, Dispose, defer)

---

## Category 3: Null/Undefined Propagation

### What to Look For

Null reference exceptions are the #1 runtime error in most languages. The bug isn't where
the null crashes — it's where the null was *introduced*.

**Detection patterns**:

```bash
# Find optional chaining patterns (indicating nullable values in the chain)
grep -rn "\?\.\|??\|\.?" ./src --include="*.ts" --include="*.js" | head -30

# Find potential null returns
grep -rn "return null\|return None\|return nil\|return undefined" ./src | grep -v "test"

# Find unchecked function calls that can return null
grep -rn "\.find(\|\.get(\|\.querySelector(\|getElementById" ./src | grep -v "if\|?\.\|!= null\|!== null\|test"

# Find destructuring without defaults (null object will crash)
grep -rn "const {.*} =" ./src --include="*.ts" --include="*.js" | grep -v "= {}\||| {}\|?? {}\|test"
```

**Red flags**:

| Pattern | Risk | Example |
|---------|------|---------|
| `.find()` result used without null check | High | `users.find(u => u.id === id).name` crashes if not found |
| API response accessed without validation | High | `response.data.user.email` — any level could be null |
| Destructuring potentially null value | Medium | `const { name } = getUser()` where getUser can return null |
| Optional parameter used as required downstream | High | `function process(data?) { data.items.forEach(...) }` |
| Database query result assumed non-null | High | `const user = await User.findById(id); user.update(...)` |

**Tracing approach**:
1. Find all functions that return nullable values (null/undefined/None/nil)
2. Trace each caller — does it check for null before using the result?
3. Look for long call chains where null from an early function propagates to a later crash
4. Check API response handling — external data is ALWAYS potentially null/malformed

---

## Category 4: Error Swallowing

### What to Look For

Error swallowing is when exceptions are caught but not properly handled — the error
disappears and the program continues in an invalid state. This causes mysterious
downstream failures that are nearly impossible to debug.

**Detection patterns**:

```bash
# Empty catch blocks (JavaScript/TypeScript)
grep -rn "catch.*{" ./src --include="*.ts" --include="*.js" -A 1 | grep -B 1 "^.*}$" | head -30

# Catch blocks with only console.log (swallowing in production)
grep -rn "catch" ./src -A 3 | grep "console\.\(log\|warn\)" | head -20

# Python bare except (catches everything including SystemExit)
grep -rn "except:" ./src --include="*.py" | grep -v "except.*Error\|except.*Exception"

# Catch-all without re-throw
grep -rn "catch\s*(.*)\s*{" ./src --include="*.ts" -A 5 | grep -v "throw\|reject\|next(\|res\.status" | head -30
```

**Severity levels of error swallowing**:

| Pattern | Severity | Why |
|---------|----------|-----|
| Empty catch block `catch (e) {}` | High | Error completely disappears; system in unknown state |
| Catch with only `console.log(e)` | Medium | Error logged but not propagated; caller doesn't know something failed |
| Generic catch masking specific errors | Medium | `catch(e)` hides type errors, network errors, auth errors equally |
| `try/catch` around entire function body | Low/Medium | Over-broad — hides which specific operation failed |
| Swallowed Promise rejection | High | `promise.catch(() => {})` — fire-and-forget hides failures |
| Python `except: pass` | Critical | Catches SystemExit, KeyboardInterrupt — unstoppable |

**What correct error handling looks like**:
- Specific error types caught (not catch-all)
- Error logged with context (what was being attempted, with what inputs)
- Error propagated or transformed into appropriate response for the caller
- System state is consistent after error (resources cleaned up, transactions rolled back)

---

## Category 5: Copy-Paste Bugs

### What to Look For

Copy-paste bugs occur when code is duplicated and then partially modified. The developer
changes most of the copy but misses one reference to the original context.

**Detection patterns**:

```bash
# Find similar function names that might be copies
grep -rn "function\|def \|func " ./src | \
  awk -F'[( ]' '{print $NF}' | sort | uniq -d | head -20

# Find blocks that are nearly identical (look for consecutive similar lines)
# Use jscpd with low thresholds to catch near-duplicates
npx jscpd ./src --min-lines 5 --min-tokens 40 --reporters consoleFull 2>/dev/null

# Find variable names from one context used in another
# (e.g., `userId` in a function that processes orders)
grep -rn "user.*order\|order.*user" ./src | head -20
```

**Common copy-paste bug patterns**:

| Pattern | Example | Bug |
|---------|---------|-----|
| Wrong variable in copy | `if (user.name === user.name)` | Should be `user.name === other.name` |
| Stale string literal | `log("Processing user")` in order handler | Copied from user handler, string not updated |
| Wrong index/offset | `array[0]` in a loop that should use `array[i]` | Copied first iteration, forgot to parameterize |
| Wrong error message | `throw new Error("User not found")` in product service | Copied from user service |
| Wrong return type | Function returns user object but was copied from address lookup | Returns wrong entity |
| Incomplete rename | 3 of 4 variables renamed, one still refers to original | `userResult` in `getOrderById()` |

**How to detect**:
1. Find code blocks that are 80–95% identical (jscpd with low thresholds)
2. Manually inspect the 5–20% differences — are they intentional modifications or missed updates?
3. Check function names vs variable names inside — do they match the current context?
4. Look for error messages that don't match the function they're in

---

## Category 6: State Machine Violations

### What to Look For

Many features have implicit state machines (user registration flow, order lifecycle, 
payment processing). Bugs occur when code transitions to an invalid state or skips required states.

**Detection approach**:

```bash
# Find status/state fields and their possible values
grep -rn "status\|state\|phase\|stage" ./src | grep "=\|enum\|type\|const" | grep -v "test" | head -30

# Find state transitions
grep -rn "\.status\s*=\|\.state\s*=\|setState\|setStatus\|update.*status" ./src | grep -v "test" | head -30

# Find conditional logic based on state (where violations manifest)
grep -rn "if.*status\|if.*state\|switch.*status\|switch.*state" ./src | grep -v "test" | head -30
```

**State machine audit process**:

1. **Map all states**: Enumerate every possible state value for each entity
2. **Map valid transitions**: Which state can transition to which other state?
3. **Find all transition code**: Every place the state is changed
4. **Verify guards**: Does each transition check that the current state is valid for that transition?
5. **Check for impossible states**: Can the system reach a state that no code handles?

**Common state machine bugs**:

| Bug | Example | Impact |
|-----|---------|--------|
| Missing transition guard | Order goes from "shipped" directly to "draft" | Data integrity violation |
| Skipped required state | Payment processed without verification state | Compliance violation |
| Orphaned state | Entity stuck in "processing" forever (no timeout) | Resource leak, stuck UX |
| Parallel state mutation | Two requests change order state simultaneously | Race condition + invalid state |
| State checked at wrong layer | UI checks state but API doesn't validate | Security bypass |

---

## Category 7: Temporal Coupling

### What to Look For

Temporal coupling means code that must execute in a specific order but doesn't enforce that order.
Bugs manifest as "it works on my machine" or "it works most of the time."

**Red flags**:

```bash
# Find initialization patterns that might have ordering dependencies
grep -rn "init\|setup\|configure\|bootstrap\|register" ./src | grep -v "test" | head -30

# Find sequences where order matters
grep -rn "await.*\nawait\|\.then.*\.then" ./src --include="*.ts" --include="*.js" | head -20
```

**Common temporal coupling bugs**:

| Pattern | Bug | Fix |
|---------|-----|-----|
| Service A must start before Service B | If B starts first, it crashes or silently fails | Explicit dependency declaration |
| Cache must be warmed before first request | First requests after deploy are slow or fail | Health check includes cache readiness |
| Config must be loaded before use | NPE if used before config loads | Lazy loading or explicit initialization order |
| DB migration must run before app starts | App crashes on unmigrated schema | Migration check in startup sequence |
| Event handlers must register before events fire | Early events silently dropped | Buffer events until handlers registered |

---

## Category 8: Integer Overflow and Boundary Errors

### What to Look For

**Detection patterns**:

```bash
# Find arithmetic on potentially large numbers
grep -rn "price\|amount\|quantity\|total\|count\|size\|length\|offset\|index" ./src | \
  grep "\+\|\-\|\*\|/" | grep -v "test\|spec" | head -30

# Find array/string access without bounds checking
grep -rn "\[.*\]" ./src | grep -v "const\|let\|var\|type\|interface\|test" | head -20

# Find parseInt without radix (JavaScript specific bug source)
grep -rn "parseInt(" ./src --include="*.ts" --include="*.js" | grep -v ", 10\|, 16\|test"
```

**Common boundary bugs**:

| Bug | Language | Example |
|-----|---------|---------|
| Integer overflow in price calculation | JS | `price * quantity` exceeds Number.MAX_SAFE_INTEGER |
| Off-by-one in loop bounds | All | `for (i = 0; i <= array.length)` — reads past end |
| Negative index | Python | `array[-1]` is valid Python but might be unintentional |
| Division by zero | All | `total / count` where count can be 0 |
| Floating point comparison | All | `0.1 + 0.2 === 0.3` is false |
| String-to-number coercion | JS | `"5" + 3 = "53"` (string concatenation, not addition) |

---

## Category 9: Logic Inversions

### What to Look For

Logic inversions are bugs where a boolean condition is accidentally negated or a comparison
operator is wrong. They often pass tests because the test was written with the same wrong assumption.

**Detection patterns**:

```bash
# Find double negations (confusing and error-prone)
grep -rn "!!\|not not\|!=.*!\|!.*!=" ./src | grep -v "test" | head -20

# Find comparisons that might be inverted
grep -rn "if (!.*)\|unless\|!==\|!= " ./src | grep -v "test" | head -30

# Find early returns with negated conditions (common inversion site)
grep -rn "if (!.*) return\|if (!.*) throw\|if (!.*) continue" ./src | grep -v "test" | head -20
```

**Common logic inversion patterns**:

| Pattern | Bug | Should Be |
|---------|-----|-----------|
| `if (!isValid) { proceed() }` | Proceeds when invalid | `if (isValid) { proceed() }` |
| `if (user.role !== 'admin')` in admin-only check | Allows non-admins | `if (user.role === 'admin')` |
| `array.filter(x => !x.active)` for active items | Returns inactive | `array.filter(x => x.active)` |
| `>` instead of `>=` in age verification | Off-by-one on boundary | Check requirement for boundary |
| `&&` instead of `\|\|` in permission check | Requires ALL permissions | Should require ANY |

---

## Category 10: API Contract Violations

### What to Look For

API contract violations are mismatches between what an API promises (documentation, types, schema)
and what it actually does in edge cases.

**Detection approach**:

```bash
# Find response types that don't match declared types
# Look for responses that bypass the type system
grep -rn "as any\|// @ts-ignore\|type: ignore\|# type: ignore" ./src | grep -v "test" | head -20

# Find endpoints that can return different shapes
grep -rn "res\.\(json\|send\|status\)" ./src | grep -v "test" | head -30

# Find functions whose return type includes undefined/null but callers don't handle it
grep -rn "| null\|| undefined\|Optional\[" ./src | grep -v "test" | head -20
```

**Common contract violations**:

| Violation | Example | Impact |
|-----------|---------|--------|
| Pagination returns wrong total | `total: items.length` (filtered count, not total) | UI shows wrong page count |
| Error response doesn't match schema | 500 returns HTML instead of JSON | Client parser crashes |
| Null field in "required" schema | Database allows null but API schema says required | Runtime type error at client |
| Inconsistent date formats | Some endpoints return ISO, others return timestamps | Client display bugs |
| Missing fields in partial update response | PATCH returns only changed fields, not full object | Client cache becomes stale |
| Status code mismatch | Returns 200 for created resource (should be 201) | Client retry logic breaks |

---

## Category 11: Regression Detection via Git Analysis

### What to Look For

Use git history to identify recently introduced bugs and areas of high instability.

```bash
# Find recently introduced complex changes (high regression risk)
git log --since="30 days ago" --stat --oneline | head -60

# Find files with frequent "fix" commits (indicates ongoing instability)
git log --oneline --all | grep -i "fix\|bug\|patch\|hotfix" | head -20

# Find reverted commits (indicates shipped bugs)
git log --oneline --all | grep -i "revert" | head -10

# Find files changed in both "feature" and "fix" commits (feature incomplete)
git log --oneline --name-only --since="60 days ago" | sort | uniq -c | sort -rn | head -20

# Find code that was recently refactored (regression risk from refactoring)
git log --since="14 days ago" --diff-filter=M --name-only --pretty=format: | sort | uniq -c | sort -rn | head -15
```

**Git-based bug detection heuristics**:

| Signal | What It Means | Action |
|--------|--------------|--------|
| File with 5+ fix commits in 30 days | Chronic instability | Deep audit this file |
| Reverted commits | Bug was shipped | Verify the revert is complete |
| Same file in feature + fix commits | Feature was incomplete | Check test coverage |
| Large commit (>500 lines changed) | Hard to review, bug-prone | Review carefully |
| Commit message says "quick fix" or "temp" | Shortcut taken | Check for proper solution |

---

## Bug Detection Checklist

Run through this checklist for every module in the audit:

- [ ] **Race conditions**: Are shared mutable state accesses synchronized?
- [ ] **Resource leaks**: Is every open/acquire matched with close/release in all paths?
- [ ] **Null propagation**: Are nullable return values checked before use?
- [ ] **Error swallowing**: Do catch blocks properly handle or propagate errors?
- [ ] **Copy-paste bugs**: Are near-duplicate blocks fully adapted to their new context?
- [ ] **State violations**: Are state transitions guarded and validated?
- [ ] **Temporal coupling**: Are operation ordering dependencies explicit and enforced?
- [ ] **Boundary errors**: Are arithmetic operations and array accesses bounds-checked?
- [ ] **Logic inversions**: Are boolean conditions tested for correctness (not just coverage)?
- [ ] **Contract violations**: Does the implementation match the documented/typed behavior?
- [ ] **Recent regressions**: Do recently-changed files have corresponding test updates?

---

## Bug Severity Quick Reference

| Bug Type | Typical Severity | Escalation Trigger |
|----------|-----------------|-------------------|
| Race condition in auth/payment | Critical | Immediate |
| Resource leak in hot path | High | Current sprint |
| Null crash on critical user journey | High | Current sprint |
| Error swallowing hiding data loss | Critical | Immediate |
| Copy-paste bug in security check | Critical | Immediate |
| State violation causing stuck records | High | Current sprint |
| Temporal coupling in deployment | Medium | Next sprint |
| Integer overflow in pricing | Critical | Immediate |
| Logic inversion in access control | Critical | Immediate |
| API contract violation (minor) | Low | Backlog |
