# Cross-Cutting Analysis — System-Wide Patterns

Feature-level audits examine individual features. Cross-cutting analysis examines what patterns
exist *across* features — where systemic issues live that no single feature audit would reveal.

This is the difference between finding a bug and finding the root cause of a class of bugs.

---

## 1. Authentication and Authorization Consistency

Inconsistent auth enforcement is one of the most common systemic vulnerabilities.

### What to Look For

- [ ] Is authentication enforced at a consistent layer? (Middleware vs. individual handler vs. service method)
- [ ] Is authorization enforced at the service/domain layer, not only at the route/controller layer?
- [ ] Are there any endpoints, CLI commands, job handlers, or library methods missing auth checks?
- [ ] Is there a single source of truth for auth logic — or duplicated auth code that can drift?
- [ ] Do all callers of the same resource use the same permission check?

```bash
# Find all entry points without auth middleware references
grep -rn "route\|handler\|endpoint\|controller\|command\|job" ./src | \
  grep -v "auth\|authenticate\|authorize\|permission\|require_login\|@Secured\|[Aa]uthorize"
```

**Red flags**:
- Auth checks by copy-pasting instead of calling a central function
- Comment: "// TODO: add auth check" in production code
- Public endpoints returning private data ("it's not linked from the UI" is not access control)

---

## 2. Input Validation Consistency

### What to Look For

- [ ] Is validation performed at a consistent boundary? (Request level, service level, or domain model level?)
- [ ] Are the same validation rules applied for the same data type across all entry points?
- [ ] Is there a shared validation library or schema, or is validation re-implemented per endpoint?
- [ ] Are error messages consistent across the application? (Same format, same terminology)

```bash
# Find all places inputs are first used — are they validated?
grep -rn "request\.\|req\.\|args\.\|params\.\|input\." ./src | \
  grep -v "validate\|sanitize\|parse\|schema\|assert"
```

**Red flags**:
- The same field (e.g., `email`) is validated differently in different features
- Some entry points validate, others pass through to the DB without checking
- Validation exists only client-side (CLI, UI, SDK) with no server-side equivalent

---

## 3. Error Handling Consistency

### What to Look For

- [ ] Is there a global error handler, or is error handling implemented per-endpoint?
- [ ] Are error response formats consistent? (Same schema: `{error: ..., message: ...}`)
- [ ] Do all features use the same set of error types/codes, or does each feature invent its own?
- [ ] Are stack traces or internal details leaking to consumers in any feature?

```bash
# Find all error responses — are they using a shared format?
grep -rn "catch\|except\|rescue\|recover" ./src | grep -v "test\|spec"

# Find all direct error messages returned to callers
grep -rn "Error\|Exception\|status.*500\|status.*400" ./src | head -40
```

---

## 4. Logging and Observability Consistency

### What to Look For

- [ ] Are log levels used consistently? (DEBUG = internals, INFO = operations, WARN = recoverable issues, ERROR = failures)
- [ ] Do all features emit structured (key-value / JSON) logs, or are some still using plain-text string concatenation?
- [ ] Do all error logs include the same context fields? (request/job ID, user/resource ID, error message)
- [ ] Are there features with no logging at all? (Silent failures)
- [ ] Do any log statements include sensitive data? (passwords, tokens, PII)

```bash
# Find plain-text log statements (potential inconsistency)
grep -rn "log\.\|logger\.\|print\|console\.\|fmt\.Print\|puts\|System\.out" ./src | \
  grep -v "test\|spec" | head -40

# Find logs that might include sensitive fields
grep -rn "log.*password\|log.*token\|log.*secret\|log.*card\|log.*ssn" ./src
```

---

## 5. Shared Code Quality

When a utility, helper, or base class is used widely, its quality multiplies across the whole codebase.

### What to Look For

- [ ] What are the top 10 most-imported/most-used modules? Are they high quality?
- [ ] Do shared utilities have comprehensive tests?
- [ ] Are there shared utilities that have grown into catch-all "utils" files with no clear cohesion?
- [ ] Are there circular dependencies that indicate architectural problems?

```bash
# Most-imported internal modules (Node.js)
grep -rh "from '\.\./\|from '\.\./\.\." ./src --include="*.ts" | \
  sort | uniq -c | sort -rn | head -20

# Find files with the most imports TO them (most-depended-on)
grep -rh "from '.*\|import '.*\|require('" ./src | \
  grep -v "node_modules" | sort | uniq -c | sort -rn | head -20

# Circular dependency detection
# Node.js:  npx madge --circular ./src
# Python:   pydeps ./src --show-cycles
# Go:       go build ./... (circular deps are compile errors)
```

---

## 6. Dead Code

Dead code wastes time (it must be read), creates false surface area for attackers, and can
confuse future developers into thinking old code paths are still used.

### What to Look For

- [ ] Functions that are exported/public but never called externally
- [ ] Feature flags that were never removed after full rollout
- [ ] Commented-out code blocks (version-controlled code should not be commented out)
- [ ] Files imported nowhere
- [ ] Database columns with all NULL values (never written to)

```bash
# Find commented-out code blocks
grep -rn "^[[:space:]]*//" ./src | grep -v "license\|copyright\|TODO\|FIXME\|NOTE" | head -30
grep -rn "^[[:space:]]*#" ./src --include="*.py" --include="*.rb" | \
  grep -v "license\|copyright\|TODO\|FIXME\|NOTE" | head -30

# Find potential dead exports (TypeScript)
npx ts-prune  # reports exported symbols that are never imported

# Find potential dead code (general)
grep -rn "TODO.*remove\|FIXME.*dead\|no longer used\|deprecated" ./src
```

---

## 7. Dependency Health

### What to Look For

- [ ] Are there dependencies with known CVEs? (Run a vulnerability scan)
- [ ] Are there outdated dependencies that have major version updates available?
- [ ] Are there unused dependencies (installed but never imported)?
- [ ] Are there dependencies that are no longer maintained?
- [ ] Is the dependency count proportionate? (Excessive dependencies = large attack surface)

```bash
# Vulnerability scan — run for your package manager
npm audit                       # Node.js
pip-audit                       # Python (pip install pip-audit)
./gradlew dependencyCheckAnalyze  # Java (OWASP Dependency Check)
go list -m all | nancy          # Go (nancy tool)
bundle audit                    # Ruby (bundler-audit gem)
cargo audit                     # Rust

# Check for outdated packages
npm outdated                    # Node.js
pip list --outdated             # Python
./gradlew dependencyUpdates     # Java (gradle-versions-plugin)
go list -u -m all               # Go

# Find unused dependencies
depcheck ./                     # Node.js (npm install -g depcheck)
pip-autoremove --list           # Python (approximate)
```

---

## 8. Architecture Pattern Consistency

### What to Look For

- [ ] Do all features follow the same layering pattern? (Are some bypassing the service layer and calling the DB directly from the controller/handler?)
- [ ] Is there a consistent approach to dependency injection, or are some modules creating their own dependencies?
- [ ] Do all features follow the same naming conventions? (A mix of `getUserById`, `get_user_by_id`, and `fetchUser` is a warning sign)
- [ ] Is configuration accessed consistently? (Centralized config object vs. scattered `os.getenv()` calls)

```bash
# Find files that break the expected layering
# Example: controllers/handlers that import directly from the DB layer
grep -rn "import.*repository\|from.*repository\|require.*repository" \
  ./src/controllers ./src/handlers ./src/routes 2>/dev/null

# Find direct DB calls in non-repository files
grep -rn "SELECT\|INSERT\|UPDATE\|DELETE\|db\.query\|mongoose\.\|prisma\." \
  ./src --include="*.ts" | grep -v "repository\|model\|migration\|test\|spec"
```

---

## 9. Test Coverage Distribution

### What to Look For

- [ ] Which features have zero tests?
- [ ] Which features have very low coverage on critical paths?
- [ ] Are there any test files with no assertions? (Tests that always pass)
- [ ] Is there over-concentration of E2E tests relative to unit tests? (Inverted pyramid)

```bash
# Run coverage report (substitute your test runner)
npm test -- --coverage              # Jest
pytest --cov=./src --cov-report=term-missing
go test ./... -coverprofile=cover.out && go tool cover -html=cover.out
./mvnw test jacoco:report           # Java + JaCoCo

# Find test files with no assertions (suspicious)
grep -rL "expect\|assert\|should\|must\|verify" \
  $(find . -name "*.test.*" -o -name "test_*.py" -o -name "*_test.go")
```

---

## Cross-Cutting Analysis Summary Template

Fill this out after completing the cross-cutting analysis:

```markdown
## Cross-Cutting Analysis Summary

### Auth Consistency: Pass / Partial / Fail
[Findings: e.g., "3 internal API endpoints have no auth middleware"]

### Input Validation Consistency: Pass / Partial / Fail
[Findings]

### Error Handling Consistency: Pass / Partial / Fail
[Findings]

### Observability Consistency: Pass / Partial / Fail
[Findings]

### Shared Code Quality: Pass / Partial / Fail
[Top shared modules reviewed; findings]

### Dead Code: Low / Medium / High Volume
[Approximate count; most critical instances]

### Dependency Health: Pass / Partial / Fail
[CVE count; unmaintained packages]

### Architecture Pattern Consistency: Pass / Partial / Fail
[Findings]

### Test Coverage Distribution: Pass / Partial / Fail
[Coverage %; features with zero coverage]

### Workflow Completeness: Pass / Partial / Fail
[Error paths covered %; critical workflows traced]

### Duplication Hotspots: Low / Medium / High
[Overall duplication %; top repeated patterns]

### AI-Generated Code Quality: Pass / Partial / Fail / N/A
[Hallucinated imports; phantom packages; inconsistent patterns]

### Performance Anti-Patterns: Low / Medium / High
[N+1 queries; unbounded pagination; blocking I/O count]

### Top 5 Systemic Issues
1. [Issue]: [Description] — affects [N] features
2. [Issue]: [Description] — affects [N] features
3. [Issue]: [Description] — affects [N] features
4. [Issue]: [Description] — affects [N] features
5. [Issue]: [Description] — affects [N] features
```

---

## 10. Workflow Completeness Matrix

Cross-cutting workflow analysis reveals patterns that individual feature audits miss.

### What to Look For

- [ ] Are ALL critical user journeys complete from trigger to success/failure?
- [ ] Do ALL error paths provide user-visible feedback (not silent failures)?
- [ ] Are ALL async operations awaited or explicitly fire-and-forget with monitoring?
- [ ] Do ALL multi-step writes use transactions or saga patterns?
- [ ] Are ALL external API calls protected by timeouts and fallbacks?
- [ ] Do ALL retry operations have idempotency guarantees?

```bash
# Find workflows with missing error paths (operations without try/catch/error handling)
grep -rn "await " ./src --include="*.ts" --include="*.js" | \
  grep -v "try\|catch\|\.catch\|test\|spec" | wc -l

# Find fire-and-forget patterns (missing await)
grep -rn "^\s*[a-zA-Z].*\.then\b" ./src --include="*.ts" | \
  grep -v "await\|return\|test" | head -20

# Find multi-step writes without transaction
grep -rn "\.save\|\.create\|\.update\|\.insert" ./src --include="*.ts" -A 1 | \
  grep -v "transaction\|atomic\|test" | head -20
```

---

## 11. Global Duplication Hotspots

### What to Look For

Cross-feature duplication is invisible from within a single feature. Look for:

- [ ] Same validation logic in multiple endpoints (extract to middleware)
- [ ] Same error formatting in multiple handlers (extract to error middleware)
- [ ] Same authorization check copy-pasted across routes (extract to guard)
- [ ] Same data transformation in multiple services (extract to mapper)
- [ ] Same API client configuration in multiple files (extract to shared client)

```bash
# Run global duplication detection
npx jscpd ./src --min-lines 5 --min-tokens 50 --threshold 3 2>/dev/null

# Find the most common repeated patterns across features
grep -rn "function\|const.*=.*=>" ./src --include="*.ts" | \
  awk -F'[( ]' '{print $NF}' | sort | uniq -c | sort -rn | head -20

# Find repeated import patterns (same set of imports = same pattern duplicated)
grep -rn "^import" ./src --include="*.ts" | sort | uniq -c | sort -rn | head -20
```

---

## 12. Shared Abstraction Opportunities

When 3+ features implement the same pattern, that pattern should be a shared utility.

| Pattern | Signal | Abstraction |
|---------|--------|------------|
| Same HTTP error handling | 5+ endpoints with identical catch blocks | Error middleware |
| Same validation rules | Same email/phone/date validation in 3+ places | Validation library |
| Same pagination logic | limit/offset/cursor handling duplicated | Pagination utility |
| Same caching pattern | Cache-aside pattern in 4+ services | Cache decorator |
| Same retry logic | Retry with backoff in 3+ API calls | Retry utility |
| Same auth check | Role/permission check copy-pasted | Auth middleware |

---

## 13. AI-Generated Code Quality (2026)

In the age of AI-assisted development, specific quality issues emerge from AI-generated code.

### What to Look For

- [ ] **Hallucinated imports**: Packages imported that don't exist in the project
- [ ] **Phantom APIs**: Calls to methods/functions that don't exist on the target object
- [ ] **Inconsistent patterns**: AI follows different conventions in different files
- [ ] **Over-commented obvious code**: AI adds redundant comments ("// increment counter")
- [ ] **Subtly wrong logic**: Code that looks correct but has edge-case bugs
- [ ] **Security anti-patterns**: AI-generated code that bypasses security best practices
- [ ] **Test that doesn't test**: AI writes tests that always pass regardless of implementation

```bash
# Find potentially hallucinated imports (imports of packages not in package.json)
grep -rn "^import\|^from " ./src --include="*.ts" --include="*.py" | \
  grep -v "node_modules\|\./\|\.\./\|@types" | \
  awk -F"'" '{print $2}' | sort -u > /tmp/imports.txt
# Compare with package.json dependencies

# Find functions called that don't exist (TypeScript compiler catches most)
npx tsc --noEmit 2>/dev/null | grep "Property.*does not exist\|Cannot find name" | head -20

# Find inconsistent naming within the same module
grep -rn "camelCase\|snake_case" ./src --include="*.ts" | head -20
# If both exist in same file, pattern inconsistency

# Find redundant comments (comment says what code already says)
grep -rn "//.*return\|//.*const\|//.*function\|#.*def\|#.*return" ./src | \
  grep -v "TODO\|FIXME\|NOTE\|eslint\|type:" | head -20
```

---

## 14. Performance Anti-Patterns

### What to Look For

Performance issues that span features and indicate systemic architecture problems:

| Anti-Pattern | Detection | Impact |
|-------------|-----------|--------|
| **N+1 queries** | Loop with individual DB queries inside | Exponential DB load |
| **Unbounded pagination** | No limit on result sets | Memory exhaustion |
| **Missing indexes** | Queries on unindexed columns | Slow queries at scale |
| **Blocking I/O in event loop** | Sync file/network ops in async code | All requests blocked |
| **Overfetching** | `SELECT *` or full object when only 1-2 fields needed | Network/memory waste |
| **Missing caching** | Same expensive computation repeated per request | Unnecessary load |
| **Large payloads** | API returning MB of data without pagination | Client timeout/crash |
| **Synchronous external calls** | Waiting for external API in request cycle | User latency |

```bash
# N+1 query detection (look for DB calls inside loops)
grep -rn "for\|forEach\|map\|while" ./src -A 5 | \
  grep "find\|query\|select\|execute\|fetch" | grep -v "test" | head -20

# Unbounded queries
grep -rn "findAll\|find(\|select\|SELECT" ./src | \
  grep -v "limit\|LIMIT\|take\|first\|paginate\|test" | head -20

# SELECT * usage
grep -rn "SELECT \*\|findAll()\|find({})" ./src | grep -v "test\|migration" | head -10

# Synchronous file operations in async code (Node.js)
grep -rn "readFileSync\|writeFileSync\|existsSync\|mkdirSync" ./src | \
  grep -v "test\|config\|setup\|init\|bin/" | head -10

# Missing response size limits
grep -rn "res\.json\|res\.send\|jsonify\|JsonResponse" ./src | \
  grep -v "test\|limit\|paginate\|slice" | head -20
```

---

## 15. Dependency Graph Health

### What to Look For

- [ ] Circular dependencies between modules (creates maintenance nightmare)
- [ ] Hub modules (depended on by everything — risky to change)
- [ ] Orphan modules (depended on by nothing — potential dead code)
- [ ] Deep dependency chains (fragile — breakage cascades)

```bash
# Circular dependency detection
npx madge --circular ./src 2>/dev/null

# Find hub modules (most imported)
grep -rh "from '.*'" ./src --include="*.ts" | \
  grep -v "node_modules" | sort | uniq -c | sort -rn | head -20

# Find orphan modules (never imported)
find ./src -name "*.ts" | while read file; do
  basename=$(basename "$file" .ts)
  count=$(grep -rl "$basename" ./src | wc -l)
  if [ "$count" -le 1 ]; then echo "ORPHAN: $file"; fi
done 2>/dev/null | head -20

# Visualize dependency graph (generates SVG)
npx madge --image ./dependency-graph.svg ./src 2>/dev/null
```
