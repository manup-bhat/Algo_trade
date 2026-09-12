# Signals & Tasks Migration — Django Signals/Celery → FastAPI Events/BackgroundTasks

## Overview

Django signals provide implicit, decoupled event handling (post_save, pre_delete, etc.).
Celery provides distributed task queues. FastAPI offers explicit alternatives:
- **Service-layer calls** or **SQLAlchemy events** replace Django signals
- **BackgroundTasks** replace simple Celery tasks
- **Arq/SAQ** replace distributed Celery for async workloads

---

## Django Signals → Explicit Service Layer Calls

### Why Not to Replicate Signals in FastAPI

Django signals are **implicit** — code runs without visible call sites, making debugging
nightmarish. FastAPI philosophy: **explicit is better than implicit**.

**Recommendation**: Replace signals with explicit function calls in your service layer.

### Example: `post_save` Signal → Service Layer

**Django (implicit):**
```python
# signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import User

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

@receiver(post_save, sender=User)
def send_welcome_email(sender, instance, created, **kwargs):
    if created:
        send_email_task.delay(instance.email, "Welcome!")
```

**FastAPI (explicit):**
```python
# fastapi_app/src/users/service.py
from .models import User, Profile
from ..notifications.service import NotificationService


class UserService:
    @staticmethod
    def create_user(session, data: UserCreate) -> User:
        user = User.model_validate(data)
        session.add(user)
        session.commit()
        session.refresh(user)

        # Explicit side effects (what signals did implicitly)
        ProfileService.create_for_user(session, user)
        NotificationService.send_welcome_email(user.email)

        return user
```

**Advantages:**
- Easy to trace in IDE (click-through to definition)
- Easy to test (mock specific calls)
- Clear execution order
- No hidden coupling

---

## When SQLAlchemy Events ARE Appropriate

For low-level data integrity concerns (audit logs, timestamps), SQLAlchemy events are acceptable:

```python
from sqlalchemy import event
from datetime import datetime, timezone


# Equivalent to Django's auto_now on save
@event.listens_for(Post, "before_update")
def set_updated_at(mapper, connection, target):
    target.updated_at = datetime.now(timezone.utc)


# Equivalent to post_delete signal for audit logging
@event.listens_for(Post, "after_delete")
def log_deletion(mapper, connection, target):
    # Write to audit log table
    connection.execute(
        audit_log_table.insert().values(
            action="DELETE",
            entity_type="post",
            entity_id=target.id,
            timestamp=datetime.now(timezone.utc),
        )
    )
```

---

## Signal Type Conversion Reference

| Django Signal | FastAPI Equivalent | When to Use |
|-------------|-------------------|-------------|
| `pre_save` | `@event.listens_for(Model, "before_insert/before_update")` | Data integrity only |
| `post_save` (created=True) | Service layer call after `session.commit()` | Business logic |
| `post_save` (created=False) | Service layer call after update | Business logic |
| `pre_delete` | `@event.listens_for(Model, "before_delete")` | Cascade cleanup |
| `post_delete` | Service layer call after `session.delete()` + `commit()` | Notifications, audit |
| `m2m_changed` | Service layer handles M2M explicitly | Business logic |
| `request_started` | `@app.middleware("http")` | Logging |
| `request_finished` | `@app.middleware("http")` (after `call_next`) | Cleanup |

---

## Celery Tasks → FastAPI BackgroundTasks

### When to Use BackgroundTasks (Simple Cases)

Use FastAPI's built-in `BackgroundTasks` when:
- Task is **fire-and-forget** (no retry needed)
- Task is **fast** (< 30 seconds)
- No distributed workers needed
- No task result tracking needed

**Django + Celery:**
```python
# tasks.py
from celery import shared_task

@shared_task
def send_notification_email(user_id, subject, body):
    user = User.objects.get(id=user_id)
    send_email(user.email, subject, body)

# views.py
def create_post(request):
    post = Post.objects.create(...)
    send_notification_email.delay(request.user.id, "Post Created", f"You created: {post.title}")
    return JsonResponse({"id": post.id})
```

**FastAPI + BackgroundTasks:**
```python
from fastapi import BackgroundTasks

def send_notification_email(user_email: str, subject: str, body: str):
    """Runs in background after response is sent."""
    # email sending logic here
    ...

@router.post("/", response_model=PostPublic)
def create_post(
    data: PostCreate,
    session: SessionDep,
    user: CurrentUserDep,
    background_tasks: BackgroundTasks,
):
    post = PostService.create(session, data, user)

    # Schedule background task (runs AFTER response)
    background_tasks.add_task(
        send_notification_email,
        user.email,
        "Post Created",
        f"You created: {post.title}",
    )

    return post
```

---

### When to Use Arq/SAQ (Distributed Task Queue — Celery Replacement)

Use a distributed task queue when:
- Tasks need **retries** with backoff
- Tasks are **long-running** (> 30 seconds)
- Tasks need to run on **separate workers**
- You need **task result tracking**
- You need **scheduled/periodic tasks**
- You need **task priority queues**

**Recommended: Arq** (async-native, Redis-backed)

```bash
pip install arq
```

```python
# fastapi_app/tasks/worker.py
import asyncio
from arq import create_pool
from arq.connections import RedisSettings


async def send_bulk_emails(ctx, user_ids: list[int], template: str):
    """Long-running task — runs on worker process."""
    for user_id in user_ids:
        # Process each user
        await send_email_async(user_id, template)
        await asyncio.sleep(0.1)  # Rate limiting


async def generate_report(ctx, report_id: int):
    """CPU-intensive task — offloaded to worker."""
    # Heavy computation here
    ...


class WorkerSettings:
    functions = [send_bulk_emails, generate_report]
    redis_settings = RedisSettings(host="localhost", port=6379)
    max_jobs = 10
    job_timeout = 300  # 5 minutes
```

```python
# fastapi_app/tasks/client.py
from arq import create_pool
from arq.connections import RedisSettings


async def get_task_pool():
    return await create_pool(RedisSettings())


# In your route:
@router.post("/reports/generate")
async def generate_report(user: CurrentUserDep):
    pool = await get_task_pool()
    job = await pool.enqueue_job("generate_report", report_id=123)
    return {"job_id": job.job_id, "status": "queued"}
```

Run worker: `arq fastapi_app.tasks.worker.WorkerSettings`

---

## Periodic Tasks (Celery Beat → Arq Cron / APScheduler)

### Django + Celery Beat

```python
# celery.py
app.conf.beat_schedule = {
    "cleanup-expired-tokens": {
        "task": "auth.tasks.cleanup_expired_tokens",
        "schedule": crontab(minute=0, hour="*/6"),
    },
}
```

### FastAPI + Arq Cron Jobs

```python
# fastapi_app/tasks/worker.py
from arq import cron

async def cleanup_expired_tokens(ctx):
    """Runs every 6 hours."""
    # cleanup logic
    ...

class WorkerSettings:
    functions = [cleanup_expired_tokens]
    cron_jobs = [
        cron(cleanup_expired_tokens, hour={0, 6, 12, 18}, minute=0),
    ]
```

### Alternative: APScheduler (if not using Arq)

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from contextlib import asynccontextmanager

scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(cleanup_expired_tokens, "cron", hour="*/6")
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)
```

---

## Django Management Commands → CLI Scripts / Lifespan

### Django Management Command

```python
# management/commands/seed_db.py
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = "Seed the database with test data"

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=10)

    def handle(self, *args, **options):
        count = options["count"]
        for i in range(count):
            Post.objects.create(title=f"Post {i}", content="...")
        self.stdout.write(f"Created {count} posts")
```

### FastAPI Equivalent: Typer CLI

```python
# fastapi_app/cli.py
import typer
from sqlmodel import Session
from .database import engine
from .src.posts.models import Post

app = typer.Typer()

@app.command()
def seed_db(count: int = 10):
    """Seed the database with test data."""
    with Session(engine) as session:
        for i in range(count):
            session.add(Post(title=f"Post {i}", content="..."))
        session.commit()
    typer.echo(f"Created {count} posts")

@app.command()
def cleanup_tokens():
    """Remove expired tokens."""
    ...

if __name__ == "__main__":
    app()
```

Run: `python -m fastapi_app.cli seed-db --count 50`

---

## Lifespan Events (Startup/Shutdown)

Replace Django's `AppConfig.ready()` and startup logic:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP (equivalent to AppConfig.ready() or Django's post_migrate signal)
    print("Creating database tables...")
    SQLModel.metadata.create_all(engine)

    # Initialize connections (Redis, HTTP clients, etc.)
    app.state.redis = await aioredis.from_url(settings.REDIS_URL)
    app.state.http_client = httpx.AsyncClient()

    yield  # App is running

    # SHUTDOWN (cleanup)
    await app.state.redis.close()
    await app.state.http_client.aclose()

app = FastAPI(lifespan=lifespan)
```

---

## Decision Matrix: Keep Celery or Replace?

| Scenario | Recommendation |
|----------|---------------|
| Simple email sending | `BackgroundTasks` — no external dependency |
| < 5 task types, all fast | `BackgroundTasks` |
| Need retries with exponential backoff | Arq or keep Celery |
| Distributed workers across machines | Keep Celery or use Arq |
| Complex task chains/workflows | Keep Celery (Canvas) |
| Periodic/scheduled tasks | Arq cron or APScheduler |
| Already heavily invested in Celery | Keep Celery (it works fine with FastAPI) |
| Want fully async stack | Arq (native asyncio) |

### Using Celery WITH FastAPI (Keeping It)

Celery works fine alongside FastAPI — no migration needed:

```python
# celery_app.py (unchanged from Django)
from celery import Celery
celery_app = Celery("myapp", broker=settings.CELERY_BROKER_URL)

# In FastAPI routes — call Celery tasks normally
from .celery_app import celery_app

@router.post("/reports/generate")
def generate_report(user: CurrentUserDep):
    task = celery_app.send_task("reports.generate", args=[user.id])
    return {"task_id": task.id}
```
