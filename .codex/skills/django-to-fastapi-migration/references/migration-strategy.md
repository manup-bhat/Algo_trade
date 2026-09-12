# Migration Strategy — Strangler Fig Pattern

## Overview

The Strangler Fig pattern allows you to incrementally replace a Django application with FastAPI
without any downtime or big-bang rewrite risk. Both applications run simultaneously, sharing
the same database, while traffic is gradually shifted from Django to FastAPI.

---

## Architecture Options

### Option A: WSGIMiddleware Mount (Recommended for APIs)

FastAPI is the primary ASGI app. Django is mounted as a WSGI sub-application.
New routes go to FastAPI; unmatched routes fall through to Django.

```python
# fastapi_app/main.py
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myproject.settings")

import django
django.setup()

from a2wsgi import WSGIMiddleware
from django.core.wsgi import get_wsgi_application
from fastapi import FastAPI

app = FastAPI(title="MyApp", version="2.0.0")

# Include migrated FastAPI routers
from src.users.router import router as users_router
from src.posts.router import router as posts_router

app.include_router(users_router, prefix="/api/v2/users", tags=["users"])
app.include_router(posts_router, prefix="/api/v2/posts", tags=["posts"])

# Mount Django for all remaining routes
django_wsgi = get_wsgi_application()
app.mount("/", WSGIMiddleware(django_wsgi))
```

**Pros:** Single process, simple deployment, shared state possible
**Cons:** WSGI overhead for Django routes, must install `a2wsgi`

### Option B: Reverse Proxy Routing (Recommended for large apps)

Use nginx/HAProxy/Traefik to route specific paths to FastAPI, others to Django.

```nginx
# nginx.conf
upstream django_app {
    server 127.0.0.1:8000;
}

upstream fastapi_app {
    server 127.0.0.1:8001;
}

server {
    listen 80;

    # Migrated endpoints go to FastAPI
    location /api/v2/ {
        proxy_pass http://fastapi_app;
    }

    # Everything else stays on Django
    location / {
        proxy_pass http://django_app;
    }
}
```

**Pros:** Independent scaling, no code coupling, can use different Python versions
**Cons:** More infrastructure, session sharing requires external store (Redis)

### Option C: Feature Flag Routing

Use a feature flag service (LaunchDarkly, Unleash, or simple Redis flag) to dynamically
switch traffic between Django and FastAPI endpoints.

```python
# In reverse proxy or API gateway
if feature_flag("use_fastapi_users"):
    route_to(fastapi_app)
else:
    route_to(django_app)
```

**Pros:** Instant rollback, gradual rollout (1% → 10% → 50% → 100%)
**Cons:** Feature flag infrastructure needed

---

## Migration Order (Recommended)

Migrate in this order for lowest risk:

```
1. Health check / status endpoints     (stateless, no auth)
2. Read-only public endpoints           (GET /api/posts)
3. Authenticated read endpoints         (GET /api/me → requires auth migration)
4. Write endpoints                      (POST, PUT, DELETE)
5. Background tasks / async processing
6. Admin interface
7. Decommission Django
```

### Why This Order?

- **Health checks first**: Proves the infrastructure works, zero risk
- **Read-only next**: No data mutation risk, easy to verify correctness
- **Auth before writes**: You need auth working before write endpoints make sense
- **Writes after reads**: Higher risk, but you've proven the pattern works
- **Tasks last**: Complex, often tightly coupled to Django internals

---

## Shared Database Strategy

During migration, both Django and FastAPI read/write the same database:

```python
# FastAPI database.py — connect to the SAME database as Django
from sqlmodel import create_engine, Session
from .config import settings

# Use the same DATABASE_URL as Django's DATABASES['default']
engine = create_engine(settings.DATABASE_URL, echo=settings.DEBUG)
```

### Migration Management During Transition

| Scenario | Who manages migrations? |
|----------|------------------------|
| Existing Django tables | Django (`manage.py migrate`) |
| New FastAPI-only tables | Alembic |
| Shared tables being migrated | Django (until fully migrated), then Alembic takes over |

**Critical Rule**: Never run both Django migrations AND Alembic on the same table simultaneously.

### Schema Synchronization

```python
# When Django model matches SQLModel — verify they agree
# Run this as a CI check during migration:
def verify_schema_sync():
    """Ensure Django model and SQLModel define the same columns."""
    from django.apps import apps
    from sqlmodel import SQLModel, inspect

    django_model = apps.get_model("users", "User")
    django_fields = {f.column for f in django_model._meta.get_fields() if hasattr(f, 'column')}

    # Compare with SQLModel table
    inspector = inspect(engine)
    sqlmodel_columns = {col['name'] for col in inspector.get_columns('users_user')}

    assert django_fields == sqlmodel_columns, f"Schema drift: {django_fields ^ sqlmodel_columns}"
```

---

## Rollback Plan

Every migrated endpoint must have a clear rollback:

1. **Feature flag rollback** (instant): Toggle flag back to Django
2. **Reverse proxy rollback** (seconds): Update nginx config, reload
3. **WSGIMiddleware rollback** (deploy): Remove FastAPI router, Django mount catches the route

### Rollback Triggers

- Error rate > 1% on migrated endpoint
- P99 latency > 2× Django baseline
- Data inconsistency detected
- Authentication failures spike

---

## Timeline Template

| Week | Activity | Risk Level |
|------|----------|-----------|
| 1-2 | Project scaffolding, DB connection, health check migrated | Low |
| 3-4 | First 3-5 read-only endpoints migrated | Low |
| 5-6 | Authentication system migrated | Medium |
| 7-8 | Write endpoints migrated (with contract tests) | Medium |
| 9-10 | Background tasks migrated | Medium |
| 11-12 | Admin panel replacement, final Django routes | Medium |
| 13-14 | Django decommissioned, cleanup | Low |
| 15-16 | Performance tuning, monitoring stabilization | Low |

Adjust based on app size. A 50-endpoint Django app typically takes 8-12 weeks.
A 200+ endpoint app may take 4-6 months.

---

## Anti-Patterns to Avoid

| Anti-Pattern | Why It Fails | Do This Instead |
|-------------|-------------|-----------------|
| Big-bang rewrite | Months of work with no production feedback | Strangler Fig |
| Rewriting Django ORM queries verbatim | SQLAlchemy has different patterns | Learn SQLModel idioms |
| Keeping Django's URL naming convention | FastAPI uses `{param}` not `<param:type>` | Adopt FastAPI conventions |
| Running two migration systems on same tables | Schema conflicts, data corruption | One system per table |
| Migrating auth first | Blocks all other work if it breaks | Migrate stateless reads first |
| Skipping contract tests | Silent behavior changes | Test both old and new |
| Copying Django middleware as-is | Different execution model | Redesign for ASGI |
