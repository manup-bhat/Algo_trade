---
name: django-to-fastapi-migration
description: "Complete Django to FastAPI migration skill. Use when: migrating Django to FastAPI, converting Django views to FastAPI routers, replacing Django ORM with SQLAlchemy/SQLModel, migrating DRF serializers to Pydantic v2, converting Django authentication to JWT/OAuth2, migrating Django middleware, replacing Celery with FastAPI BackgroundTasks, converting Django signals to event-driven patterns, migrating Django admin to SQLAdmin, incremental migration using Strangler Fig pattern, running Django and FastAPI side-by-side, zero-downtime migration, Django REST Framework to FastAPI, convert Django app to async, migrate Django to modern Python API framework, best practices 2025 2026."
argument-hint: 'Component or layer to migrate (e.g. "auth system", "all models", "views/users.py", "full migration plan")'
---

# Django to FastAPI Migration Skill

A structured, production-safe methodology for migrating Django applications to FastAPI
without breaking functionality. Uses the **Strangler Fig pattern** for incremental,
zero-downtime migration — updated for FastAPI 0.115+ / Pydantic v2 / SQLModel / PyJWT / pwdlib / Python 3.10+.

---

## Quick Reference

| Migration Area | Reference File | Key Risks |
|---------------|---------------|-----------|
| Strategy & Planning | [migration-strategy.md](./references/migration-strategy.md) | Big-bang rewrite, data loss, downtime |
| Models & ORM | [models-orm.md](./references/models-orm.md) | Schema drift, N+1 queries, missing migrations |
| Views → Routers | [views-to-routers.md](./references/views-to-routers.md) | Broken URLs, missing permissions, wrong HTTP methods |
| Authentication | [authentication.md](./references/authentication.md) | Session invalidation, password hash incompatibility |
| Middleware | [middleware-migration.md](./references/middleware-migration.md) | Missing security headers, broken request flow |
| Serializers → Pydantic | [serializers-to-pydantic.md](./references/serializers-to-pydantic.md) | Validation gaps, data leaks, missing fields |
| Signals & Tasks | [signals-tasks.md](./references/signals-tasks.md) | Lost async jobs, orphaned side-effects |
| Testing | [testing-migration.md](./references/testing-migration.md) | False confidence, untested edge cases |
| Admin & Static | [admin-static-templates.md](./references/admin-static-templates.md) | Lost admin functionality, broken uploads |
| Migration Checklist | [checklist.md](./references/checklist.md) | Single-page validation gate |

---

## When to Use This Skill

| Trigger phrase | Start here |
|---------------|-----------|
| "Migrate Django to FastAPI" | All phases (start with strategy) |
| "Convert Django views to FastAPI" | [views-to-routers.md](./references/views-to-routers.md) |
| "Replace Django ORM with SQLModel" | [models-orm.md](./references/models-orm.md) |
| "Migrate DRF serializers to Pydantic" | [serializers-to-pydantic.md](./references/serializers-to-pydantic.md) |
| "Convert Django auth to JWT" | [authentication.md](./references/authentication.md) |
| "Run Django and FastAPI together" | [migration-strategy.md](./references/migration-strategy.md) |
| "Migration plan / roadmap" | [migration-strategy.md](./references/migration-strategy.md) + [checklist.md](./references/checklist.md) |
| "Migrate Celery tasks" | [signals-tasks.md](./references/signals-tasks.md) |
| "Convert Django tests to pytest" | [testing-migration.md](./references/testing-migration.md) |

---

## Migration Philosophy

### The Strangler Fig Pattern

**NEVER do a big-bang rewrite.** Instead:

1. Mount Django inside FastAPI using `WSGIMiddleware` (or use reverse proxy)
2. Migrate one route/feature at a time to FastAPI
3. Both frameworks share the same database during transition
4. Use contract tests to verify identical behavior
5. Once all routes migrated, remove the Django mount

```python
# Coexistence: FastAPI handles new routes, Django handles legacy
from a2wsgi import WSGIMiddleware
from fastapi import FastAPI
from django.core.wsgi import get_wsgi_application

import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myproject.settings")
django.setup()

app = FastAPI()

# New FastAPI routes
@app.get("/api/v2/users/{user_id}")
async def get_user(user_id: int): ...

# Legacy Django handles everything else
django_app = get_wsgi_application()
app.mount("/", WSGIMiddleware(django_app))
```

### Core Principles

1. **Route-by-route migration** — never rewrite everything at once
2. **Contract testing** — each migrated endpoint must pass identical tests
3. **Shared database** — both frameworks read/write the same DB during transition
4. **Password compatibility** — `pwdlib` can verify Django's PBKDF2 hashes
5. **Zero-downtime** — use feature flags or reverse proxy routing to switch traffic
6. **Rollback ready** — keep Django routes active until FastAPI is proven stable

---

## 7-Phase Migration Workflow

### Phase 1 — Discovery & Inventory

Before writing any code:

1. **List all Django apps** — `INSTALLED_APPS` minus third-party
2. **Count endpoints** — parse `urls.py` files, count URL patterns
3. **Map dependencies** — which apps depend on which (signals, imports, FK relations)
4. **Identify blocking Django features**:
   - Django Admin (heavy use?) → Plan SQLAdmin replacement
   - Django Forms (server-rendered?) → Plan separate frontend or Jinja2
   - Django Channels (WebSockets?) → FastAPI has native WebSocket support
   - Celery (task queue?) → Evaluate BackgroundTasks vs Arq vs keeping Celery
5. **Prioritize** — start with stateless, low-risk endpoints (health checks, read-only APIs)

### Phase 2 — Project Scaffolding

Set up the FastAPI project structure alongside Django:

```
project/
├── django_app/              # Existing Django project (untouched initially)
│   ├── manage.py
│   ├── myproject/
│   │   ├── settings.py
│   │   ├── urls.py
│   │   └── wsgi.py
│   └── apps/
│       ├── users/
│       ├── posts/
│       └── ...
├── fastapi_app/             # New FastAPI application
│   ├── main.py              # FastAPI app + WSGIMiddleware mount
│   ├── config.py            # pydantic-settings BaseSettings
│   ├── database.py          # SQLModel engine + session
│   └── src/
│       ├── users/
│       │   ├── router.py
│       │   ├── schemas.py
│       │   ├── models.py
│       │   ├── service.py
│       │   └── dependencies.py
│       └── posts/
│           └── ...
├── tests/
│   ├── contract/            # Tests that run against BOTH Django and FastAPI
│   ├── fastapi/
│   └── django/
├── alembic/                 # Database migrations (shared with Django during transition)
│   └── versions/
├── requirements.txt
└── pyproject.toml
```

### Phase 3 — Database Layer Migration

Load [models-orm.md](./references/models-orm.md).

1. Create SQLModel table models matching Django models exactly
2. Point both Django and SQLModel at the same database
3. Use Alembic for new migrations (Django migrations still run for Django-managed tables)
4. Verify data reads are identical between Django ORM and SQLModel queries

### Phase 4 — Route Migration (One-by-One)

Load [views-to-routers.md](./references/views-to-routers.md).

For each endpoint:
1. Write a contract test that passes against the Django endpoint
2. Create the equivalent FastAPI route
3. Run the same contract test against the FastAPI endpoint
4. Switch traffic (feature flag or reverse proxy)
5. Monitor for errors
6. Remove Django route only after stability period

### Phase 5 — Authentication & Middleware

Load [authentication.md](./references/authentication.md) and [middleware-migration.md](./references/middleware-migration.md).

Critical: Migrate auth AFTER a few simple routes are proven working.

### Phase 6 — Background Tasks & Signals

Load [signals-tasks.md](./references/signals-tasks.md).

Migrate asynchronous processing and event-driven side effects.

### Phase 7 — Decommission Django

Only after ALL routes, middleware, and background tasks are migrated:

1. Remove `WSGIMiddleware` mount
2. Remove Django from `requirements.txt`
3. Remove Django app directory
4. Run full test suite
5. Deploy and monitor

---

## Django → FastAPI Concept Mapping (Quick Lookup)

| Django Concept | FastAPI Equivalent | Notes |
|---------------|-------------------|-------|
| `urls.py` + `path()` | `APIRouter` + decorators (`@router.get`) | Path params use `{param}` not `<param>` |
| `views.py` function | Path operation function | Add type hints for auto-validation |
| `ViewSet` (DRF) | `APIRouter` with CRUD functions | No magic; explicit is better |
| `Serializer` (DRF) | Pydantic `BaseModel` | Separate Input/Output models |
| `ModelSerializer` | SQLModel + Pydantic schema split | `HeroBase` / `Hero(table)` / `HeroPublic` |
| `@login_required` | `Depends(get_current_user)` | Dependency injection |
| `PermissionClass` | `Depends(require_role("admin"))` | Composable dependencies |
| `Django ORM QuerySet` | SQLModel `select()` / SQLAlchemy | Use `selectinload` for relations |
| `Django Middleware` | `@app.middleware("http")` or `BaseHTTPMiddleware` | Or use dependencies for per-route |
| `settings.py` | `pydantic-settings` `BaseSettings` | Validated at startup, `.env` support |
| `signals` (post_save) | Service-layer calls or SQLAlchemy events | Explicit > implicit |
| `Celery task` | `BackgroundTasks` (simple) or Arq/SAQ (distributed) | Keep Celery if complex |
| `Django Admin` | SQLAdmin / FastAPI-Admin | Less magic, more control |
| `manage.py command` | CLI script or `lifespan` event | Use `typer` for CLI |
| `Form` | Pydantic model + `Form(...)` parameter | Or separate frontend |
| `FileField` / `ImageField` | `UploadFile` | Magic-byte MIME validation |
| `TestCase` + `self.client` | `pytest` + `httpx.AsyncClient` | Use `ASGITransport` |
| `django.test.override_settings` | `app.dependency_overrides` | Per-dependency mocking |
| `DATABASES` config | `create_engine(DATABASE_URL)` | Connection string |
| `STATIC_URL` / `staticfiles` | `app.mount("/static", StaticFiles(...))` | Single mount point |
| `django.contrib.auth.models.User` | Custom `User` SQLModel + `pwdlib` | Full control over schema |

---

## 2025/2026 Technology Stack

| Layer | Recommended | Why |
|-------|-------------|-----|
| Framework | FastAPI 0.115+ | Latest stable, Python 3.10+ |
| Validation | Pydantic v2 | 5-50× faster than v1 |
| ORM | SQLModel | Built on SQLAlchemy, Pydantic-native |
| Migrations | Alembic | Industry standard for SQLAlchemy |
| Auth | PyJWT + pwdlib[argon2] | FastAPI official recommendation |
| Settings | pydantic-settings | Type-safe, `.env` support |
| Testing | pytest + httpx + ASGITransport | Async-native, dependency_overrides |
| Task Queue | Arq (or keep Celery) | Redis-backed, async-native |
| Admin | SQLAdmin | Async, SQLAlchemy-native |
| Linting | Ruff | 10-100× faster than flake8+isort+black |

---

## Critical Migration Gotchas

### 1. Password Hash Compatibility
```python
# pwdlib can verify Django's default PBKDF2 hashes!
# Configure pwdlib to support legacy Django hashes:
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.django import DjangoHasher  # reads PBKDF2

password_hash = PasswordHash((DjangoHasher(), Argon2Hasher()))
# Verifies old Django hashes, new passwords get Argon2
```

### 2. Django ORM Lazy Loading in Templates
Django templates trigger lazy DB queries. FastAPI with Pydantic won't. You must
explicitly load all related data in your service layer using `selectinload()`.

### 3. CSRF Tokens
Django uses CSRF protection for form submissions. FastAPI APIs typically use
JWT Bearer tokens instead. If you have browser-based forms, you need either:
- SameSite cookies + CORS
- Custom CSRF middleware (rare for API-only apps)

### 4. Django's `request.user` Magic
Django middleware populates `request.user` on every request. In FastAPI, use
`Depends(get_current_user)` explicitly on routes that need it — never globally.

### 5. Transaction Handling
Django wraps views in `ATOMIC_REQUESTS`. In FastAPI, manage transactions
explicitly in your service layer or use a middleware/dependency.

---

## See Also

- [FastAPI Review Skill](../fastapi-review/SKILL.md) — for reviewing migrated FastAPI code
- [FastAPI Official: Including WSGI](https://fastapi.tiangolo.com/advanced/wsgi/) — Django mount docs
- [FastAPI Official: SQL Databases](https://fastapi.tiangolo.com/tutorial/sql-databases/) — SQLModel tutorial
- [FastAPI Official: OAuth2 JWT](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/) — Auth implementation
- [pwdlib docs](https://github.com/frankie567/pwdlib) — Password hash migration
