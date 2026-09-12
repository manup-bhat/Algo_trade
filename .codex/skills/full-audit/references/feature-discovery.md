# Feature Discovery — Map Every Feature in the Codebase

> **Step 1 of full-audit.** Before auditing anything, you must know what exists.
> A missed feature is an unaudited risk.

---

## What Is a "Feature"?

A feature is any discrete unit of functionality that a user, system, or scheduled process
can invoke. Features exist at multiple levels:

| Layer | Examples |
|-------|---------|
| **User-facing** | Login, Registration, Search, Profile edit, Checkout, Password reset |
| **API endpoints** | `POST /orders`, `GET /users/:id`, `DELETE /sessions` |
| **Admin/internal** | User management, Content moderation, Analytics dashboard, Impersonation |
| **Background jobs** | Email digests, Payment reconciliation, Data exports, Report generation |
| **Event/webhook handlers** | Stripe webhook, GitHub webhook, Slack event subscription |
| **Scheduled tasks** | Daily cleanup, Cache warming, Audit log pruning |
| **Batch processes** | Data import, Bulk updates, Nightly aggregations |
| **Integrations** | OAuth flows, External API calls, SSO, Third-party service sync |
| **System features** | Health checks, Feature flags, Config management, Migrations |

---

## Discovery Method 1 — Route/Endpoint Mapping

### Web Frameworks
```bash
# Express / Fastify / Koa (Node.js)
grep -rn "app\.\(get\|post\|put\|delete\|patch\|options\)\|router\.\(get\|post\|put\|delete\|patch\)" ./src

# Django (Python)
grep -rn "path(\|re_path(\|url(" ./src --include="urls.py"

# FastAPI / Flask (Python)
grep -rn "@app\.route\|@router\.\|@app\.get\|@app\.post\|@app\.put\|@app\.delete" ./src

# Spring Boot (Java)
grep -rn "@GetMapping\|@PostMapping\|@PutMapping\|@DeleteMapping\|@RequestMapping" ./src --include="*.java"

# Rails (Ruby)
cat config/routes.rb
grep -rn "resources\|get\|post\|put\|delete\|patch" config/routes.rb

# Laravel (PHP)
find . -name "web.php" -o -name "api.php" | xargs grep -n "Route::"
```

### REST / GraphQL
```bash
# OpenAPI spec — best single source of truth if maintained
find . -name "openapi.yaml" -o -name "openapi.json" -o -name "swagger.yaml"

# GraphQL schema
find . -name "*.graphql" -o -name "schema.graphql" | head -10

# tRPC (TypeScript)
grep -rn "createTRPCRouter\|publicProcedure\|protectedProcedure" ./src
```

---

## Discovery Method 2 — UI Page Mapping

```bash
# React / Next.js (pages router)
find ./pages -name "*.tsx" -o -name "*.jsx" -o -name "*.js" | grep -v "_app\|_document\|_error\|api/"

# Next.js App Router
find ./app -name "page.tsx" -o -name "page.jsx"

# Vue / Nuxt
find ./pages -name "*.vue" | head -40
grep -rn "path:" ./src --include="router.ts" --include="router.js" --include="routes.ts"

# Angular
grep -rn "path:" ./src --include="*.routing.ts" --include="*.module.ts"

# SvelteKit
find ./src/routes -name "+page.svelte" -o -name "+page.ts"
```

---

## Discovery Method 3 — Background Jobs and Scheduled Tasks

```bash
# Node.js (Bull, BullMQ, Agenda, node-cron)
grep -rn "new Queue\|new Worker\|addJob\|process(\|Queue(\|cron\.\|schedule(" ./src

# Python (Celery, RQ, APScheduler)
grep -rn "@app\.task\|@shared_task\|@celery\.task\|scheduler\.add_job\|cron_job" ./src

# Ruby (Sidekiq, Delayed::Job)
grep -rn "class.*Worker\|class.*Job\|perform_async\|perform_in\|cron:" ./app

# Java (Spring @Scheduled, Quartz)
grep -rn "@Scheduled\|@Component.*Job\|implements Job" ./src --include="*.java"

# Generic cron files
find . -name "crontab" -o -name "*.cron" | head -10
find . -name "Procfile" -o -name "*.Procfile"
```

---

## Discovery Method 4 — Event Handlers and Webhooks

```bash
# Event emitters / listeners
grep -rn "\.on(\|addEventListener\|EventEmitter\|pubsub\|subscribe\|@EventHandler\|@EventListener" ./src

# Webhook endpoints (look for signature verification patterns)
grep -rn "webhook\|x-hub-signature\|stripe-signature\|x-github-event" ./src --include="*.ts" --include="*.py" --include="*.rb"

# Message queue consumers
grep -rn "consumer\|subscriber\|\.consume\|receiveMessage\|SQS\|RabbitMQ\|Kafka\|NATS" ./src
```

---

## Discovery Method 5 — Admin and Internal Features

```bash
# Admin routes (often separate from public-facing)
grep -rn "admin\|internal\|management\|backoffice\|staff" ./src --include="*.ts" -l
grep -rn "isAdmin\|hasRole.*admin\|requireAdmin\|@AdminOnly" ./src

# Find admin-only middleware
grep -rn "adminMiddleware\|AdminGuard\|admin_required\|staff_member_required" ./src
```

---

## Discovery Method 6 — Configuration and Feature Flags

```bash
# Feature flags
grep -rn "featureFlag\|feature_flag\|isEnabled\|getFlag\|LaunchDarkly\|Flagsmith\|unleash" ./src

# Configuration keys (env vars)
grep -rn "process\.env\.\|os\.environ\|ENV\[" ./src | grep -v "NODE_ENV\|test" | sort -u
find . -name ".env.example" -o -name ".env.template" | xargs cat
```

---

## Discovery Method 7 — Dead Code Detection

Identify code that exists but is never called — it still represents audit surface:

```bash
# TypeScript / JavaScript (ts-unused-exports, deadcode)
npx ts-unused-exports tsconfig.json
npx unimported

# Python (vulture)
pip install vulture
vulture ./src

# General: look for exports with no imports
grep -rn "export function\|export const\|export class\|export default" ./src | wc -l
grep -rn "import.*from" ./src | wc -l
```

---

## Discovery Method 8 — Git History as Feature Map

Git log reveals features that may not be obvious from the current codebase:

```bash
# List all unique files touched in the last year
git log --since="1 year ago" --name-only --pretty=format: | sort -u | head -80

# Find areas of highest churn (most changed = most critical to audit)
git log --since="6 months ago" --format=format: --name-only | sort | uniq -c | sort -rn | head -30

# Find large additions that may represent feature introductions
git log --oneline --diff-filter=A --since="1 year ago" -- "*.ts" "*.py"

# List all contributors (helps find orphaned features with no owner)
git shortlog -sn --all --no-merges | head -20
```

---

## Feature Inventory Table Template

After discovery, record every feature here:

```markdown
## Feature Inventory

| # | Feature Name | Entry Points | Layer(s) | Owner/Team | Audit Status |
|---|-------------|-------------|---------|-----------|-------------|
| 1 | User Authentication | POST /auth/login, POST /auth/register, POST /auth/logout | API, Service, DB | Auth Team | ⬜ Pending |
| 2 | Search | GET /search, SearchPage, SearchBar component | UI, API, Service, ElasticSearch | Search Team | ⬜ Pending |
| 3 | Checkout | /checkout/*, POST /orders | UI, API, Service, Payment, DB | Commerce Team | ⬜ Pending |
| 4 | Email Notifications | EmailWorker, NotificationQueue | Background, Email Service | Platform Team | ⬜ Pending |
| 5 | Admin User Management | /admin/users/*, GET/POST/DELETE /admin/users | Admin UI, API, DB | Infra Team | ⬜ Pending |
...

Status: ⬜ Pending | 🔄 In Progress | ✅ Complete | ⏭️ Skipped (out of scope)
```

---

## Prioritizing Which Features to Audit First

Not all features carry equal risk. Prioritize by:

| Priority Signal | Reason |
|----------------|--------|
| Handles user authentication or authorization | Security impact is maximized here |
| Processes payments or financial data | Compliance + data integrity |
| Touches PII (email, address, health data) | Privacy and regulatory exposure |
| Highest traffic / most-used | Bug impact is proportional to usage |
| Highest git churn (most commits) | Churned code accumulates the most cruft |
| Recently shipped (last 30 days) | New features have the least battle-testing |
| No test coverage | Untested features hide bugs |
| Flagged by on-call or bug reports | Real signal from production |
| Customer-visible on launch path | Pre-launch critical path |

---

## Discovery Checklist

- [ ] All HTTP routes/endpoints enumerated
- [ ] All UI pages and flows listed
- [ ] Background jobs and scheduled tasks inventoried
- [ ] Event handlers and webhook consumers catalogued
- [ ] Admin and internal-only features listed separately
- [ ] Feature flags documented
- [ ] Dead code identified and noted
- [ ] Git history mined for high-churn areas
- [ ] AI-generated code identified and flagged for quality review
- [ ] Feature Inventory Table created with entry points and owners
- [ ] Features sorted by audit priority (security-critical first)
- [ ] Dependency graph mapped (which features depend on which shared modules)
- [ ] External service dependencies listed (APIs, databases, message queues)

---

## Discovery Method 9 — AI-Generated Code Identification

In the era of AI-assisted development, identify code that was likely AI-generated and
may need extra scrutiny for quality issues:

```bash
# Find commits likely made with AI assistance (common patterns)
git log --oneline --all --since="6 months ago" | \
  grep -i "copilot\|generated\|ai\|chatgpt\|claude\|autocomplete" | head -20

# Find large commits by a single author (possible bulk AI generation)
git log --since="6 months ago" --pretty=format:"%h %an %s" --shortstat | \
  grep -B 1 "insertions" | grep -B 1 "[0-9]\{3,\} insertion" | head -20

# Find files with hallucination indicators
# - Imports of packages not in package.json/requirements.txt
# - Over-commented obvious code
# - Inconsistent naming conventions within a single file
grep -rn "// [A-Z].*the\|# [A-Z].*the" ./src | \
  grep -v "TODO\|FIXME\|NOTE\|HACK" | head -20

# Find potential phantom package imports
grep -rn "^import\|^from " ./src --include="*.ts" --include="*.py" | \
  grep -v "\./\|\.\./\|@types\|node_modules" | \
  awk -F"['\"]" '{print $2}' | sort -u
# Cross-reference with package.json/requirements.txt
```

**AI-generated code audit priority**:
- Flag all likely AI-generated files for deeper review in Steps 3-6
- Verify imports actually exist in the dependency manifest
- Check test files for meaningful assertions (not `expect(true).toBe(true)`)
- Verify business logic matches actual requirements (AI may solve a slightly different problem)

---

## Discovery Method 10 — Complexity and Risk Heatmap

Before auditing, create a risk heatmap to prioritize where to focus:

```bash
# Combine churn + complexity to find highest-risk files
# Step 1: Get churn data
git log --since="6 months ago" --name-only --pretty=format: | \
  sort | uniq -c | sort -rn | head -30 > /tmp/churn.txt

# Step 2: Get complexity data (adjust tool for your language)
npx eslint --rule '{"complexity": ["warn", 1]}' ./src --format json 2>/dev/null | \
  jq '.[] | .filePath + ": " + (.messages | length | tostring)' | head -30

# Step 3: Cross-reference — files in BOTH lists are your highest-priority audit targets
```

**Risk heatmap categories**:

| Churn | Complexity | Priority |
|-------|-----------|---------|
| High | High | 🔴 Audit first — highest bug probability |
| High | Low | 🟡 Audit second — frequently changed but manageable |
| Low | High | 🟡 Audit third — complex but stable |
| Low | Low | ✅ Audit last — low risk |
