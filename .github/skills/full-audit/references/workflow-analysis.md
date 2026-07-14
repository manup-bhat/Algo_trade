# Workflow & Data Flow Analysis

> "A system is only as reliable as its weakest error path." — Every SRE

This reference provides systematic methods for tracing complete workflows through a system,
verifying data integrity at every boundary, and detecting gaps in error handling, async
operations, and transaction management.

---

## Why Workflow Analysis Matters

Most bugs found in production are NOT in the happy path. They exist in:
- Error paths that were never tested
- Edge cases where data is missing, malformed, or concurrent
- Async operations that are started but never completed
- Transactions that partially commit
- Retry logic that creates duplicates
- Event flows where messages are lost or delivered out of order

**The workflow audit finds these by tracing every path, not just the one the developer tested.**

---

## 1. Complete User Journey Tracing

### Methodology

For each feature, trace the COMPLETE flow from trigger to completion:

```
[Trigger] → [Validation] → [Authorization] → [Business Logic] → [Side Effects] → [Response]
     ↓           ↓              ↓                   ↓                  ↓              ↓
  [Error?]    [Error?]       [Error?]            [Error?]           [Error?]      [Error?]
     ↓           ↓              ↓                   ↓                  ↓              ↓
  [Handle]    [Handle]       [Handle]            [Handle]           [Handle]      [Handle]
```

### Happy Path Verification

For each step in the flow, verify:
- [ ] Input is validated before processing
- [ ] Authorization is checked before accessing resources
- [ ] Business rules are applied correctly
- [ ] Side effects (emails, events, logs) are triggered
- [ ] Response contains correct data in the correct format
- [ ] State changes are persisted correctly

### Error Path Verification (Critical)

**For EVERY operation that can fail, verify:**

| Question | If Missing |
|----------|-----------|
| What happens if this operation throws? | Unhandled exception → 500 error or crash |
| Is the error caught at the right level? | Caught too high → lost context; too low → noisy |
| Is the user notified appropriately? | Silent failure → user confused |
| Is the system state consistent after the error? | Partial state → data corruption |
| Are resources cleaned up on error? | Leak → degradation over time |
| Is the error logged with enough context to debug? | Undebuggable → long incident resolution |

```bash
# Find operations without error handling
# JavaScript/TypeScript — await without try/catch
grep -rn "await " ./src --include="*.ts" --include="*.js" | grep -v "try\|catch\|\.catch\|test\|spec" | head -30

# Python — calls that can raise but aren't in try blocks
grep -rn "raise\|\.connect\|\.execute\|requests\.\|open(" ./src --include="*.py" | grep -v "try\|except\|test" | head -30

# Find functions that return early on error without cleanup
grep -rn "if.*error\|if.*err\|if.*fail" ./src -A 2 | grep "return\|throw" | head -20
```

---

## 2. Data Flow Integrity

### Input Boundary Validation

Data should be validated at the SYSTEM BOUNDARY (where external data enters) and then
trusted within the system. Verify:

```
External Input → [VALIDATE HERE] → Internal Processing (trusted data)
                        ↑
            Reject invalid data AT the boundary
            Don't validate deep inside business logic
```

**Audit checklist**:

| Boundary | What to Check |
|----------|--------------|
| HTTP request body | Schema validated? Types correct? Required fields enforced? |
| URL parameters | Parsed and typed? Injection-safe? |
| Query string | Validated against whitelist of allowed params? |
| File uploads | Size limited? Type verified? Content scanned? |
| Environment variables | Parsed to correct types at startup? Fail-fast if missing? |
| Database reads | Null handling for missing records? |
| External API responses | Schema validated? Timeout handled? |
| Message queue payloads | Schema versioned? Unknown fields handled? |
| User config/settings | Bounds-checked? Sanitized before use? |

```bash
# Find unvalidated request body usage
grep -rn "req\.body\.\|request\.json\|request\.data\|request\.form" ./src | \
  grep -v "validate\|schema\|parse\|sanitize\|test" | head -20

# Find database reads without null handling
grep -rn "findOne\|findById\|get_object\|fetchone\|QueryRow" ./src | \
  grep -v "if\|?\.\|!= nil\|is not None\|test" | head -20
```

### Transformation Integrity

When data is transformed between layers, verify:
- [ ] No data is silently dropped during transformation
- [ ] Transformation errors are caught (parsing, type conversion)
- [ ] Original data is preserved if transformation fails
- [ ] Date/timezone conversions are explicit and consistent
- [ ] Currency/precision handling is correct (use integers for money, not floats)
- [ ] Encoding/decoding is symmetric (what's encoded can be decoded)

---

## 3. Async Operation Lifecycle

### Unhandled Promises / Dangling Operations

The most common workflow bug in modern applications: async operations started but never awaited.

**Detection**:

```bash
# Find fire-and-forget async calls (missing await)
grep -rn "^\s*[a-zA-Z].*\.then\|^\s*[a-zA-Z].*Async\|^\s*fetch(\|^\s*axios\." ./src --include="*.ts" --include="*.js" | \
  grep -v "await\|return\|const\|let\|var\|test" | head -20

# Find async functions called without await
grep -rn "async function\|async (" ./src --include="*.ts" -l | while read file; do
  funcs=$(grep -oP 'async function \K\w+|const \K\w+(?=\s*=\s*async)' "$file")
  for func in $funcs; do
    grep -rn "$func(" ./src | grep -v "await\|return.*$func\|test" | head -5
  done
done

# Find Promise.all/allSettled without error handling
grep -rn "Promise\.\(all\|allSettled\|race\)" ./src | grep -v "try\|catch\|\.catch\|test" | head -10

# Python — find coroutines called without await
grep -rn "async def " ./src --include="*.py" -l | while read file; do
  funcs=$(grep -oP 'async def \K\w+' "$file")
  for func in $funcs; do
    grep -rn "$func(" ./src --include="*.py" | grep -v "await\|test" | head -5
  done
done
```

### Async Error Propagation

| Pattern | Risk | Impact |
|---------|------|--------|
| `promise.catch(() => {})` | High | Error silently swallowed |
| Unhandled rejection listener missing | Medium | Process crash in Node.js |
| Background task errors not surfaced | High | Silent failures, stale data |
| Parallel operations — one fails, others continue | Medium | Inconsistent state |
| Long-running operation without timeout | High | Resource exhaustion |

### Verification Checklist

- [ ] Every `async` function call has a corresponding `await` or `.then()/.catch()` handler
- [ ] Background operations have monitoring (log success/failure, emit metrics)
- [ ] Timeouts are configured for all external calls (HTTP, DB, message queue)
- [ ] Parallel operations use `Promise.allSettled` when partial success is acceptable
- [ ] Graceful shutdown awaits in-flight operations before exit

---

## 4. Transaction Boundary Analysis

### What Can Go Wrong

Transactions ensure atomicity — either everything succeeds or nothing does. When transaction
boundaries are wrong, you get partial writes (the most dangerous kind of bug: data corruption
that looks like it worked).

**Detection**:

```bash
# Find multi-step write operations (potential transaction boundary issues)
grep -rn "\.save\|\.create\|\.update\|\.insert\|\.delete\|\.remove" ./src | \
  grep -v "test\|mock\|spec" | \
  awk -F: '{print $1}' | sort | uniq -c | sort -rn | head -20
# Files with 3+ write operations may need transaction wrapping

# Find explicit transaction usage (good sign)
grep -rn "transaction\|BEGIN\|COMMIT\|ROLLBACK\|@Transactional\|atomic" ./src | grep -v "test" | head -20

# Find sequential writes without transaction (bad sign)
grep -rn "await.*save\|await.*create\|await.*update" ./src --include="*.ts" -A 2 | \
  grep -B 1 "await.*save\|await.*create\|await.*update" | head -30
```

### Transaction Audit Questions

For each multi-step operation, ask:

| Question | If "No" → Bug |
|----------|---------------|
| Are all writes in a single transaction? | Partial writes possible on failure |
| Does the transaction rollback on ANY error? | Partial state on specific errors |
| Are reads within the transaction (if consistency required)? | Read-after-write inconsistency |
| Is the transaction scope minimal? | Long transactions → lock contention |
| Are side effects (emails, events) OUTSIDE the transaction? | Sending email for rolled-back operation |
| Is there a compensating transaction for external side effects? | Refund after failed downstream call |

### Common Transaction Bugs

| Bug | Example | Impact |
|-----|---------|--------|
| Write outside transaction | Create order, then payment fails → orphaned order | Data integrity |
| Side effect inside transaction | Send email, then rollback → user gets email for non-existent action | User confusion |
| Long transaction | Lock held during external API call → other requests blocked | Performance |
| Nested transaction misconception | Inner rollback doesn't rollback outer | Partial state |
| No retry on serialization failure | Optimistic locking fails, error propagates | Unnecessary user error |

---

## 5. Retry & Idempotency Analysis

### Why It Matters

Networks fail. Services timeout. Messages get delivered twice. If operations aren't
idempotent, retries cause duplicates (double charges, duplicate emails, duplicate records).

### Audit Checklist

For every operation that can be retried (API calls, message processing, background jobs):

| Check | Risk if Missing |
|-------|----------------|
| Is the operation idempotent? | Retries create duplicates |
| Is there a unique request ID / idempotency key? | Can't detect duplicate requests |
| Are retries configured with exponential backoff? | Thundering herd on failure |
| Is there a maximum retry count? | Infinite loop on permanent failures |
| Is the retry scope correct? (only retry the failed part, not the whole flow) | Duplicate side effects |
| Are already-completed steps skipped on retry? | Re-processing already-done work |

**Detection**:

```bash
# Find retry patterns
grep -rn "retry\|retries\|backoff\|attempt" ./src | grep -v "test" | head -20

# Find message/job processing without idempotency checks
grep -rn "process\|handle\|consume\|worker" ./src --include="*.ts" --include="*.py" | \
  grep -v "idempoten\|dedup\|already\|processed\|test" | head -20

# Find payment/financial operations (MUST be idempotent)
grep -rn "charge\|payment\|transfer\|debit\|credit\|invoice" ./src | grep -v "test" | head -20
```

### Idempotency Patterns

| Pattern | Use Case | Implementation |
|---------|----------|---------------|
| **Idempotency key** | API mutations | Client sends unique key; server rejects duplicates |
| **Status check before action** | Job processing | Check if already processed before executing |
| **Upsert instead of insert** | Data sync | Use INSERT ON CONFLICT UPDATE |
| **Outbox pattern** | Event publishing | Write event to DB, publish separately, retry-safe |
| **Saga with compensating actions** | Multi-service operations | Each step has a corresponding undo |

---

## 6. Event Flow Completeness

### What to Verify

In event-driven architectures, verify that every event has:
- At least one producer (something that emits it)
- At least one consumer (something that handles it)
- Error handling in the consumer
- Dead letter queue for unprocessable events
- Monitoring for event lag/backlog

**Detection**:

```bash
# Find all event emissions
grep -rn "emit\|publish\|dispatch\|send\|produce\|fire" ./src | \
  grep -v "test\|spec\|console\|log" | sort | head -30

# Find all event consumers
grep -rn "on(\|subscribe\|consume\|listen\|handle\|@EventHandler\|@Subscriber" ./src | \
  grep -v "test\|spec" | sort | head -30

# Cross-reference: find events emitted but never consumed (orphaned events)
# Compare the two lists above manually
```

### Event Flow Audit Matrix

| Event | Producer(s) | Consumer(s) | Error Handling | DLQ | Monitoring |
|-------|-------------|-------------|---------------|-----|-----------|
| [event_name] | [file:line] | [file:line] | ✅/❌ | ✅/❌ | ✅/❌ |

**Common event flow bugs**:

| Bug | Impact | Detection |
|-----|--------|-----------|
| Event emitted, no consumer | Feature silently broken | Cross-reference emit/subscribe |
| Consumer registered, never triggered | Dead code | Coverage analysis |
| Consumer fails silently | Lost data/actions | Check error handling in consumer |
| No DLQ configured | Poison messages block queue | Config inspection |
| Event schema changed, consumer not updated | Runtime crash in consumer | Schema version check |
| Events delivered out of order | Incorrect state transitions | Check ordering guarantees |

---

## 7. Cascading Failure Analysis

### What to Verify

A cascading failure is when one component's failure causes other components to fail,
potentially bringing down the entire system.

**Detection**:

```bash
# Find external service calls without timeouts
grep -rn "fetch(\|axios\.\|requests\.\|http\.\|grpc\." ./src | \
  grep -v "timeout\|signal\|AbortController\|deadline\|test" | head -20

# Find calls without circuit breaker patterns
grep -rn "fetch(\|axios\.\|requests\.\|http\." ./src | \
  grep -v "circuit\|breaker\|fallback\|retry\|test" | head -20

# Find synchronous blocking calls to external services
grep -rn "Sync(\|synchronous\|blocking" ./src | grep -v "test" | head -10
```

### Resilience Checklist

For every external dependency (database, API, message queue, cache):

| Check | If Missing |
|-------|-----------|
| Timeout configured? | Single slow request blocks all resources |
| Circuit breaker? | Repeated calls to dead service waste resources |
| Fallback/degradation? | Service unavailable → feature unavailable (should degrade gracefully) |
| Bulkhead (connection pool limit)? | One slow dependency exhausts all connections |
| Health check? | Can't distinguish "down" from "slow" |
| Graceful degradation? | Cache miss → DB call (not crash) |

---

## 8. State Management Audit

### For Frontend Applications

| Check | Risk |
|-------|------|
| Global state modified by multiple components? | Race conditions, stale updates |
| State derived from props not recalculated? | Stale UI |
| Form state reset on navigation? | Data leaks between forms |
| Optimistic updates rolled back on error? | Phantom state visible to user |
| Cache invalidation on mutation? | Stale data displayed |
| Memory leak from subscriptions not cleaned? | Performance degradation |

### For Backend Applications

| Check | Risk |
|-------|------|
| Module-level mutable state? | Race conditions between requests |
| Session state assumed to be consistent? | Stale session after parallel requests |
| Cache invalidation strategy defined? | Serving stale data |
| Database connection state managed? | Connection pool exhaustion |
| In-memory queue state persistent? | Data loss on restart |

---

## Workflow Analysis Report Template

```markdown
## Workflow & Data Flow Analysis

### Workflows Traced: [N]

| # | Workflow | Happy Path | Error Paths | Async Safety | Transaction Safety | Retry Safety |
|---|---------|-----------|-------------|-------------|-------------------|-------------|
| 1 | [Name] | ✅/❌ | ✅/❌/🟡 | ✅/❌ | ✅/❌/N/A | ✅/❌/N/A |
| 2 | [Name] | ✅/❌ | ✅/❌/🟡 | ✅/❌ | ✅/❌/N/A | ✅/❌/N/A |

### Data Flow Gaps

| # | Boundary | Issue | Risk |
|---|----------|-------|------|
| 1 | [e.g., API input] | [e.g., No schema validation] | [High] |

### Async Issues

| # | Location | Issue | Risk |
|---|----------|-------|------|
| 1 | [file:line] | [e.g., Unhandled promise rejection] | [High] |

### Transaction Issues

| # | Operation | Issue | Risk |
|---|-----------|-------|------|
| 1 | [e.g., Order creation] | [e.g., Payment outside transaction] | [Critical] |

### Resilience Gaps

| External Dependency | Timeout | Circuit Breaker | Fallback | Status |
|--------------------|---------|----------------|----------|--------|
| [e.g., Payment API] | ✅/❌ | ✅/❌ | ✅/❌ | 🔴/🟡/✅ |
```
