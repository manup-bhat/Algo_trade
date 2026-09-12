# Technical Debt Assessment

Technical debt is the cost of rework caused by choosing an easier or faster solution now
instead of a better approach that would take longer.

Unlike a financial debt, technical debt is invisible in most team meetings — until it
suddenly manifests as a production incident, a failed feature, or a resignation.

> "Ward Cunningham's original debt metaphor was about code that made sense quickly but
> needed to be refined later. The problem is that most teams take on debt without intending to."
> — Martin Fowler

---

## The Technical Debt Quadrant

Martin Fowler's quadrant classifies debt on two axes:

```
                 RECKLESS                 PRUDENT
             ┌─────────────────┬──────────────────────────┐
DELIBERATE   │ "We don't have  │ "We must ship now and   │
             │ time for design"│ will deal with it later" │
             ├─────────────────┼──────────────────────────┤
INADVERTENT  │ "What's         │ "Now we know how we      │
             │ layering?"      │ should have done it"     │
             └─────────────────┴──────────────────────────┘
```

| Quadrant | Meaning | Action |
|---------|---------|--------|
| Reckless / Deliberate | Team knowingly skipped design ("no time") | Highest priority to address — team needs practices |
| Reckless / Inadvertent | Team didn't know better | Address; invest in skill-building |
| Prudent / Deliberate | Conscious tradeoff with payback plan | Track and schedule the payback |
| Prudent / Inadvertent | Learned better after the fact | Normal; address in refactoring pass |

**The audit's job**: Identify which quadrant each item of debt falls into, because the response differs.

---

## Identifying Technical Debt in the Codebase

### Signal 1: High-Churn Files

Files that are edited frequently accumulate bugs and debt disproportionately.

```bash
# Find the 20 most frequently changed files in the last 6 months
git log --since="6 months ago" --name-only --pretty=format: | \
  grep -v "^$" | sort | uniq -c | sort -rn | head -20
```

**Why it matters**: High-churn files are often "hot spots" — both difficult to work in and
risky to change. Paying down debt in these files has outsized ROI.

### Signal 2: High Complexity in High-Churn Files

The combination of high complexity AND high churn is where most production bugs originate
(Tornhill & Borg, 2022 study cited by Martin Fowler: 15× higher defect density in complex,
frequently-changed code compared to clean, frequently-changed code).

```bash
# Measure cyclomatic complexity (adapt for your language/tool)
# JavaScript/TypeScript:
npx eslint --rule '{"complexity": ["error", 10]}' ./src

# Python:
radon cc ./src -a -s  # pip install radon

# Java:
# CheckStyle complexity metric, or SonarQube

# Go:
gocyclo -over 10 ./...  # go install github.com/fzipp/gocyclo/...

# Generic: long functions are a proxy for complexity
find ./src -name "*.py" | xargs awk '/^def /{count=0; fn=$0} {count++} /^def |^class /{if(count>50) print FILENAME": "fn" ("count" lines)"}' 2>/dev/null
```

### Signal 3: TODO and FIXME Comments

These are known debt that the team acknowledged but didn't address.

```bash
# Count and categorize TODOs
grep -rn "TODO\|FIXME\|HACK\|XXX\|DEBT\|WORKAROUND" ./src | \
  grep -v "test\|spec\|node_modules" | wc -l

# See the actual comments
grep -rn "TODO\|FIXME\|HACK\|XXX" ./src | \
  grep -v "test\|spec\|node_modules" | head -30
```

### Signal 4: Test Coverage Gaps

Uncovered code is technical debt because:
- It can't be refactored safely
- Bugs in it go undetected until production
- Future developers can't verify their changes

```bash
# Get coverage report with untested files
# Node:   npm test -- --coverage --coverageReporters=text
# Python: pytest --cov=./src --cov-report=term-missing
# Go:     go test ./... -cover
# Java:   mvn test; look at target/site/jacoco/index.html
```

### Signal 5: Duplicated Logic

```bash
# Find potential code duplication
# JavaScript/TypeScript: jscpd
npx jscpd ./src --min-lines 10 --min-tokens 70

# Python: pylint --disable=all --enable=duplicate-code ./src

# General: look for repeated function names or identical blocks
grep -rn "def \|function \|func " ./src | \
  awk -F'(' '{print $1}' | sort | uniq -d | head -20
```

### Signal 6: Dependency Age and Unused Dependencies

```bash
# Check for very old, never-updated dependencies
npm outdated           # Node.js
pip list --outdated    # Python

# Check for unused dependencies
npx depcheck           # Node.js
pip-autoremove --list  # Python (approximate)
```

---

## Technical Debt Register

Create a debt register — a living document that tracks known debt items.
This transforms invisible debt into managed debt.

```markdown
| # | Description | Location | Quadrant | Impact | Effort | Priority |
|---|-------------|----------|----------|--------|--------|----------|
| 1 | Auth logic duplicated in 4 handlers | src/handlers/* | Inadvertent/Reckless | High | Medium | P1 |
| 2 | Order service is 800 lines, does too much | src/services/OrderService | Inadvertent/Prudent | Medium | High | P2 |
| 3 | No integration tests for payment flow | tests/ | Deliberate/Reckless | High | Medium | P1 |
| 4 | Config hardcoded in 12 places | src/*, config/ | Inadvertent/Reckless | Medium | Low | P2 |
| 5 | 6 TODO comments in user module | src/users/ | Deliberate/Prudent | Low | Low | P3 |
```

**Fields**:
- **Quadrant**: Which of the four quadrant categories (Reckless/Deliberate, Prudent/Inadvertent, etc.)
- **Impact**: What happens if this debt is NOT paid? (High/Medium/Low)
- **Effort**: How hard is it to fix? (Low = hours, Medium = days, High = weeks)
- **Priority**: P1 = next sprint, P2 = next quarter, P3 = when touching the area

---

## Debt Quantification

When communicating debt to non-technical stakeholders:

### Time-Based Cost Estimate

For each debt item, estimate:
- **Maintenance overhead per sprint**: How much extra time does this debt add each sprint? (Hours/sprint)
- **Bug probability multiplier**: Does this area produce bugs 2× more often than average?
- **Onboarding cost**: How long does it take a new team member to understand this area?

```
Total debt cost per year = 
  Σ (maintenance_hours_per_sprint × sprints_per_year) +
  Σ (incident_hours × incidents_per_year_caused_by_debt) +
  new_developer_ramp_up_hours × developer_turnover
```

### The Martin Fowler ROI Argument

> "Is High Quality Software Worth the Cost?" — Martin Fowler (2019)
> 
> For internal code quality: high-quality code enables teams to add features faster within
> a few weeks of starting, and continues to accelerate indefinitely. Low-quality code starts
> faster but slows down within weeks and never recovers.

Use this framing in stakeholder communication: debt reduction is not a cost — it is investment
in future velocity.

---

## Debt Prioritization Formula

When you have many debt items, prioritize by:

```
Debt Priority Score = (Impact × 3) + (Churn × 2) + (Complexity × 1) - (Effort × 1)

Where:
  Impact  = business impact if unaddressed: Low=1, Medium=2, High=3
  Churn   = how often the file is changed: Low=1, Medium=2, High=3
  Complexity = code complexity: Low=1, Medium=2, High=3
  Effort  = fix difficulty: Low=1, Medium=2, High=3
```

High-churn + high-complexity areas get the most ROI from debt reduction.
Low-churn + low-complexity areas can wait — the cost of debt there is low.

---

## Extended Debt Categories (2026)

### Duplication Debt

**Definition**: The ongoing maintenance cost of having the same logic in multiple places.

**How it accumulates**:
- Copy-paste during time pressure → diverging copies → bugs fixed in one but not others
- New developers don't know canonical version exists → create another copy
- Each copy requires its own tests, its own bug fixes, its own documentation

**Measurement**:
```
Duplication Debt Cost = 
  (number of copies - 1) × avg_change_frequency × avg_change_time_per_copy
```

**Example**: Validation logic copied in 4 endpoints. Each change requires updating all 4.
If changed once/sprint, and each update takes 30 minutes: 3 × 26 × 0.5h = 39 hours/year of pure waste.

**Detection**: See [duplicate-waste-analysis.md](./duplicate-waste-analysis.md) for tools.

---

### Principle Debt

**Definition**: The accumulated cost of violating SOLID/DRY/KISS/YAGNI principles.

**How it manifests**:
- **SRP debt**: Every feature addition requires touching 5+ files (shotgun surgery)
- **OCP debt**: Every new type/variant requires modifying a growing switch statement
- **DIP debt**: Every feature is untestable without real infrastructure
- **DRY debt**: Same bug appears repeatedly in different copies of same logic
- **KISS debt**: Simple changes take days because developers can't understand the over-engineered code

**Measurement**:
```
Principle Debt Cost =
  time_to_make_simple_change_now / time_it_would_take_in_clean_code

If ratio > 3×: significant principle debt
If ratio > 5×: critical — team velocity will continue to degrade
```

**Detection**: See [reusability-principles.md](./reusability-principles.md) for assessment method.

---

### Workflow Debt

**Definition**: Incomplete error handling, missing edge cases, and gaps in data flow that
cause production incidents.

**How it accumulates**:
- Happy path shipped under time pressure → error paths never added
- External services assumed to always be available → no timeout/fallback
- Operations assumed to be atomic → no transaction boundaries
- Operations assumed to succeed → no retry/compensation logic

**Measurement**:
```
Workflow Debt Cost =
  (incidents_per_month × avg_incident_resolution_hours × engineer_cost_per_hour)
  + (customer_impact_per_incident × incidents_per_month)
```

**Detection**: See [workflow-analysis.md](./workflow-analysis.md) for tracing methodology.

---

### AI-Generated Debt (2026)

**Definition**: Low-quality code produced by AI assistants that passed review because it
"looked correct" at first glance but contains subtle issues.

**Characteristics of AI-generated debt**:
- Code that appears correct but uses non-existent API methods (hallucinations)
- Code that follows different conventions than the rest of the codebase
- Over-commented obvious operations ("// increment the counter")
- Tests that always pass regardless of implementation (not actually testing anything)
- Security anti-patterns (AI doesn't understand auth context)
- Copy-paste from training data that doesn't fit this specific application

**How it accumulates**:
- Developers accept AI suggestions without thorough review
- AI generates code faster than humans can review properly
- Subtle bugs in AI code don't surface until edge cases hit production
- AI doesn't understand business context — generates technically valid but semantically wrong code

**Measurement**:
```
AI Debt Indicators =
  hallucinated_imports_count +
  inconsistent_patterns_count +
  tests_that_never_fail_count +
  functions_that_partially_match_requirements_count
```

**Mitigation strategy**:
1. Require automated static analysis on ALL AI-generated code
2. Run `tsc --noEmit` / type checker to catch hallucinated APIs immediately
3. Require meaningful test assertions (not just "expect(true).toBe(true)")
4. Review AI code for business logic correctness, not just syntax

---

## Debt Interest Rate Estimation

Different types of debt accrue interest at different rates:

| Debt Type | Interest Rate | Explanation |
|-----------|--------------|-------------|
| Security debt | Very High | Exploit probability increases with time; regulatory penalties grow |
| Duplication debt | High | Every feature change multiplied by copy count |
| Principle debt (SRP/DIP) | High | Compounds with each new feature — progressively harder to change |
| Workflow debt | Medium-High | Each missing error path is a future incident; cost is probabilistic |
| AI-generated debt | Medium | Increases as more code builds on top of incorrect assumptions |
| Test coverage debt | Medium | Refactoring becomes impossible without tests — locks in other debt |
| Documentation debt | Low | Slows onboarding but doesn't cause incidents directly |
| Naming/style debt | Very Low | Cognitive friction but rarely causes bugs |

---

## Debt Paydown Strategy

### The 20% Rule

Allocate **minimum 20% of sprint capacity** to debt reduction. Research shows:
- Teams with < 10% debt allocation see accelerating velocity decay
- Teams with 20-30% debt allocation maintain stable or improving velocity
- Teams with > 30% debt allocation see rapid quality improvement but slower feature delivery

### Boy Scout Rule (Continuous)

> "Always leave the code cleaner than you found it."

Every PR should leave touched files slightly better:
- Rename one confusing variable
- Extract one duplicated block
- Add one missing null check
- Remove one dead code block

This compounds over time without requiring dedicated "refactoring sprints."

### Hotspot-Focused Debt Reduction

Focus debt reduction effort on files that are:
1. **High churn** (changed frequently — maximum ROI)
2. **High complexity** (difficult to work in — maximum time savings)
3. **High defect density** (repeatedly causing bugs — maximum quality improvement)

```bash
# Find debt reduction priority files (intersection of churn + complexity)
git log --since="6 months ago" --name-only --pretty=format: | \
  sort | uniq -c | sort -rn | head -20
# Cross-reference with complexity scores from radon/eslint
```
