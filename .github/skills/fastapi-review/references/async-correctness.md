# Async Correctness Reference

## The Core Rule

One blocking call inside `async def` stalls **every** in-flight request on the event loop —
not just the current one. FastAPI's throughput advantage exists only if the loop is never blocked.

---

## Decision Tree

```
Need I/O in a route?
├── Native async SDK exists?  →  YES: use async SDK (preferred)
│                                     httpx, asyncpg, redis.asyncio, motor, aioboto3
└── NO native SDK?
    ├── sync def route (FastAPI runs it in threadpool)  — OK for low-traffic
    └── run_in_threadpool(blocking_fn)                 — last resort
        └── CPU-heavy? → offload to worker process (Celery / Arq / RQ)
```

---

## Never Block Inside `async def`

```python
# ❌ Blocks the ENTIRE event loop for all requests
@app.get("/report")
async def report():
    data = requests.get("https://slow-api.example.com").json()   # blocking socket
    time.sleep(2)                                                  # blocks the loop
    return data

# ✅ Awaits — loop serves other requests while waiting
@app.get("/report")
async def report(client: httpx.AsyncClient = Depends(get_http)):
    resp = await client.get("https://slow-api.example.com")
    return resp.json()
```

---

## Sync SDK Table

| Sync (avoid in async def) | Native-async replacement |
|--------------------------|--------------------------|
| `requests` | `httpx.AsyncClient`, `aiohttp` |
| `psycopg2` | `asyncpg`, `SQLAlchemy async engine` |
| `redis-py` (sync) | `redis.asyncio` |
| `pymongo` | `motor` |
| `boto3` | `aioboto3` |
| `smtplib` | `aiosmtplib` |

---

## asyncio.run() Inside a Route = Always Wrong

```python
# ❌ Raises RuntimeError inside a running event loop
@app.get("/users/{uid}")
def get_user(uid: int):
    return asyncio.run(repo.fetch(uid))

# ✅
@app.get("/users/{uid}")
async def get_user(uid: int):
    return await repo.fetch(uid)
```

---

## Threadpool as Last Resort

```python
from fastapi.concurrency import run_in_threadpool

@app.get("/legacy")
async def legacy():
    # Only use if no async SDK exists AND it's not CPU-bound
    return await run_in_threadpool(blocking_library_call)
```

**Warning**: The threadpool cap is ~40 threads (AnyIO default). Hot paths
going through the threadpool collapse under load.

---

## CPU-Bound Work → Worker Process

```python
# ❌ Pins a worker process; all concurrent requests are throttled
@app.post("/render")
async def render(doc: Doc):
    return heavy_pdf_render(doc)

# ✅ Enqueue; return a job handle
@app.post("/render", status_code=202)
async def render(doc: Doc):
    job = await queue.enqueue(heavy_pdf_render, doc)
    return {"job_id": job.id}
```

---

## BackgroundTasks Scope

`BackgroundTasks` = in-process, fire-and-forget, no retry, no persistence.

| Use BackgroundTasks | Use a real queue (Celery/Arq/RQ) |
|--------------------|--------------------------------|
| Send a welcome email | Payment processing |
| Log an analytics event | Heavy data processing |
| < 1 second, silent failure ok | Retry-critical, needs scheduling |

```python
# ✅ Fine for BackgroundTasks
@app.post("/signup")
async def signup(user: UserCreate, tasks: BackgroundTasks):
    tasks.add_task(send_welcome_email, user.email)
```

---

## Unawaited Coroutines

```python
# ❌ Coroutine dropped silently — email never sent
@app.post("/signup")
async def signup(user: UserCreate):
    send_welcome_email(user.email)  # returns coroutine object, never awaited

# ✅
    await send_welcome_email(user.email)
    # or: tasks.add_task(send_welcome_email, user.email)
```
