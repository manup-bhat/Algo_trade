# Reusability & Development Principles Assessment

> "The goal of software architecture is to minimize the human resources required to build
> and maintain the required system." — Robert C. Martin (Clean Architecture)

> "Simplicity is prerequisite for reliability." — Edsger W. Dijkstra

This reference provides a systematic assessment of adherence to proven software engineering
principles. These principles, when followed, produce code that is easier to understand, test,
modify, and extend — directly reducing defect density and increasing development velocity.

---

## Why Principles Matter (The Economics)

From the research:
- **15× higher defect density** in low-quality code vs high-quality code (Tornhill & Borg, 2022)
- **2× longer** to resolve issues in low-quality code
- High-quality code has **negative cost** — it saves more time than it takes to write (Martin Fowler)
- Elite teams (DORA) achieve both speed AND reliability by maintaining internal quality
- SonarSource 2026: Code quality is a prerequisite for AI-assisted development — AI agents produce worse output in low-quality codebases

**When principles are violated systematically**, the team experiences:
- Features take longer and longer to ship (velocity decay)
- Bug rate increases with each new feature (exponential, not linear)
- Onboarding new developers takes months instead of weeks
- Simple changes require touching 10+ files (shotgun surgery)
- Fear of refactoring because "everything breaks"

---

## SOLID Principles Assessment

### S — Single Responsibility Principle (SRP)

> "A class should have only one reason to change." — Robert C. Martin

**What to check**:
- Does each file/module/class have a clear, singular purpose?
- Can you describe what a module does in one sentence without using "and"?
- When requirements change, does only one part of the system need updating?

**Violation signals**:

| Signal | Threshold | Example |
|--------|-----------|---------|
| File > 300 lines | Medium risk | `UserService.ts` — 800 lines handling auth, profile, preferences, notifications |
| Class > 5 public methods | Review needed | One class doing validation + persistence + formatting |
| Function > 30 lines | Complexity risk | Single function with 3+ levels of nesting |
| File imports from 5+ different domains | Coupling smell | Importing auth, payment, email, analytics, logging |
| Mixed abstraction levels | Readability issue | HTTP handling + business logic + DB queries in one function |

**Detection**:

```bash
# Find large files (potential SRP violations)
find ./src -name "*.ts" -o -name "*.py" -o -name "*.go" -o -name "*.java" | \
  xargs wc -l | sort -rn | head -20

# Find classes/modules with too many public methods
grep -rn "export function\|export const\|export class\|public " ./src | \
  awk -F: '{print $1}' | sort | uniq -c | sort -rn | head -20

# Find functions with too many lines
# (language-specific; use complexity tools for precision)
grep -rn "function \|def \|func " ./src | head -50
```

**Remediation patterns**:
- Extract Class: Split God class into focused classes
- Extract Method: Break large functions into named sub-operations
- Move Method: Relocate logic to the class that owns the data
- Facade Pattern: Create simple interface over complex subsystem

---

### O — Open/Closed Principle (OCP)

> "Software entities should be open for extension, but closed for modification."

**What to check**:
- Can new behavior be added without changing existing code?
- Are extension points provided where requirements frequently change?
- Do changes require modifying switch/if-else chains?

**Violation signals**:

| Signal | Example | Fix |
|--------|---------|-----|
| Growing switch/if-else on type | `if (type === 'email') {...} else if (type === 'sms') {...}` | Strategy pattern |
| Every new feature requires changing a core file | `router.ts` grows with every feature | Plugin/registration pattern |
| Conditional logic based on feature flags throughout code | `if (newFeature) { ... } else { ... }` everywhere | Feature abstraction |
| Constants file that grows with every new type | `TYPES = ['a', 'b', 'c', ...]` extended frequently | Registry pattern |

**Detection**:

```bash
# Find growing switch statements
grep -rn "switch\|case " ./src | awk -F: '{print $1}' | sort | uniq -c | sort -rn | head -10
# Files with many case statements may violate OCP

# Find if-else chains (> 3 branches)
grep -rn "else if\|elif " ./src | awk -F: '{print $1}' | sort | uniq -c | sort -rn | head -10

# Find files that change with every feature (high churn = potential OCP violation)
git log --since="6 months ago" --name-only --pretty=format: | sort | uniq -c | sort -rn | head -20
```

---

### L — Liskov Substitution Principle (LSP)

> "Objects of a superclass shall be replaceable with objects of its subclasses without
> breaking the application."

**What to check**:
- Can subclasses be used wherever the base class is expected?
- Do subclasses honor the contracts (preconditions, postconditions) of the base?
- Are there type checks (`instanceof`, `typeof`, `is`) after receiving a base type?

**Violation signals**:

| Signal | Example | Fix |
|--------|---------|-----|
| `instanceof` / `typeof` checks on received params | `if (shape instanceof Circle)` | Use polymorphism |
| Subclass throws where base doesn't | `NotImplementedError` in override | Don't inherit if you can't fulfill the contract |
| Subclass ignores base method behavior | Override returns null where base always returns value | Redesign hierarchy |
| Forced inheritance for code reuse | `AdminUser extends User` when admin isn't really a user | Composition over inheritance |

**Detection**:

```bash
# Find type checks that might indicate LSP violations
grep -rn "instanceof\|typeof.*===\|is_instance\|type(" ./src | grep -v "test\|spec" | head -20

# Find NotImplementedError / abstract method violations
grep -rn "NotImplementedError\|throw.*not implemented\|raise.*NotImplemented" ./src | head -10

# Find classes that override and change behavior significantly
grep -rn "override\|@Override\|super\(\)" ./src | grep -v "test" | head -20
```

---

### I — Interface Segregation Principle (ISP)

> "No client should be forced to depend on methods it does not use."

**What to check**:
- Are interfaces/type definitions focused and cohesive?
- Do implementations have empty/no-op methods for interface methods they don't need?
- Do clients use all methods of the interfaces they depend on?

**Violation signals**:

| Signal | Threshold | Example |
|--------|-----------|---------|
| Interface with > 5 methods | Review needed | `IRepository` with 15 methods |
| Implementation with no-op methods | Violation | `class Cache implements IStorage { delete() { /* no-op */ } }` |
| Client imports interface but uses only 1 method | Over-coupling | Importing full `IUserService` for `getById()` only |
| "God interface" that everything implements | Architecture issue | `IService` with auth, crud, events, logging all mixed |

**Detection**:

```bash
# Find large interfaces
grep -rn "interface\|protocol\|trait\|abstract class" ./src | \
  grep -v "test" | head -30
# Then check how many methods each has

# Find no-op implementations (methods that do nothing)
grep -rn "() {}\|pass\|return nil\|return null\|return undefined" ./src | \
  grep -v "test\|mock\|stub" | head -20
```

---

### D — Dependency Inversion Principle (DIP)

> "High-level modules should not depend on low-level modules. Both should depend on abstractions."

**What to check**:
- Does business logic import infrastructure directly (DB drivers, HTTP clients, file systems)?
- Can you swap implementations without changing business logic?
- Are dependencies injected rather than created internally?

**Violation signals**:

| Signal | Example | Fix |
|--------|---------|-----|
| `new ConcreteClass()` in business logic | `const db = new PostgresClient()` in service | Inject via constructor/parameter |
| Direct import of infrastructure in domain | `import { prisma } from './database'` in service | Import interface, inject implementation |
| Hard-coded external service URLs | `fetch('https://api.stripe.com/...')` in business logic | Inject client or config |
| No way to test without real infrastructure | Tests require real DB, real API | Dependency injection enables mocking |

**Detection**:

```bash
# Find direct infrastructure imports in business/service/domain layers
grep -rn "import.*prisma\|import.*mongoose\|import.*sequelize\|import.*redis\|import.*axios" \
  ./src/services ./src/domain ./src/core 2>/dev/null | grep -v "test\|mock"

# Find 'new' keyword in service/domain layers (potential DIP violation)
grep -rn "new .*Client\|new .*Connection\|new .*Pool\|new .*Driver" \
  ./src/services ./src/domain 2>/dev/null | grep -v "test\|mock"

# Find hardcoded URLs in non-config files
grep -rn "https://\|http://\|localhost:" ./src | \
  grep -v "test\|config\|env\|\.md\|comment\|doc" | head -20
```

---

## DRY — Don't Repeat Yourself

> "Every piece of knowledge must have a single, unambiguous, authoritative representation
> within a system." — The Pragmatic Programmer

**What to check**:
- Is the same business logic implemented in multiple places?
- Is the same validation duplicated across endpoints?
- Is the same transformation written in multiple services?
- Are the same constants defined in multiple files?

**Detection approach**:
See [duplicate-waste-analysis.md](./duplicate-waste-analysis.md) for comprehensive duplication detection.

**Quick DRY check**:

```bash
# Find repeated logic patterns
npx jscpd ./src --min-lines 5 --min-tokens 50 --threshold 3

# Find duplicated constants
grep -rn "const.*=\s*['\"]" ./src | awk -F= '{print $2}' | sort | uniq -d | head -20

# Find duplicated validation patterns
grep -rn "validate\|sanitize\|check\|verify" ./src | \
  awk -F: '{print $1}' | sort | uniq -c | sort -rn | head -10
```

**DRY violation severity**:

| Copies | Severity | Action |
|--------|----------|--------|
| 2 copies | Low | Consider extracting on next touch |
| 3 copies | Medium | Extract into shared utility this sprint |
| 4+ copies | High | Extract immediately — maintenance risk |

---

## KISS — Keep It Simple, Stupid

> "Everything should be made as simple as possible, but not simpler." — Einstein (attributed)

**What to check**:
- Is the code more complex than the problem requires?
- Are there abstractions that serve no current purpose?
- Can a junior developer understand this code in 30 seconds?
- Are there simpler alternatives to the current approach?

**KISS violation signals**:

| Signal | Example | Simpler Alternative |
|--------|---------|-------------------|
| Generic where concrete suffices | `Processor<T>` only used with `User` | `UserProcessor` |
| Pattern where direct code works | Factory for one type | Direct construction |
| Abstraction layer that just delegates | Service → ServiceImpl (same methods) | Remove interface, use class directly |
| Over-parameterized function | 8+ parameters, most optional | Params object or builder pattern |
| Metaprogramming for simple cases | Reflection to call methods by string name | Direct method calls |
| Custom framework over library | Re-implementing Express routing logic | Use the library |

**Detection — Cognitive Complexity**:

Cognitive Complexity (SonarSource model) measures how hard code is for a human to understand.
Unlike cyclomatic complexity, it penalizes nesting depth and breaks in linear flow.

```bash
# Measure cyclomatic complexity as proxy (cognitive complexity needs SonarQube)
npx eslint --rule '{"complexity": ["warn", 10]}' ./src 2>/dev/null

# Python
pip install radon
radon cc ./src -s -n C  # Show functions with complexity >= C grade

# Find deeply nested code (indicator of high cognitive complexity)
grep -rn "^\s\{12,\}" ./src --include="*.ts" --include="*.py" | head -20
# Lines with 12+ spaces of indentation = 3+ nesting levels
```

**Cognitive Complexity thresholds**:

| Score | Rating | Action |
|-------|--------|--------|
| 1–5 | Simple | No action needed |
| 6–10 | Moderate | Consider simplifying if high-churn |
| 11–15 | Complex | Should be refactored |
| 16–25 | Very complex | Must be refactored |
| 25+ | Unmaintainable | Urgent refactoring needed |

---

## YAGNI — You Aren't Gonna Need It

> "Always implement things when you actually need them, never when you just foresee
> that you need them." — Ron Jeffries

**What to check**:
- Are there extension points/hooks that nothing uses?
- Are there configuration options that are never configured differently?
- Are there generic type parameters that are always the same type?
- Are there "future-proofing" comments with no linked ticket?

**Detection**:

```bash
# Find potentially unused extension points
grep -rn "plugin\|hook\|extension\|register\|middleware\|interceptor" ./src | \
  grep -v "test\|node_modules" | head -20
# Then check: are these actually used by more than one implementation?

# Find TODO comments mentioning future work (YAGNI indicator if no ticket)
grep -rn "TODO.*future\|TODO.*later\|TODO.*eventually\|YAGNI\|might need" ./src | head -20

# Find generic type parameters
grep -rn "<T>\|<T,\|<T extends" ./src --include="*.ts" | head -20
# Check: is T always the same concrete type?

# Find configuration constants that never vary
grep -rn "config\.\|options\.\|settings\." ./src | \
  awk -F'[.[]' '{print $2}' | sort | uniq -c | sort -rn | head -20
```

---

## 12-Factor App Compliance

The [12-Factor methodology](https://12factor.net/) defines best practices for modern cloud-native applications.
Violation of these factors causes deployment issues, environment inconsistencies, and scaling problems.

### 12-Factor Audit Checklist

| Factor | Check | Detection Command |
|--------|-------|-------------------|
| **I. Codebase** | One repo, multiple deploys | `git remote -v` — should be one origin |
| **II. Dependencies** | Explicitly declared, no implicit system deps | Check package.json/requirements.txt completeness |
| **III. Config** | Store in environment, NOT in code | `grep -rn "hardcoded\|localhost\|password\s*=" ./src` |
| **IV. Backing Services** | Treat as attached resources (swappable) | Check if DB/cache/queue connections are configurable |
| **V. Build, Release, Run** | Strictly separate stages | Check if build artifacts are reproducible |
| **VI. Processes** | Stateless processes (no local state between requests) | `grep -rn "global\|module.*state\|singleton" ./src` |
| **VII. Port Binding** | Export services via port binding | Check if app is self-contained (not relying on app server) |
| **VIII. Concurrency** | Scale via process model | Can multiple instances run simultaneously? |
| **IX. Disposability** | Fast startup, graceful shutdown | Check for startup init time, shutdown handlers |
| **X. Dev/Prod Parity** | Keep dev/staging/prod similar | Docker usage? Same DB in dev and prod? |
| **XI. Logs** | Treat as event streams (stdout) | `grep -rn "writeFile.*log\|fs.*log\|open.*log" ./src` |
| **XII. Admin Processes** | Run admin/management as one-off processes | Check for migration scripts, admin commands |

### Key 12-Factor Violations to Detect

```bash
# Factor III: Hardcoded configuration (should be in env vars)
grep -rn "localhost\|127\.0\.0\.1\|:3000\|:5432\|:6379\|:27017" ./src | \
  grep -v "test\|spec\|\.env\|config\|docker\|README" | head -20

# Factor VI: Process state (should be stateless)
grep -rn "global\.\|module\.exports.*=\s*{" ./src --include="*.ts" --include="*.js" | \
  grep -v "const\|freeze\|test" | head -20

# Factor XI: File-based logging (should use stdout)
grep -rn "createWriteStream\|appendFile\|writeFile.*log\|open.*\.log\|logging\.FileHandler" ./src | \
  grep -v "test" | head -10
```

---

## Clean Architecture Assessment

### Dependency Direction Rule

> "Source code dependencies must point only inward, toward higher-level policies."

```
[Frameworks & Drivers] → [Interface Adapters] → [Use Cases] → [Entities]
         (outer)                                                   (inner)
```

**Inner layers must NOT import from outer layers.**

**Detection**:

```bash
# Find domain/core importing from infrastructure (violation)
grep -rn "import.*database\|import.*http\|import.*express\|import.*flask" \
  ./src/domain ./src/core ./src/entities 2>/dev/null

# Find services importing from controllers/handlers (violation)
grep -rn "import.*controller\|import.*handler\|import.*route\|import.*view" \
  ./src/services ./src/use-cases ./src/domain 2>/dev/null

# Find circular dependencies
# Node.js:
npx madge --circular ./src 2>/dev/null
# Python:
# pydeps --show-cycles ./src
```

### Layer Boundary Violations

| Violation | Example | Impact |
|-----------|---------|--------|
| Domain imports DB driver | `from sqlalchemy import ...` in domain model | Can't test without DB |
| Service imports HTTP framework | `import { Request } from 'express'` in service | Tied to one framework |
| Business logic in controller | Validation + transformation + storage in route handler | Untestable, unreusable |
| Entity knows about persistence | `user.save()` on domain object | Domain coupled to infra |

---

## Composition Over Inheritance

### What to Check

- Inheritance depth > 3 levels = probably wrong
- Multiple inheritance / mixins creating diamond problems
- Base classes with methods that some children don't use
- Inheritance used for code reuse rather than "is-a" relationship

**Detection**:

```bash
# Find deep inheritance hierarchies
grep -rn "extends " ./src | awk '{print $NF}' | sort | uniq -c | sort -rn | head -10
# Classes extended many times may have deep hierarchies

# Find multiple inheritance / mixins
grep -rn "extends.*,\|implements.*,.*," ./src | head -10
grep -rn "class.*\(.*,.*\):" ./src --include="*.py" | head -10  # Python multiple inheritance
```

---

## Law of Demeter (Principle of Least Knowledge)

> "Only talk to your immediate friends."

**Violation pattern**: `a.b.c.d.method()` — chaining through objects you shouldn't know about.

**Detection**:

```bash
# Find long method chains (potential LoD violations)
grep -rn "\.\w\+\.\w\+\.\w\+\.\w\+" ./src | grep -v "test\|spec\|node_modules\|import" | head -20

# Python
grep -rn "\.\w\+\.\w\+\.\w\+\.\w\+" ./src --include="*.py" | grep -v "test\|import" | head -20
```

**Exception**: Fluent/builder APIs (designed for chaining) and data traversal (accessing nested data structures) are NOT violations.

---

## Principles Compliance Report Template

```markdown
## Development Principles Assessment

### SOLID Compliance

| Principle | Status | Violations Found | Top Offenders |
|-----------|--------|-----------------|---------------|
| SRP | ✅/🟡/🔴 | [N] | [files with > 300 lines] |
| OCP | ✅/🟡/🔴 | [N] | [files with growing switch statements] |
| LSP | ✅/🟡/🔴 | [N] | [classes with instanceof checks] |
| ISP | ✅/🟡/🔴 | [N] | [interfaces with > 5 methods] |
| DIP | ✅/🟡/🔴 | [N] | [services importing infrastructure directly] |

### DRY Score
- Overall duplication: [X]% (threshold: < 3%)
- Locations with 3+ copies of same logic: [N]
- Status: ✅/🟡/🔴

### KISS Score
- Functions with cognitive complexity > 15: [N]
- Average cognitive complexity: [X]
- Files with > 3 nesting levels: [N]
- Status: ✅/🟡/🔴

### YAGNI Score
- Unused extension points: [N]
- Abstractions with 0–1 implementations: [N]
- Generic parameters always same type: [N]
- Status: ✅/🟡/🔴

### 12-Factor Compliance

| Factor | Status | Issues |
|--------|--------|--------|
| I. Codebase | ✅/❌ | |
| II. Dependencies | ✅/❌ | |
| III. Config | ✅/❌ | [N] hardcoded values |
| IV. Backing Services | ✅/❌ | |
| V. Build/Release/Run | ✅/❌ | |
| VI. Processes | ✅/❌ | [N] stateful patterns |
| VII. Port Binding | ✅/❌ | |
| VIII. Concurrency | ✅/❌ | |
| IX. Disposability | ✅/❌ | |
| X. Dev/Prod Parity | ✅/❌ | |
| XI. Logs | ✅/❌ | [N] file-based logging |
| XII. Admin Processes | ✅/❌ | |

### Architecture Score
- Circular dependencies: [N]
- Layer violations: [N]
- Dependency direction correct: [%]
- Status: ✅/🟡/🔴

### Overall Principles Score: [X]/100
- 90–100: Excellent adherence, high maintainability
- 70–89: Good with minor issues
- 50–69: Significant violations affecting velocity
- < 50: Systematic issues, major refactoring needed

### Top 5 Principle Violations (by impact)
1. [Violation]: [Location] — Impact: [description]
2. [Violation]: [Location] — Impact: [description]
3. [Violation]: [Location] — Impact: [description]
4. [Violation]: [Location] — Impact: [description]
5. [Violation]: [Location] — Impact: [description]
```

---

## Refactoring Patterns Quick Reference

When violations are found, apply the appropriate refactoring:

| Violation | Refactoring Pattern | Effort |
|-----------|-------------------|--------|
| God class (SRP) | Extract Class, Extract Module | Medium-High |
| Long method (SRP) | Extract Method, Compose Method | Low-Medium |
| Switch on type (OCP) | Replace Conditional with Polymorphism | Medium |
| Type checks (LSP) | Push behavior to subclasses | Medium |
| Fat interface (ISP) | Split Interface, Role Interface | Low-Medium |
| Direct dependency (DIP) | Introduce Interface, Inject Dependency | Medium |
| Duplicated logic (DRY) | Extract Method, Extract Utility | Low |
| Over-complex code (KISS) | Simplify Conditional, Inline Method | Low-Medium |
| Unused abstraction (YAGNI) | Inline Class, Remove Dead Code | Low |
| Deep nesting | Replace Nested Conditional with Guard Clauses | Low |
| Long parameter list | Introduce Parameter Object | Low |
| Feature envy | Move Method to the class that has the data | Low |
| Data clumps | Extract Class for grouped data | Low-Medium |
| Shotgun surgery | Move Method, Inline Class | Medium-High |
