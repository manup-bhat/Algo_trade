# Duplicate Code & Waste Code Analysis

> "Duplication is the primary enemy of a well-designed system." — Robert C. Martin
>
> "Every piece of knowledge must have a single, unambiguous, authoritative representation
> within a system." — Andy Hunt & Dave Thomas (The Pragmatic Programmer)

This reference provides systematic methods for detecting all forms of duplicated, dead,
and wasteful code in a codebase. Reducing duplication directly improves maintainability,
reduces bug surface area, and accelerates development velocity.

---

## Why Duplication Matters

**The real cost of duplication**:
- Bug fixed in one copy but not the others → same bug keeps recurring
- Behavior changes require finding and updating all copies → missed copies cause inconsistency
- Code review burden multiplied — reviewers see "new" code that is actually a copy
- Codebase size inflated — harder to navigate, slower CI, longer onboarding
- Test burden multiplied — each copy needs its own tests (or none of them have tests)

**Industry thresholds** (SonarQube/SonarSource standards):
- ✅ **< 3% duplication** — Excellent (well-managed codebase)
- 🟡 **3–5% duplication** — Acceptable (monitor, address in tech debt sprints)
- 🔴 **> 5% duplication** — Action needed (active maintenance burden)
- 💀 **> 10% duplication** — Critical (significant velocity drag)

---

## Clone Types (Classification)

Code clones are classified into four types by their similarity level:

| Type | Name | Definition | Detection Method |
|------|------|-----------|-----------------|
| **Type 1** | Exact Clone | Identical code fragments (ignoring whitespace/comments) | Token-based tools (jscpd, PMD CPD) |
| **Type 2** | Renamed Clone | Structurally identical but with renamed identifiers | Token-based + normalization |
| **Type 3** | Gapped Clone | Similar with some statements added, removed, or modified | AST-based + threshold matching |
| **Type 4** | Semantic Clone | Different code that achieves the same functionality | Manual review + semantic analysis |

**Priority**: Type 1 and Type 2 clones are always bugs (missed refactoring opportunities).
Type 3 clones are often copy-paste bugs. Type 4 clones indicate missing shared abstractions.

---

## Detection Tools Per Language

### JavaScript / TypeScript

```bash
# jscpd — primary tool for JS/TS duplication detection
npx jscpd ./src --min-lines 5 --min-tokens 50 --reporters consoleFull
npx jscpd ./src --min-lines 10 --min-tokens 70 --format "typescript,javascript"

# With threshold reporting
npx jscpd ./src --threshold 3 --reporters consoleFull
# Exits with error code if duplication > threshold%

# Exclude test files and generated code
npx jscpd ./src --ignore "**/test/**,**/spec/**,**/*.d.ts,**/generated/**"

# ts-prune — find unused exports (dead code)
npx ts-prune

# unimported — find unused files and dependencies
npx unimported

# depcheck — find unused npm dependencies
npx depcheck
```

### Python

```bash
# pylint duplicate-code detector
pylint --disable=all --enable=duplicate-code ./src --min-similarity-lines=6

# vulture — dead code detection
pip install vulture
vulture ./src --min-confidence 80

# radon — complexity + maintainability index (correlates with duplication)
pip install radon
radon mi ./src -s  # Maintainability Index

# Python CPD (PMD Copy-Paste Detector)
# If PMD is installed:
pmd cpd --minimum-tokens 50 --language python --dir ./src
```

### Go

```bash
# dupl — Go duplication detector
go install github.com/mibk/dupl@latest
dupl -t 50 ./...

# deadcode — find unreachable code
go install golang.org/x/tools/cmd/deadcode@latest
deadcode ./...

# staticcheck — includes unused code detection
staticcheck ./...
```

### Java

```bash
# PMD CPD (Copy-Paste Detector)
pmd cpd --minimum-tokens 70 --language java --dir ./src

# SonarQube (if available)
# Configure duplication detection in quality gate

# IntelliJ IDEA — built-in duplicate detection
# Analyze → Locate Duplicates
```

### Ruby

```bash
# flay — structural similarity detection
gem install flay
flay ./app ./lib

# reek — code smell detection (includes duplication-related smells)
gem install reek
reek ./app ./lib
```

### Universal (Any Language)

```bash
# PMD CPD supports: Java, JavaScript, Python, Go, C/C++, C#, Ruby, Swift, Kotlin, and more
pmd cpd --minimum-tokens 50 --language <lang> --dir ./src

# Semgrep patterns for duplicate detection
# Write custom patterns to find specific repeated code structures
semgrep --config=p/default ./src
```

---

## Dead Code Detection

Dead code is code that exists but is never executed. It wastes maintenance time, confuses
developers, and increases attack surface without providing value.

### Categories of Dead Code

| Category | Definition | Detection |
|----------|-----------|-----------|
| **Unreachable code** | Code after return/throw/break that can never execute | Static analysis, compiler warnings |
| **Unused functions** | Exported/public but never called | ts-prune, vulture, deadcode |
| **Unused imports** | Imported but never referenced | ESLint no-unused-imports, autoflake |
| **Unused variables** | Declared but never read | Compiler/linter warnings |
| **Unused files** | Files not imported anywhere | unimported, custom scripts |
| **Unused dependencies** | Packages in manifest never imported | depcheck, pip-autoremove |
| **Orphaned tests** | Tests for deleted features | Coverage report + manual review |
| **Feature flag zombies** | Flags fully rolled out > 90 days ago | grep + git log date analysis |
| **Commented-out code** | Code in comments (should be in version control, not comments) | grep patterns |

### Detection Commands

```bash
# --- Commented-out code blocks (> 3 lines) ---
# JavaScript/TypeScript
grep -rn "^\s*//" ./src --include="*.ts" --include="*.js" | \
  grep -v "TODO\|FIXME\|NOTE\|eslint\|prettier\|@ts\|Copyright\|License" | \
  awk -F: '{print $1}' | sort | uniq -c | sort -rn | head -20

# Python (blocks of consecutive # lines)
grep -rn "^\s*#" ./src --include="*.py" | \
  grep -v "TODO\|FIXME\|NOTE\|type:\|noqa\|pragma\|coding:\|#!/" | \
  awk -F: '{print $1}' | sort | uniq -c | sort -rn | head -20

# --- Feature flag graveyards ---
# Find flags defined but potentially fully rolled out
grep -rn "featureFlag\|feature_flag\|isEnabled\|getFlag\|FF_\|FEATURE_" ./src | \
  grep -v "test\|spec" | head -20

# Check git blame on flag usage to see if they're old
git log --since="90 days ago" --all --name-only -- "*flag*" "*feature*" 2>/dev/null | head -20

# --- Unused exports (TypeScript) ---
npx ts-prune | grep -v "(used in module)"

# --- Unused files ---
npx unimported 2>/dev/null

# --- Unused dependencies ---
npx depcheck 2>/dev/null
pip install pip-autoremove && pip-autoremove --list 2>/dev/null
```

---

## Speculative Generality Detection

Speculative generality (YAGNI violation) is code written for hypothetical future requirements
that never materialized. It adds complexity without providing value.

### Signs of Speculative Generality

| Signal | Example | Action |
|--------|---------|--------|
| Abstract class with only one implementor | `AbstractPaymentProcessor` with only `StripeProcessor` | Remove abstraction, inline |
| Interface with only one implementation | `IUserRepository` → only `UserRepository` exists | Remove interface until needed |
| Function parameters never used | `function process(data, options, callback)` where options/callback always null | Remove unused params |
| Generic type parameters with one usage | `class Processor<T>` only ever instantiated with `User` | Remove generic, use concrete |
| Factory pattern for single type | `createHandler("email")` only ever called with "email" | Remove factory, use direct |
| Plugin architecture with no plugins | Extension point exists but only default behavior used | Remove extension mechanism |
| Event system with one listener | Events emitted, only one handler subscribes | Simplify to direct call |
| Configuration for values that never change | `MAX_RETRIES` config used but always set to 3 | Hardcode constant |

### Detection Commands

```bash
# Find abstract classes/interfaces with potentially only one implementation
grep -rn "abstract class\|interface " ./src --include="*.ts" | \
  while read line; do
    name=$(echo "$line" | grep -oP '(abstract class|interface)\s+\K\w+')
    count=$(grep -rn "implements $name\|extends $name" ./src | wc -l)
    echo "$count implementations: $line"
  done | grep "^[01] " | head -20

# Find functions with unused parameters (TypeScript/JavaScript)
grep -rn "function.*(.*, .*)" ./src --include="*.ts" | head -20
# Then check if parameters are used within the function body

# Find factory/builder patterns that only produce one type
grep -rn "create\|build\|make\|factory\|Factory" ./src | grep -v "test" | head -20

# Find strategy/plugin patterns with single implementation
grep -rn "Strategy\|Plugin\|Provider\|Handler\|Adapter" ./src | \
  grep "class\|interface" | head -20
```

---

## Over-Abstraction Detection

Over-abstraction is the opposite of duplication — too many layers of indirection that make
code harder to follow without providing real benefit.

### Signs of Over-Abstraction

| Signal | Threshold | Impact |
|--------|-----------|--------|
| **Indirection depth** > 5 layers | Call chain: A → B → C → D → E → F to do one thing | Debugging nightmare |
| **Thin wrappers** | Function that only calls one other function | Adds noise, no value |
| **Pass-through layers** | Service → Repository → DataAccess → DB (service adds nothing) | Remove unnecessary layer |
| **AbstractAbstractFactory** | Multiple levels of abstraction for simple operations | Over-engineering |
| **God interface** | Interface with 20+ methods | Too broad, violates ISP |
| **Micro-modules** | Packages/modules with only 1 exported function of < 10 lines | Merge into parent |

### Detection Commands

```bash
# Find thin wrappers (functions with only one statement)
# This is approximate — look for very short functions that just delegate
grep -rn "function\|=>" ./src --include="*.ts" -A 3 | \
  grep -B 1 "return\|await" | grep "function\|=>" | head -20

# Find files with very little code (potential micro-modules)
find ./src -name "*.ts" -o -name "*.py" -o -name "*.go" | \
  xargs wc -l | sort -n | head -20

# Find deep inheritance hierarchies
grep -rn "extends.*extends\|class.*extends" ./src | head -20

# Find modules that are just re-exports (barrel files with no logic)
grep -rn "export.*from\|module\.exports.*require" ./src | \
  awk -F: '{print $1}' | sort | uniq -c | sort -rn | head -10
```

---

## Duplication Remediation Strategies

Once duplication is identified, apply the appropriate refactoring pattern:

| Duplication Pattern | Refactoring | When to Apply |
|--------------------|------------|---------------|
| Same logic in 2 places | **Extract Method** — pull into shared function | Always |
| Same logic in 3+ places | **Extract Module** — create shared utility | Always |
| Similar logic with variations | **Template Method** or **Strategy Pattern** | When variations are meaningful |
| Same validation in multiple endpoints | **Shared Middleware** or **Decorator** | When all callers need same check |
| Same DB query in multiple services | **Repository Pattern** — centralize data access | When > 2 callers |
| Same error handling in multiple handlers | **Error Middleware** — centralize error processing | When pattern is consistent |
| Same transformation in multiple flows | **Mapper/Transformer** utility | When transformation is reusable |
| Copy-paste with minor differences | **Parameterization** — make differences into parameters | When differences are data, not logic |

### Decision: When NOT to Deduplicate

Not all duplication should be removed. Keep duplication when:
- The duplicated code belongs to different bounded contexts (DDD principle)
- Coupling the code would create an unnatural dependency between unrelated features
- The code is likely to diverge in the future (different business rules)
- The abstraction would be harder to understand than the duplication
- The duplication is in test setup code (tests should be independent and readable)

**Rule of Three**: Consider extracting on the second occurrence, definitely extract on the third.

---

## Waste Code Identification Summary

| Waste Type | Detection Tool | Threshold for Action |
|-----------|---------------|---------------------|
| Exact duplicates | jscpd, PMD CPD | Any occurrence (> 10 lines) |
| Near-duplicates | jscpd --min-tokens 40 | Review differences for copy-paste bugs |
| Dead exports | ts-prune, vulture | Any unused public symbol |
| Dead files | unimported | Any file not imported |
| Dead dependencies | depcheck, pip-autoremove | Any installed but unused |
| Commented-out code | grep patterns | Any block > 3 lines |
| Feature flag zombies | grep + git log date | Any flag > 90 days since last toggle |
| Speculative generality | Manual + static analysis | Abstractions with 0-1 implementations |
| Over-abstraction | Call depth analysis | Indirection > 5 layers for simple operations |
| Orphaned tests | Coverage + import analysis | Tests for deleted code |

---

## Duplication Report Template

After analysis, fill in this report section:

```markdown
## Duplicate & Waste Code Analysis

### Overall Duplication Score: [X]%
- Threshold: < 3% (excellent), 3-5% (acceptable), > 5% (action needed)
- Status: ✅ / 🟡 / 🔴

### Clone Map (Top Duplications)

| # | Type | Lines | File A | File B | Recommendation |
|---|------|-------|--------|--------|---------------|
| 1 | Type 1 (exact) | 45 lines | [file:line] | [file:line] | Extract to shared utility |
| 2 | Type 2 (renamed) | 30 lines | [file:line] | [file:line] | Parameterize differences |
| 3 | Type 3 (gapped) | 25 lines | [file:line] | [file:line] | Review for copy-paste bugs |

### Dead Code Inventory

| Category | Count | Files | Action |
|----------|-------|-------|--------|
| Unused exports | [N] | [list] | Remove |
| Unused files | [N] | [list] | Remove |
| Unused dependencies | [N] | [list] | Uninstall |
| Commented-out code | [N] blocks | [list] | Delete (it's in git history) |
| Feature flag zombies | [N] | [list] | Remove flags, clean up dead branches |

### Speculative Generality

| # | Pattern | Location | Recommendation |
|---|---------|----------|---------------|
| 1 | [e.g., Interface with 1 impl] | [file] | Remove abstraction |
| 2 | [e.g., Unused parameters] | [file] | Remove params |

### Recommendations
1. [Top priority duplication to address]
2. [Dead code cleanup batch]
3. [Speculative generality to simplify]
```
