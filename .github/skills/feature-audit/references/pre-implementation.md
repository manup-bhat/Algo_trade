# Phase 1: Discovery & Pre-Implementation Research

Before writing one line of code, a senior developer performs a thorough audit of the existing
feature, the codebase, the users, and all known issues. Rushing past this phase is the #1 cause
of features that break things, miss edge cases, or require immediate rewrites.

---

## Step 1: Read the Feature End-to-End

Trace the complete execution path of the feature from user-facing trigger to data layer and back.

### Starting Points

Find where the feature begins:
- **UI**: Which component, page, route, or button initiates the feature?
- **API**: Which endpoint is called? What is the HTTP verb and path?
- **Event**: Is there a message queue, webhook, cron job, or event listener?
- **CLI**: Is there a command that triggers this?

### Tracing Downward

Follow every call until you reach the data layer:
```
User action
  → Router / URL handler
    → Controller / Request handler
      → Middleware (auth, validation, logging)
        → Service / Business logic
          → Repository / Data access
            → Database / External API / File system
```

Take notes on every file touched in this chain. This is your impact surface.

### Tools for Tracing

```bash
# Find all usages of a function/class/symbol
grep -rn "functionName\|ClassName" ./src --include="*.js" --include="*.ts" --include="*.py"

# Find files related to a feature by name
find . -name "*feature-name*" -not -path "*/node_modules/*"

# Find all imports of a module
grep -rn "from.*feature-module\|require.*feature-module" ./src

# Find all API routes (example for Express.js)
grep -rn "router\.\(get\|post\|put\|delete\|patch\)" ./src/routes
```

---

## Step 2: Git History Audit

Understand how the feature evolved. History reveals intent, past bugs, and risky areas.

```bash
# Full commit history for a file (follows renames)
git log --oneline --follow -- path/to/file.ts

# See what changed in each commit for a file
git log -p -- path/to/file.ts

# Find commits related to the feature by keyword
git log --oneline --grep="login\|auth\|authentication" --all

# See who wrote which line and when (blame)
git blame path/to/file.ts

# Find when a specific line was introduced
git log -S "specific code string" --oneline

# See what changed between two versions
git diff HEAD~10..HEAD -- path/to/feature/

# Find all branches touching this file
git log --all --oneline -- path/to/file.ts
```

### What to Look For in History

- **Frequent changes**: Files changed many times = complex or buggy area. Treat carefully.
- **Large rewrites**: Suggests the original design was wrong. Understand why.
- **Revert commits**: The feature was broken badly enough to roll back. What happened?
- **Merge conflicts**: Areas where multiple people work = coordination required.
- **Recent changes**: Something changed in the last sprint? That's often where bugs live.

---

## Step 3: Find All Existing Issues

Never start work without knowing what's already broken or noted.

### In the Codebase

```bash
# Find all developer-noted problems
grep -rn "TODO\|FIXME\|HACK\|XXX\|BUG\|KLUDGE\|TEMP\|deprecated" \
  --include="*.js" --include="*.ts" --include="*.py" --include="*.java" \
  ./src | grep -i "feature-name\|related-term"

# Find all commented-out code (often hiding old bugs or workarounds)
grep -rn "^[[:space:]]*//" ./src --include="*.ts" | head -40

# Find hardcoded values that should be configurable
grep -rn "\"http://localhost\|hardcoded-value\|magic-number" ./src
```

### In Issue Trackers

Search your GitHub Issues / Jira / Linear for:
- The feature name and related terms
- `bug` label on feature-related issues
- `wontfix` or `known-issue` labels (these often hide critical context)
- Closed issues — sometimes bugs were "fixed" but the fix was incomplete

---

## Step 4: Understand the User Journey

Developers who skip this write technically correct code that fails users. Map the journey first.

### User Journey Mapping

For the feature, write out every step:
```
1. User arrives at [entry point] — what do they see?
2. User performs [first action] — what feedback do they get?
3. System processes [what?] — how long does it take?
4. User sees [result] — is it clear what happened?
5. What if the operation fails? — what does the user see?
6. What if the user is offline? — graceful degradation or broken?
7. What if the data is empty? — empty state or blank screen?
8. What if the user does it twice? — idempotent? Error? Duplicate?
```

### Questions Every Developer Must Answer Before Writing Code

| Question | Why It Matters |
|----------|---------------|
| Who uses this feature? | Different user types may have different permissions and journeys |
| How often is it used? | High-traffic = needs performance and resilience; low-traffic = correctness first |
| What is the critical path? | The one thing that must never fail |
| What happens on partial failure? | DB write succeeds but email fails — what state is the system in? |
| What data does this feature touch? | PII? Financial? Medical? → drives security and compliance requirements |
| Is there a race condition? | Two users simultaneously doing this — what happens? |
| What does an empty result look like? | Table with 0 rows, API returning `[]`, first-time user with no data |
| What is the timeout behavior? | If a dependency is slow, does the feature hang or degrade gracefully? |
| Are there feature flags? | Is this behind a flag? Does the flag have a fallback state? |
| What are the known limitations? | Every feature has them — find them before users do |

---

## Step 5: Assess Existing Tests

Before adding tests, understand what exists.

```bash
# Find all test files related to the feature
find . -name "*.test.*" -o -name "*.spec.*" -o -name "*_test.*" | \
  xargs grep -l "feature-name\|FeatureClass\|feature_function" 2>/dev/null

# Check test coverage for specific files (if coverage reports exist)
# Jest:
npx jest --coverage --collectCoverageFrom="src/feature/**"
# pytest:
pytest --cov=src/feature tests/
```

### Evaluate Existing Tests

Ask for each test file:
- Does it test behavior or implementation? (behavior = good; implementation = brittle)
- Are the tests passing? (Run them — don't assume)
- Do the tests cover edge cases or only the happy path?
- Are there any tests marked `skip`, `pending`, or `xit`? (Red flags)
- When were tests last updated? (Old tests on new code = tests lying to you)

---

## Step 6: Review Existing Documentation

Documentation that is out of date is worse than no documentation — it actively misleads.

Check:
- **README**: Does the feature description match what the code actually does?
- **API docs** (Swagger/OpenAPI, Postman): Are all parameters, responses, and error codes documented? Accurate?
- **Inline comments**: Do `@param`, `@returns`, or docstrings match the actual function signature?
- **Architecture docs**: If a design doc exists, does the implementation follow it?
- **Changelog**: Is the feature's history documented for users?

---

## Discovery Output: Fill This In Before Phase 2

After completing discovery, you should be able to answer all of these:

```
Feature name: ______________________
Entry points (UI/API/event): ______________________
Files involved (trace): ______________________
Known TODOs/FIXMEs in this area: ______________________
Known issues (from tracker): ______________________
User journey (steps): ______________________
Critical path (the one thing that must work): ______________________
Edge cases identified: ______________________
Existing tests (coverage level): ______________________
Documentation accuracy: ______________________
High-risk areas (frequent changes, recent rewrites): ______________________
Dependencies on other features: ______________________
```

Only when all fields are filled should you move to Phase 2: Impact Analysis.

---

## Bug Investigation: Feature Forensics

When the task is debugging rather than building, use these forensic techniques
BEFORE diving into the code:

### Stakeholder Context

| Question | Why It Matters |
|----------|---------------|
| Who reported this? | Helps understand the context and environment |
| What's the business impact? | Determines urgency and depth of investigation |
| When did it start? | Narrows the search window (recent change? always?) |
| How many users affected? | Determines if it's a specific-case or systemic issue |
| Is there a workaround? | Reduces urgency pressure, allows thorough investigation |

### Git Forensics — Recent Changes

```bash
# What changed recently in the affected area?
git log --oneline --since="2 weeks ago" -- <affected-file-or-directory>

# Who modified this file? What did they change?
git blame <file> | grep -B 2 -A 2 <affected-line-number>

# What was the file like BEFORE the last change?
git show HEAD~1:<file>

# Find the commit that introduced a specific string/pattern
git log -S "<suspicious-string>" --oneline

# Find commits that changed a specific function
git log -L :<function-name>:<file>
```

### Reproduction Recipe Template

```markdown
## Bug Reproduction

**Reporter**: [who]
**Impact**: [Critical/High/Medium/Low] — [N users affected]
**Environment**: [OS, browser, version, etc.]

**Preconditions**:
- [Account state: new user? admin? specific plan?]
- [Data state: empty? large dataset? specific records?]
- [Config: specific feature flags? environment variables?]

**Steps to Reproduce**:
1. [Exact step]
2. [Exact step]
3. [Exact step]

**Expected Result**: [What should happen]
**Actual Result**: [What actually happens]
**Frequency**: [Always / Sometimes (~X%) / One-time]

**What I've Already Tried**:
- [Approach 1: result]
- [Approach 2: result]
```

### Investigation Scope Boundaries

Define what IS and IS NOT the problem area to avoid wasting time:

```markdown
## Investigation Scope

**Definitely IN scope** (the bug is likely here):
- [File/module 1 — because [reason]]
- [File/module 2 — because [reason]]

**Definitely OUT of scope** (the bug is NOT here):
- [File/module 3 — because this hasn't changed / works for other users]
- [File/module 4 — because the output at this point is correct]

**Uncertain** (need to investigate):
- [File/module 5 — need to verify output is correct here]
```

### When the Bug Can't Be Reproduced Locally

| Prod-only factor | How to investigate |
|-----------------|-------------------|
| Data volume | Request a subset of prod data (sanitized) |
| Concurrency/load | Use load testing tool locally (k6, ab, locust) |
| Timing/race conditions | Add artificial delays or use thread-unsafe test mode |
| Environment-specific config | Compare all env vars between local and prod |
| External service behavior | Check service logs/dashboards for errors at the time |
| User-specific state | Impersonate user or replicate their exact data state |
| Caching | Clear all caches; or replicate the exact cache state |

---

## Discovery for Different Task Types

### If You're ADDING a New Feature

Focus on:
- What similar features exist? How are they implemented?
- What patterns does the codebase use for this type of thing?
- Where should this code live? (Which directory, which module?)
- What shared utilities can you reuse?

### If You're FIXING a Bug

Focus on:
- Can I reproduce it? (If not, I can't fix it properly)
- When did it start? (git log, git bisect)
- What changed recently? (git blame, recent PRs)
- What are the exact conditions that trigger it?

### If You're IMPROVING/REFACTORING

Focus on:
- What's the current behavior? (Don't accidentally change it)
- Who/what depends on this code? (Impact analysis critical)
- What tests exist? (They're your safety net for refactoring)
- Is there a reason it's written this way? (Check git history/comments before assuming it's "bad")
