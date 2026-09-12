# Refactor Workflow — Autonomous Loop Reference

When the user asks to **refactor, clean up, reorganize, or simplify** existing code,
follow this safety-first protocol within the autonomous loop.

---

## The Golden Rule of Refactoring

> **NEVER change behavior and structure simultaneously.**
>
> First make the change easy (refactor), then make the easy change (new behavior).
> — Kent Beck

---

## The Safe Refactoring Loop

```
┌────────────────────────────────────────────────────────────────┐
│  1. CHARACTERIZE — Ensure tests exist for current behavior     │
│  2. IDENTIFY     — Choose ONE structural improvement           │
│  3. TRANSFORM    — Apply the refactoring (structure only)      │
│  4. VERIFY       — All tests still pass (behavior preserved)   │
│  5. ASSESS       — More improvements? Loop. Clean? Done.       │
└────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Characterize Current Behavior (Iterations 1–3)

### Verify Existing Tests

Before touching ANYTHING:
1. Run the full test suite
2. Note which tests cover the code you'll refactor
3. Note test count and all-pass status (this is your baseline)

**If tests are missing for the refactoring target:**
- Write characterization tests FIRST
- These tests document CURRENT behavior (even if it's wrong)
- They protect against accidental behavior changes during refactoring

### Characterization Test Pattern

```python
# Characterization test: documents what the code CURRENTLY does
def test_process_order_current_behavior():
    """This test captures current behavior for safe refactoring.
    It may include quirks that are intentional or accidental."""
    result = process_order(sample_input)
    assert result.status == "completed"
    assert result.total == 42.50
    assert len(result.items) == 3
```

### Document Baseline

Before refactoring begins, record:
- Total test count: ___
- All passing: YES
- Coverage of target area: (rough percentage)
- Known quirks or edge cases

---

## Phase 2: Identify Improvement (Iteration 2–4)

### Common Refactoring Targets

| Code Smell | Refactoring |
|-----------|-------------|
| Long function (>30 lines) | Extract Method |
| Duplicate code | Extract & Parameterize |
| Deep nesting (>3 levels) | Early return / Guard clause |
| God class (too many responsibilities) | Extract Class |
| Feature envy (uses another class's data) | Move Method |
| Long parameter list (>4 params) | Introduce Parameter Object |
| Switch/case on type | Replace with Polymorphism |
| Magic numbers/strings | Extract Constant |
| Temporal coupling (must call A before B) | Combine into single operation |
| Dead code | Delete it |

### Choose ONE Improvement Per Iteration

Don't try to fix everything at once. Pick the ONE change that:
1. Has the highest impact on readability/maintainability
2. Is safely achievable in one step
3. Has test coverage protecting the behavior

### Plan the Transform

Before executing, know exactly:
- What code will change (specific lines/blocks)
- What the result will look like
- What tests should still pass after

---

## Phase 3: Apply Transformation (Iterations 3–N)

### Extract Method/Function

**When:** Function is too long, or a block of code has a clear purpose

```python
# Before: Long function with mixed concerns
def process_order(order):
    # 15 lines of validation...
    # 20 lines of calculation...
    # 10 lines of notification...

# After: Clear responsibilities
def process_order(order):
    validate_order(order)
    total = calculate_order_total(order)
    notify_order_processed(order, total)
```

### Flatten Nesting (Guard Clauses)

**When:** Deep `if/else` nesting makes logic hard to follow

```python
# Before: Deep nesting
def get_discount(user):
    if user:
        if user.is_member:
            if user.years > 5:
                return 0.20
            else:
                return 0.10
        else:
            return 0.0
    else:
        return 0.0

# After: Guard clauses (early return)
def get_discount(user):
    if not user:
        return 0.0
    if not user.is_member:
        return 0.0
    if user.years > 5:
        return 0.20
    return 0.10
```

### Remove Duplication (DRY)

**When:** Same logic appears in 2+ places

```python
# Before: Duplicated validation
def create_user(data):
    if not data.get('email') or '@' not in data['email']:
        raise ValueError("Invalid email")
    ...

def update_user(data):
    if not data.get('email') or '@' not in data['email']:
        raise ValueError("Invalid email")
    ...

# After: Extracted shared validation
def validate_email(email):
    if not email or '@' not in email:
        raise ValueError("Invalid email")

def create_user(data):
    validate_email(data.get('email'))
    ...

def update_user(data):
    validate_email(data.get('email'))
    ...
```

### Rename for Clarity

**When:** Names don't communicate purpose

```python
# Before: Unclear names
def proc(d, f):
    r = []
    for i in d:
        if f(i):
            r.append(i)
    return r

# After: Clear names
def filter_items(items, predicate):
    matching = []
    for item in items:
        if predicate(item):
            matching.append(item)
    return matching
```

### Simplify Conditionals

**When:** Boolean logic is tangled or redundant

```python
# Before: Overly complex condition
if not (not user.active or user.banned) and user.verified:

# After: Simplified
if user.active and not user.banned and user.verified:

# Even better: Named condition
is_eligible = user.active and not user.banned and user.verified
if is_eligible:
```

### Extract Constant

**When:** Magic numbers or strings appear in code

```python
# Before: Magic numbers
if retry_count > 3:
    await asyncio.sleep(30)

# After: Named constants
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 30

if retry_count > MAX_RETRIES:
    await asyncio.sleep(RETRY_DELAY_SECONDS)
```

---

## Phase 4: Verify After Every Change (CRITICAL)

### After EVERY single transformation:

1. **Run all tests** — They MUST all pass
2. **Run type checker** — No new type errors
3. **Run linter** — No new warnings

If any test fails:
- Your refactoring changed behavior (it shouldn't have)
- UNDO the change immediately
- Re-analyze what went wrong
- Try a smaller transformation

### The No-Red Rule

> Tests must be green before, during (at each step), and after refactoring.
> If you see red, you've gone too far. Undo and take a smaller step.

---

## Phase 5: Assess & Continue (Iterations N–30)

### After Each Successful Transform

Ask:
1. Is the code now at acceptable quality?
2. Are there more improvements with high impact?
3. Is the refactoring goal the user stated achieved?

### When to Stop

**Stop when:**
- The user's stated refactoring goal is achieved
- Code is readable and well-structured
- All tests pass
- Diminishing returns on further changes

**Don't stop because:**
- You did one rename
- One function was extracted
- "It's better than before" (is it GOOD though?)

---

## Large-Scale Refactoring

For major refactoring (renaming modules, moving files, changing architecture):

### Strangler Fig Pattern
1. Create the new structure alongside the old
2. Migrate consumers one at a time to the new structure
3. After all consumers migrated, delete the old structure
4. Never break the system during migration

### File Move Strategy
1. Create new file in target location
2. Copy code to new file
3. Update imports in ONE consumer
4. Verify tests pass
5. Repeat for remaining consumers
6. Delete old file

### Interface Change Strategy
1. Add new interface alongside old one
2. Implement new interface
3. Migrate callers one at a time
4. Each migration: verify tests pass
5. Remove old interface when no callers remain

---

## Quality Checklist (Before Declaring Refactoring Complete)

- [ ] All tests that passed before still pass
- [ ] No behavior has changed (same inputs produce same outputs)
- [ ] Code is measurably more readable/maintainable
- [ ] No new type errors or lint warnings
- [ ] No dead code left behind
- [ ] No orphaned files or unused imports
- [ ] Naming is consistent throughout the affected area
- [ ] Functions are focused (single responsibility)
- [ ] Nesting depth is reasonable (≤3 levels)
- [ ] No remaining duplication in the refactored area
