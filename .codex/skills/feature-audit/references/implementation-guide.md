# Phase 3: Implementation Guide — Expert-Level Coding Practices

Writing code that works is table stakes. Senior developers write code that is correct,
readable, testable, and maintainable by the next person who touches it — including themselves
six months from now.

---

## Core Philosophy (From Google Engineering Practices)

> "The most important thing to cover in a review is the overall design of the CL.
> Do the interactions of various pieces of code in the CL make sense? Does this change
> belong in your codebase, or in a library? Does it integrate well with the rest of your system?"

Before writing a line:
1. **Is this the right place for this change?** Don't add feature logic to a utility class.
2. **Is this the right time?** If the feature area is being refactored or deprecated, coordinate first.
3. **Is the approach sound?** Design problems are 10x more expensive to fix after implementation.

---

## SOLID Principles — Applied, Not Memorized

### S — Single Responsibility Principle

Each class, function, or module should have **one reason to change**.

**Violation signs**:
- Function name contains "and": `validateAndSaveUser()` → split it
- Class has > ~200 lines and handles multiple concerns
- You need to change a utility class every time a specific feature changes

**Applied**:
```
// BAD: This function does too much
function processUserRegistration(data) {
  validateEmail(data.email);      // validation
  hashPassword(data.password);    // security
  saveToDatabase(data);           // persistence
  sendWelcomeEmail(data.email);   // side effect
}

// GOOD: Each step is separate, testable, replaceable
function registerUser(data) {
  const validated = validateRegistrationData(data);
  const prepared  = prepareUserRecord(validated);
  const saved     = userRepository.save(prepared);
  emailService.sendWelcome(saved.email);
  return saved;
}
```

---

### O — Open/Closed Principle

Code should be **open for extension, closed for modification**.

**Applied**: Use strategies, plugins, or configuration rather than modifying existing logic when
adding variations. Adding a new payment method should not require modifying the existing
payment processing core.

---

### L — Liskov Substitution Principle

Subclasses should be substitutable for their base class without breaking behavior.

**Applied**: If you override a method, it must honor the same contract (preconditions,
postconditions, side effects) as the parent. If it can't, inheritance is the wrong tool.

---

### I — Interface Segregation Principle

Don't force clients to depend on interfaces they don't use.

**Applied**: A `ReadOnlyUserRepository` interface should not force consumers to implement
`save()` and `delete()` methods they'll never need.

---

### D — Dependency Inversion Principle

High-level modules should not depend on low-level modules. Both should depend on abstractions.

**Applied**: Your `UserService` should depend on a `UserRepository` *interface*, not a concrete
`PostgresUserRepository`. This makes unit testing trivially easy (inject a mock) and allows
swapping implementations.

---

## DRY — When to Abstract vs When to Repeat

**DRY (Don't Repeat Yourself)** is about knowledge, not code. Two pieces of code can look
identical but have different reasons to change — don't force them together.

### Rule of Three
- **First time**: Just write it.
- **Second time**: Notice the duplication; consider whether they're truly the same concept.
- **Third time**: Definitely abstract it.

### When NOT to DRY
- When two things happen to look similar but serve different business purposes.
- When premature abstraction creates a wrong mental model for future readers.
- In tests: test code is allowed to repeat itself for clarity (DAMP > DRY in tests).

---

## YAGNI — You Aren't Gonna Need It

> "Developers should solve the problem they know needs to be solved now, not the problem
> that the developer speculates might need to be solved in the future."
> — Google Engineering Practices

**Violations to avoid**:
- "I'll make this configurable in case we need to change it later" — just hardcode it until you need the config.
- "I'll add a plugin system in case we need to extend this" — add the extension point when you have a second use case.
- "I'll make this generic so it works for other entities too" — make it work for one entity first.

**Applied**: Every generic abstraction added speculatively is code that must be maintained,
documented, and tested for benefits that may never materialize.

---

## Complexity — Keep It Low

> "Too complex usually means 'can't be understood quickly by code readers.' It can also mean
> 'developers are likely to introduce bugs when they try to call or modify this code.'"
> — Google Engineering Practices

### Measuring Complexity

**Function-level indicators**:
- More than 3–4 levels of nesting → extract inner logic
- More than 10–15 lines → consider splitting
- More than 3 parameters → consider a params object or restructure
- Cyclomatic complexity > 10 → too many branches, needs simplification

**Class-level indicators**:
- More than ~200 lines → likely doing too much
- More than 7–10 public methods → consider splitting responsibilities

### Reducing Complexity

```javascript
// BAD: deeply nested, hard to follow
function processOrder(order) {
  if (order) {
    if (order.items) {
      if (order.items.length > 0) {
        if (order.status === 'pending') {
          // 50 more lines of actual work
        }
      }
    }
  }
}

// GOOD: guard clauses flatten the nesting
function processOrder(order) {
  if (!order) return;
  if (!order.items?.length) return;
  if (order.status !== 'pending') return;
  // actual work at zero indent
}
```

---

## Naming Conventions (Google Engineering Practices)

> "A good name is long enough to fully communicate what the item is or does,
> without being so long that it becomes hard to read."

| Level | Good Name | Bad Name |
|-------|-----------|---------|
| Variable | `userEmailAddress` | `ue`, `data`, `temp` |
| Boolean | `isEmailVerified` / `hasPermission` | `flag`, `check`, `valid` |
| Function | `calculateDiscountedPrice()` | `calc()`, `doIt()`, `process()` |
| Class | `OrderFulfillmentService` | `Manager`, `Helper`, `Util`, `Handler` |
| Constant | `MAX_RETRY_ATTEMPTS` | `N`, `MAX`, `CONSTANT` |
| Test | `shouldReturnErrorWhenEmailIsInvalid()` | `test1()`, `testEmail()` |

**Rules**:
- Names should not require a comment to explain them
- Booleans should start with `is`, `has`, `can`, `should`
- Functions should be verb phrases (`getUserById`, not `user`)
- Collections should be plural (`orders`, not `orderList`)
- Avoid abbreviations unless universally understood (`id`, `url`, `html` are OK; `usr`, `mgr` are not)

---

## Comments — Explain WHY, Not WHAT

> "Usually comments are useful when they explain WHY some code exists, and should not be
> explaining WHAT some code is doing. If the code isn't clear enough to explain itself,
> then the code should be made simpler."
> — Google Engineering Practices

```javascript
// BAD: comments that repeat what the code says
i++; // increment i
user.save(); // save the user

// GOOD: comments that explain reasoning
// We skip soft-deleted records here because the audit log
// query runs before the deletion transaction commits.
const users = await userRepo.findAll({ includeDeleted: false });

// Using a 30-second timeout here matches the payment gateway's
// documented processing window. See TICKET-1234 for context.
const PAYMENT_TIMEOUT_MS = 30_000;
```

**When comments are always appropriate**:
- Explaining *why* a non-obvious approach was chosen
- Documenting a known limitation or workaround
- Referencing a ticket, issue, or external spec
- Warning about non-obvious side effects
- Complex regex or algorithms (explain what they match/do)

---

## Error Handling

### Principles

1. **Fail fast**: Detect invalid state as early as possible.
2. **Fail clearly**: Error messages must explain what went wrong and what the user/caller can do.
3. **Fail safely**: On error, leave the system in a valid, known state (rollback transactions).
4. **Never swallow exceptions**: `catch (e) {}` hides bugs. At minimum, log the error.
5. **Don't leak internals**: Error responses to users should never include stack traces, SQL errors, or file paths.

```javascript
// BAD: swallows error silently
try {
  await processPayment(order);
} catch (e) {}

// BAD: leaks internal details to client
res.status(500).json({ error: e.stack });

// GOOD: handles, logs, and responds appropriately
try {
  await processPayment(order);
} catch (e) {
  logger.error({ orderId: order.id, error: e.message, stack: e.stack });
  if (e instanceof PaymentGatewayError) {
    return res.status(502).json({ error: 'Payment processing unavailable. Try again.' });
  }
  return res.status(500).json({ error: 'Order could not be processed.' });
}
```

---

## Concurrency and Race Conditions

These are among the hardest bugs to find because they don't appear in normal testing.

### Common Patterns to Check

**Check-then-act** (classic TOCTOU race):
```javascript
// BAD: gap between check and action allows race condition
const exists = await db.user.findUnique({ where: { email } });
if (!exists) {
  await db.user.create({ data: { email } }); // two calls may both pass the check!
}

// GOOD: use DB-level constraints + handle the constraint error
try {
  await db.user.create({ data: { email } }); // DB unique constraint prevents duplicate
} catch (e) {
  if (isUniqueConstraintViolation(e)) {
    throw new ConflictError('Email already registered');
  }
  throw e;
}
```

**Scenarios to always check**:
- [ ] What if two users submit the same form at the same time?
- [ ] What if a background job and a user request both update the same record?
- [ ] What if an API call retries due to network timeout — is the operation idempotent?
- [ ] What if a user double-clicks a submit button? Is the action protected?

**Tools for concurrency safety**:
- Database-level unique constraints and transactions
- Optimistic locking (version fields / `updatedAt` checks)
- Idempotency keys for payment or external API operations
- Mutex or semaphore for in-process shared state

---

## Style Consistency

The best code feels like it was written by one person, even when written by ten.

**Rules**:
- Match the patterns already in the file, not your personal preference
- If you want to improve a style that isn't in the style guide, mark it as a suggestion ("Nit:")
- Do not combine style changes with functional changes in the same commit/PR — reviewers can't tell what's meaningful
- Follow the project's linter rules: they encode the team's style decisions

```bash
# Run the linter before every commit
npm run lint  # or: eslint ., flake8 ., golangci-lint run, etc.

# Auto-fix safe style issues
npm run lint -- --fix  # or: black . / gofmt -w .
```

---

## Checklist Before Opening a PR

- [ ] Does the code do exactly what the feature requires? No more, no less.
- [ ] Is the code at the right level of complexity for the problem?
- [ ] Are all names self-documenting?
- [ ] Are all comments explaining WHY, not WHAT?
- [ ] Is error handling correct, logged, and safe?
- [ ] Are there any race conditions or concurrent-access risks?
- [ ] Does the code match the style of the surrounding codebase?
- [ ] Have I removed all debugging code, console.logs, and commented-out code?
- [ ] Does the solution introduce any new shared abstractions that aren't clearly needed yet?

---

## Implementation Order — Build for Fastest Feedback

### The Experienced Developer's Build Order

1. **Build the riskiest/hardest part first** — If this doesn't work, better to know day 1 than day 10
2. **Build the thinnest vertical slice** — End-to-end but minimal. Proves the architecture works.
3. **Build the happy path** — Core functionality before edge cases
4. **Add error handling and edge cases** — Harden after foundation works
5. **Polish and optimize** — Last, because requirements might change

### Anti-Pattern: Building Layer by Layer

```
DON'T:  Database ━━━━━━━━━━━━━━━━━━━━┓
        Service ━━━━━━━━━━━━━━━━━━━━━━┫  (can't demo until ALL layers complete)
        API ━━━━━━━━━━━━━━━━━━━━━━━━━━┫
        UI ━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

DO:     ┃Slice 1┃ → Demo → ┃Slice 2┃ → Demo → ┃Slice 3┃
        (thin, all layers)  (widen)             (widen more)
```

---

## Incremental Delivery

### Ship Small, Ship Often

- Each PR should be deployable on its own (not break anything if deployed without the next PR)
- Use feature flags to ship incomplete features safely to production
- Prefer 5 small PRs over 1 large PR (faster review, easier revert, less risk)

### Feature Flag Discipline

```
# Pattern: Build behind a flag, enable when ready
if (featureFlags.isEnabled("new-checkout-flow", user)) {
  return newCheckoutFlow(request);
} else {
  return existingCheckoutFlow(request);
}
```

**Feature flag lifecycle**:
1. Create flag (default OFF)
2. Build feature behind flag
3. Test in staging with flag ON
4. Gradually enable in production (% rollout or specific users)
5. When stable: remove flag and old code (don't leave flags forever!)

---

## Defensive Programming at Boundaries

### Validate at System Edges, Trust Internally

```
[External World] ──→ [VALIDATE HERE] ──→ [Internal Code - trusted data]
                          │
                    Reject invalid
                    input AT the boundary.
                    Never validate deep
                    inside business logic.
```

**What to validate at boundaries**:
- HTTP request bodies (schema validation: Zod, Pydantic, Joi, etc.)
- File uploads (size, type, content)
- Environment variables (at startup, fail fast if missing)
- External API responses (don't trust — validate shape and types)
- Database reads (handle null/missing records)
- Message queue payloads (schema versioned, unknown fields handled)

**What NOT to do**:
- Don't validate the same thing at every layer (once at the boundary is enough)
- Don't silently coerce bad input into "good enough" input (reject clearly)
- Don't trust client-side validation (always validate server-side too)

---

## Error Handling Philosophy

### Handle Errors at the Right Layer

| Layer | Error Responsibility |
|-------|---------------------|
| **Controller/Handler** | Convert domain errors into HTTP responses. Don't leak internals. |
| **Service/Business Logic** | Throw domain-specific errors. Don't catch unless you can handle. |
| **Data/Repository** | Throw if operation fails. Don't hide failures. |
| **Utility/Helper** | Document what can throw. Let callers decide how to handle. |

### Error Handling Rules

1. **Don't swallow errors** — `catch (e) {}` is almost always a bug
2. **Don't over-catch** — catch specific error types, not `Exception`
3. **Fail fast** — surface errors early rather than propagating corrupted state
4. **Fail loudly** — log with context (what were you trying to do? with what inputs?)
5. **Fail safely** — clean up resources in finally/defer blocks
6. **User-facing errors must be helpful** — "Something went wrong" is not helpful
