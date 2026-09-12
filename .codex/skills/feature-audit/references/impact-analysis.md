# Phase 2: Impact Analysis — Every File and Layer That Must Change

Impact analysis is how senior developers avoid "I thought I only changed one thing" incidents.
Before writing code, map every file, layer, and system that will be affected.

---

## The Impact Layers

Modern applications have distinct layers. Every feature change touches at least two. Trace each one.

```
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 7: Documentation & Changelog                             │
│  LAYER 6: Tests (unit, integration, E2E, fixtures, mocks)       │
│  LAYER 5: Configuration (env vars, feature flags, app config)   │
│  LAYER 4: Infrastructure (DB schemas, migrations, queues, cache)│
│  LAYER 3: Data Access (repositories, ORMs, raw queries)         │
│  LAYER 2: Business Logic (services, domain models, events)      │
│  LAYER 1: Interface (API routes, controllers, UI components)    │
└─────────────────────────────────────────────────────────────────┘
```

Trace from the entry point DOWN to infrastructure, then check which HORIZONTAL services
are touched (notifications, logging, analytics, audit trails, caches).

---

## Layer-by-Layer Audit

### Layer 1: Interface (UI / API)

**Web / SPA Frontend**
- [ ] Which component renders the feature? (`components/`, `pages/`, `views/`)
- [ ] Which parent components pass props to this one?
- [ ] Which routes lead to this feature? (`router.js`, `routes.py`, `routes/`)
- [ ] Is there any client-side state management touched? (Redux store, context, Zustand, Pinia)
- [ ] Are there any form inputs that need validation? (client-side and server-side)
- [ ] Are there any CSS/style files specific to this feature?
- [ ] Is the feature accessible? (ARIA, semantic HTML, keyboard navigation)

**Backend API**
- [ ] Which controller handles the request? (`controllers/`, `handlers/`, `views.py`)
- [ ] What middleware applies? (auth, rate limiting, input validation, logging)
- [ ] What is the request/response schema? (serializers, DTOs, Pydantic models, Zod schemas)
- [ ] Is the response paginated? How?
- [ ] What HTTP status codes does this endpoint return? Are they all correct?
- [ ] Is this endpoint documented in OpenAPI/Swagger/Postman?

**Search command**:
```bash
# Find all routes (adapt pattern for your framework)
grep -rn "@app.route\|router.get\|router.post\|app.get\|app.post\|@GetMapping\|@PostMapping" ./src
grep -rn "path.*feature-name\|url.*feature-name" ./src
```

---

### Layer 2: Business Logic (Services / Domain)

- [ ] Which service class or module contains the core logic?
- [ ] What domain models / entities are involved?
- [ ] Are there any domain events published or consumed? (`events/`, `pubsub/`, `messaging/`)
- [ ] Are there any background jobs, queues, or async tasks involved? (`workers/`, `tasks/`, `jobs/`)
- [ ] Is there any caching layer (Redis, memcache, in-memory) that must be invalidated on change?
- [ ] Are there any rate limits or throttling rules that apply?
- [ ] Is the business logic covered by unit tests that will need updating?

```bash
# Find service/domain files
find ./src -name "*Service*" -o -name "*service*" -o -name "*Domain*" | \
  xargs grep -l "FeatureName\|feature_function" 2>/dev/null
```

---

### Layer 3: Data Access (Repository / ORM / Raw SQL)

- [ ] Which repository, DAO, or query file handles data for this feature?
- [ ] What tables, collections, or indexes are read/written?
- [ ] Are there N+1 query risks? (Loading a collection then querying each item individually)
- [ ] Are queries parameterized? (No raw string interpolation into SQL)
- [ ] Are there indexes for the query patterns used? (Will it scale?)
- [ ] Are there transactions needed? (Multi-table writes should be atomic)

```bash
# Find all database queries for a feature
grep -rn "SELECT\|INSERT\|UPDATE\|DELETE\|findBy\|findAll\|query\|execute" ./src | \
  grep -i "feature_table\|FeatureModel"
```

---

### Layer 4: Infrastructure (DB Schema / Migrations / Queues / Cache)

**Database**
- [ ] Does the schema need to change? (new columns, new tables, indexes, constraints)
- [ ] Is a migration script required?
- [ ] Is the migration **backwards compatible**? (Can old and new code run simultaneously during deploy?)
- [ ] Does seed data / test fixtures need updating?
- [ ] Are there any database-level constraints, triggers, or stored procedures to update?

**Queues / Events**
- [ ] Are message queue schemas changing? (Producers and consumers must stay in sync)
- [ ] Do event listeners need updating?

**Cache**
- [ ] Which cache keys relate to this feature?
- [ ] On what write operations should caches be invalidated?
- [ ] Is the TTL appropriate for the feature's data freshness requirements?

```bash
# Find migration files
find . -name "*migration*" -o -name "*migrate*" | sort -r | head -20
# Find schema definition files
find . -name "schema.*" -o -name "models.*" -o -name "*.prisma" | head -20
```

---

### Layer 5: Configuration (Env Vars / Feature Flags / App Config)

- [ ] Does the feature require new environment variables? (`DATABASE_URL`, `API_KEY`, `TIMEOUT_MS`)
- [ ] Is `.env.example` updated so other developers know what's needed?
- [ ] Is the feature behind a feature flag? Is the flag documented?
- [ ] Do deployment scripts or infrastructure-as-code files need updating? (`docker-compose.yml`, `k8s/`, `terraform/`)
- [ ] Are there per-environment configurations that differ? (`config/production.yaml` vs `config/development.yaml`)

```bash
# Find all env var usages
grep -rn "process.env\.\|os.getenv\|System.getenv\|ENV\[" ./src | \
  grep -v "node_modules"
```

---

### Layer 6: Tests

When the feature changes, tests at every level must be audited and updated.

**Identify all tests that need attention**:

```bash
# Find all test files that reference this feature
find . \( -name "*.test.ts" -o -name "*.spec.js" -o -name "*_test.py" -o -name "Test*.java" \) \
  | xargs grep -l "FeatureName\|featureFunction\|feature_route" 2>/dev/null

# Find test fixtures / mocks / factories related to the feature
find . -path "*/fixtures/*" -o -path "*/mocks/*" -o -path "*/factories/*" | \
  xargs grep -l "feature" 2>/dev/null
```

**Categorize tests found**:

| Test Type | What to Check |
|-----------|--------------|
| Unit tests | Do assertions still match expected behavior after your change? |
| Integration tests | Do tests still set up the correct dependencies / test data? |
| E2E tests | Do selectors still find the correct UI elements? Do user journeys still complete? |
| Contract tests | Do request/response schemas match what consumers expect? |
| Snapshot tests | Do snapshots need regenerating? (Deliberately, not automatically) |
| Fixture / seed data | Does it reflect real-world shapes of data for the feature? |

---

### Layer 7: Documentation

Documentation that lies is worse than no documentation.

- [ ] **README**: Does it describe the feature correctly? Do setup steps still work?
- [ ] **API documentation** (OpenAPI/Swagger, Postman collections): All endpoints, params, response schemas, error codes accurate?
- [ ] **Inline docstrings / JSDoc / JavaDoc**: Function signatures, param types, return values accurate?
- [ ] **Architecture / design docs**: Does the implementation match the documented design?
- [ ] **CHANGELOG**: Is there a user-visible entry for this change?
- [ ] **Runbooks / ops docs**: If this feature has incident runbooks, are they still accurate?

---

## Horizontal Cross-Cutting Concerns

These touch every layer and are easy to forget:

| Concern | Questions |
|---------|-----------|
| **Authentication** | Does the new/changed functionality correctly enforce auth? |
| **Authorization** | Does it check permissions server-side, not just client-side? |
| **Logging** | Are meaningful log messages added? Are sensitive fields excluded? |
| **Audit trail** | For sensitive actions, is there an immutable audit record? |
| **Metrics / Observability** | Are counters, histograms, or traces updated for the new behavior? |
| **Error tracking** | Will errors from this feature appear in your error tracker (Sentry, etc.)? |
| **Internationalization (i18n)** | Are new user-visible strings added to translation files? |
| **Analytics** | If the feature is tracked for product analytics, are new events fired? |
| **Rate limiting** | Does the feature need rate limits? Are existing limits still appropriate? |
| **Backwards compatibility** | Can old clients or API consumers still work while you deploy? |

---

## Dependency Graph Tracing

When a **shared** utility, base class, or library function changes, the blast radius is larger.

```bash
# Find all files that import/require a module
grep -rn "from.*'./shared/utils'\|require.*shared/utils" ./src

# In TypeScript: find all usages of an exported symbol
# (Use VS Code "Find All References" or TypeScript language server)

# Find circular dependencies (Node.js)
npx madge --circular ./src
```

**Rule**: If a change touches a shared/common module, **every consumer** is in scope for testing.

---

## Integration Points With External Systems

- [ ] Does this feature call any external APIs? Will the API contract still be satisfied?
- [ ] Does this feature produce data consumed by another service? (Microservices, event-driven)
- [ ] Does this feature consume data from another service? (Will changes break the contract?)
- [ ] Does this feature integrate with third-party services? (Stripe, SendGrid, Twilio, etc.)
  - Are there webhook handlers that may need updating?
  - Are there SDK version changes that affect behavior?

---

## Impact Summary Template

Fill this out after completing the layer-by-layer audit. Share it in your PR description.

```
## Impact Analysis for: [Feature Name]

### Files Changed (core)
- src/controllers/FeatureController.ts — [reason]
- src/services/FeatureService.ts — [reason]
- src/models/Feature.ts — [reason]

### Files Changed (supporting)
- src/routes/index.ts — [added/updated route]
- db/migrations/0042_add_feature_column.sql — [schema change]
- .env.example — [new env var: FEATURE_TIMEOUT_MS]

### Tests Updated
- tests/unit/FeatureService.test.ts — [updated for new logic]
- tests/integration/FeatureController.test.ts — [new test cases]
- tests/e2e/feature-journey.spec.ts — [updated selector]

### Documentation Updated
- README.md — [updated setup section]
- docs/api/feature.yaml — [new endpoint documented]
- CHANGELOG.md — [user-visible change noted]

### Breaking Changes
- [ ] None
- [ ] API response shape changed (consumers: [list them])
- [ ] DB schema change (migration required before deploy)
- [ ] Env var added (must be set in production before deploy)

### Rollout Risk: Low / Medium / High
[Reason for risk assessment]
```
