# Phase 4: Testing Strategy — The Practical Test Pyramid

A feature without tests is a feature with an unknown number of bugs.
A feature with bad tests is a feature with a false sense of confidence.
This guide is based on Martin Fowler's Practical Test Pyramid and production-proven patterns.

---

## The Test Pyramid

```
                    ▲
                   ▲ ▲
                  ▲   ▲      E2E / UI Tests
                 ▲ ▲ ▲ ▲     (fewest — high-value journeys only)
                ▲         ▲
               ▲           ▲  Integration Tests
              ▲ ▲ ▲ ▲ ▲ ▲ ▲ ▲ (moderate — test boundaries)
             ▲                 ▲
            ▲                   ▲  Unit Tests
           ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲ (most — all logic paths, fast)
```

**Rules that must not be violated**:
1. Write tests with different granularity — not just one level.
2. The more high-level a test is, the fewer of them you should have.
3. If a higher-level test fails and no lower-level test fails → write the lower-level test first.
4. Push tests as far down the pyramid as possible — lower = faster, more isolated, easier to debug.
5. **Never duplicate tests** across pyramid levels. Each level tests different concerns.

---

## Unit Tests — The Foundation

### What They Test

The smallest testable unit of behavior. A function, method, or class in isolation.

**Test what the unit does (behavior), not how it does it (implementation)**:
```javascript
// BAD: tests implementation details (brittle — breaks on refactor)
test('should call repository.findById once', () => {
  userService.getProfile(42);
  expect(userRepository.findById).toHaveBeenCalledTimes(1);
});

// GOOD: tests observable behavior (resilient — survives refactors)
test('should return user profile when user exists', async () => {
  userRepository.findById.mockResolvedValue({ id: 42, name: 'Alice' });
  const profile = await userService.getProfile(42);
  expect(profile.name).toBe('Alice');
});
```

### What to Test / What to Skip

| Test | Why |
|------|-----|
| ✅ All non-trivial code paths | These are where bugs live |
| ✅ Edge cases (null, empty, boundary) | These are where bugs hide |
| ✅ Error / exception paths | Often untested, always important |
| ✅ The "unhappy path" | Sad path bugs reach users |
| ❌ Trivial getters / setters | No logic = no tests needed |
| ❌ Third-party library behavior | Test your code, not their code |
| ❌ Private method internals | Private = implementation detail; test via public interface |

> "Don't test trivial code. You won't gain anything from testing simple getters or setters."
> — Martin Fowler

### Structure: Arrange-Act-Assert

Every unit test follows this structure:

```javascript
test('should calculate discounted price for eligible orders', () => {
  // ARRANGE: set up test data and dependencies
  const order = { total: 600, customerId: 'premium-user' };
  pricingRules.getDiscount.mockReturnValue(0.10);

  // ACT: call the function under test
  const result = calculateOrderTotal(order);

  // ASSERT: verify the expected outcome
  expect(result.finalPrice).toBe(540);
  expect(result.discountApplied).toBe(60);
});
```

Alternative mnemonic: **Given → When → Then** (BDD style):
```javascript
describe('given a premium customer with a large order', () => {
  describe('when calculateOrderTotal is called', () => {
    it('then applies the 10% discount', () => { ... });
    it('then does not apply discount twice', () => { ... });
  });
});
```

### Mocking and Stubbing

**Mock**: An object that records calls and can assert on them.
**Stub**: An object that returns pre-configured responses.

**Sociable tests** (use real collaborators when fast and side-effect-free):
```javascript
// OK: UserProfile is a simple data class — use the real one
const profile = new UserProfile({ id: 42, name: 'Alice' });
```

**Solitary tests** (mock slow, network-bound, or side-effectful collaborators):
```javascript
// MOCK: database, HTTP clients, email senders, file system
jest.mock('./userRepository');
userRepository.findById.mockResolvedValue({ id: 42, name: 'Alice' });
```

**Guideline**: Mock at the architectural boundary (database, external service), not at every internal function call. Over-mocking makes tests useless.

---

## Integration Tests — The Middle Layer

### What They Test

That your code integrates correctly with external systems: databases, file systems, external APIs.

**Narrow integration tests** (preferred): Test **one** integration point at a time. Replace other dependencies with fakes.

```
Test: UserRepository → Real Database (test instance)
Everything else: Mocked or not involved
```

**What to write integration tests for** (Martin Fowler's rule):
- Every place you **serialize or deserialize** data
- Calls to databases (read and write paths)
- Calls to external HTTP APIs
- Reading from / writing to queues or event buses
- Reading from / writing to the file system

### Database Integration Tests

Use a real (test) database. Don't mock the database in integration tests — that defeats the purpose.

```javascript
// Use in-memory or ephemeral test databases
// Jest + SQLite for Node.js:
beforeAll(async () => { await db.migrate(); });
afterEach(async () => { await db.truncate(); });
afterAll(async () => { await db.close(); });

test('should save and retrieve a user', async () => {
  // ARRANGE
  const userData = { email: 'test@example.com', name: 'Test User' };

  // ACT
  const saved = await userRepository.save(userData);
  const retrieved = await userRepository.findById(saved.id);

  // ASSERT
  expect(retrieved.email).toBe('test@example.com');
});
```

### External Service Integration Tests

Use WireMock / nock / httpretty to stub external services in tests — never call real external APIs in automated tests.

```javascript
// nock example (Node.js)
nock('https://api.payment.com')
  .post('/charge', { amount: 100, currency: 'USD' })
  .reply(200, { id: 'ch_abc123', status: 'succeeded' });

const result = await paymentService.charge({ amount: 100 });
expect(result.status).toBe('succeeded');
```

---

## Contract Tests — For API Consumers

### When to Use

When you build an API that is consumed by other teams or services. Contract tests ensure that changes don't silently break consumers.

**Consumer-Driven Contract Testing with Pact**:

1. Consumer team writes a Pact test defining what they expect from the API.
2. Pact generates a contract file (JSON).
3. Provider team runs the contract file against their service.
4. If the provider breaks the contract, the test fails.

This approach means:
- Consumers drive the interface (you only build what's needed).
- Both sides have automated regression tests for the contract.
- Neither side needs to coordinate manually for every change.

---

## End-to-End Tests — The Top of the Pyramid

### What They Test

The entire application from user action to data layer and back — through the real UI or API.

**Use sparingly**: E2E tests are slow (seconds to minutes per test), flaky (browser issues, timing), and expensive to maintain.

**Reserve E2E tests for critical user journeys only**:
- The most valuable workflows users perform
- Workflows where a failure would cause significant business impact
- Journeys that cross multiple services and can't be verified by lower-level tests

```javascript
// Playwright example: critical checkout journey
test('user can complete a purchase', async ({ page }) => {
  await page.goto('/shop');
  await page.click('[data-testid="product-add-to-cart"]');
  await page.click('[data-testid="checkout-button"]');
  await page.fill('[name="card-number"]', '4242424242424242');
  await page.fill('[name="expiry"]', '12/28');
  await page.click('[data-testid="place-order"]');
  await expect(page.locator('[data-testid="order-confirmation"]')).toBeVisible();
});
```

**E2E anti-pattern**: Writing E2E tests for edge cases that should be unit tests. The pyramids flips to an ice cream cone — slow and unstable.

---

## Acceptance Tests — Feature Validation

### What They Test

That a feature works correctly from the user's perspective. Higher-level than unit/integration, but can be run at any level.

```python
# BDD-style acceptance test (Python)
def test_user_can_add_item_to_wishlist():
    # given
    user = a_logged_in_user()
    product = a_product(name="Wireless Keyboard", in_stock=True)

    # when
    user.navigates_to(product.detail_page)
    user.clicks("Add to Wishlist")

    # then
    assert product in user.wishlist
    assert "Added to wishlist" in user.last_notification
```

---

## Avoid Test Duplication Across Levels

> "If a higher-level test spots an error and there's no lower-level test failing,
> you need to write a lower-level test."
> — Martin Fowler

**The rule**: If the same behavior is tested at multiple pyramid levels, you have test duplication. Remove the higher-level test once the lower-level test provides the same confidence.

| Scenario | Right level |
|----------|-------------|
| Discount calculation logic | Unit test |
| Discount applied to order in DB | Integration test |
| User sees discounted price in checkout | E2E test (just one) |
| Edge cases for discount logic | Unit tests only |

---

## Clean Test Code Principles

> "Test code is as important as production code. Give it the same level of care."

1. **One condition per test**: Each test asserts exactly one thing. Tests that check five things are five tests in disguise.
2. **Test names describe behavior**: `shouldReturnEmptyArrayWhenNoOrdersExist()` not `test1()`.
3. **No logic in tests**: No `if`, no loops, no try/catch (unless specifically testing exceptions). Logic in tests is untested code.
4. **DAMP over DRY in tests**: Duplication is acceptable when it improves readability. Each test should be understandable in isolation.
5. **Don't test through too many layers**: If testing `UserService`, don't also test `UserRepository` behavior — that's what integration tests are for.
6. **Tests should run in any order**: No test should depend on the side effects of another test.
7. **Avoid `sleep()` and timeouts in tests**: Use event-driven waits or mock time-dependent code.

---

## Test Coverage Targets

| Level | Target | Note |
|-------|--------|------|
| Unit | 80%+ of business logic lines/branches | Focus on non-trivial paths |
| Integration | All critical integration points | Don't measure by line count |
| E2E | Top 5–10 critical user journeys | More than this → over-invested |
| Security paths | 100% of auth/validation code | No gaps allowed |

**Warning**: 100% coverage is not 100% correct. Coverage tells you which lines ran, not whether they behaved correctly. Tests must also have meaningful assertions.

---

## Framework Quick Reference

| Framework | Unit | Integration | E2E |
|-----------|------|-------------|-----|
| Node.js / TypeScript | Jest, Vitest | Jest + Supertest, Testcontainers | Playwright, Cypress |
| Python | pytest, unittest | pytest + SQLAlchemy test session | Playwright, Selenium |
| Java | JUnit 5, Mockito | Spring Boot Test, Testcontainers | Selenium, Playwright |
| Go | testing package | testify + real DB | Playwright |
| C# | xUnit, NUnit | EF Core InMemory, Testcontainers | Playwright, Selenium |
| Ruby | RSpec | RSpec + DatabaseCleaner | Capybara |

---

## TDD for Bug Fixes

Test-Driven Development applied specifically to bug fixing:

### The Bug Fix TDD Cycle

```
1. RED:   Write a test that REPRODUCES the bug (must fail)
2. GREEN: Make the smallest change that fixes it (test passes)
3. VERIFY: Run entire test suite (nothing else breaks)
4. REFACTOR: Clean up if needed (test still passes)
```

### Why Test-First for Bugs

| Benefit | Without TDD | With TDD |
|---------|------------|----------|
| Understanding | "I think I fixed it" | "I KNOW I fixed it — test proves it" |
| Regression | Bug can return silently | Test catches it immediately |
| Scope | Might fix the wrong thing | Test defines exact expected behavior |
| Confidence | "Hope it works" | "Mathematically proven" |

### Bug Fix Test Naming Convention

```
test_bug_<ticket>_<short_description>
test_regression_<what_was_failing>
test_edge_case_<condition>_<expected_behavior>
```

---

## Property-Based Testing

Instead of testing specific examples, test INVARIANTS that should always hold:

### Concept

```
# Example-based test (fragile, limited):
assert sort([3, 1, 2]) == [1, 2, 3]

# Property-based test (robust, comprehensive):
for any list L:
  assert len(sort(L)) == len(L)                    # length preserved
  assert all(sort(L)[i] <= sort(L)[i+1])          # output is sorted
  assert set(sort(L)) == set(L)                    # elements preserved
```

### When to Use Property-Based Testing

| Good For | Not Good For |
|----------|-------------|
| Pure functions (same input → same output) | Functions with side effects |
| Data transformations (serialization, parsing) | UI interactions |
| Algorithms (sorting, searching, filtering) | Integration with external services |
| Validation logic (all valid inputs pass, all invalid fail) | Complex state machines |

### Tools

| Language | Library |
|----------|---------|
| Python | Hypothesis |
| JavaScript/TypeScript | fast-check |
| Java | jqwik |
| Haskell | QuickCheck |
| Scala | ScalaCheck |
| Rust | proptest |

---

## Mutation Testing

> "Tests that never fail are worthless. Mutation testing verifies your tests can actually detect bugs."

### Concept

Mutation testing makes small changes (mutations) to your code and checks if your tests catch them:

```
Original code: if (age >= 18) { allow(); }
Mutation 1:    if (age >  18) { allow(); }  ← Your tests should FAIL on this
Mutation 2:    if (age >= 17) { allow(); }  ← Your tests should FAIL on this
Mutation 3:    if (age >= 18) { deny();  }  ← Your tests should FAIL on this
```

If your tests pass with the mutation → your tests have a gap (they don't actually verify that behavior).

### Tools

| Language | Tool |
|----------|------|
| JavaScript/TypeScript | Stryker |
| Python | mutmut, cosmic-ray |
| Java | PIT (pitest) |
| C# | Stryker.NET |
| Ruby | mutant |

### When to Use

- On critical business logic (payment, auth, data integrity)
- When you suspect tests are superficial ("this has high coverage but bugs still escape")
- To validate test quality after writing a test suite

---

## Flaky Test Detection and Elimination

### What Makes Tests Flaky

| Cause | Symptom | Fix |
|-------|---------|-----|
| **Time dependency** | Fails around midnight, month boundaries | Use deterministic time (fake clock) |
| **Random data** | Fails unpredictably | Use seeded random or fixed test data |
| **Shared state** | Fails when other tests run first | Isolate test state, reset between tests |
| **Network calls** | Fails when service is slow/down | Mock external services in tests |
| **Race conditions** | Fails intermittently | Use proper async patterns, increase timeouts |
| **File system** | Fails on different OS/machine | Use temp directories, clean up after |
| **Database ordering** | Fails without explicit ORDER BY | Never rely on implicit ordering |

### Flaky Test Elimination Strategy

1. **Identify**: Track test pass rates. Any test < 99% pass rate is flaky.
2. **Quarantine**: Move flaky tests to a separate suite (don't block CI but don't delete)
3. **Fix root cause**: Address the underlying non-determinism
4. **Prevent**: Add lint rules or CI checks that catch common flakiness patterns

### Prevention Rules

- [ ] No `sleep()` or `setTimeout()` in tests (use proper async waiting)
- [ ] No real network calls in unit tests (mock/stub external services)
- [ ] No shared mutable state between tests (setup/teardown isolates)
- [ ] No reliance on test execution order (each test runs independently)
- [ ] No hardcoded dates/times (inject time, use relative dates)
