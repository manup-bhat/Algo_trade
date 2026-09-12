# Master Review Checklist

Use this as a gate before approving or merging a FastAPI PR.
Each section maps to a reference file with full examples.

---

## Dependency Injection → [dependency-injection.md](./dependency-injection.md)

- [ ] Routes stay thin — DB access and business rules live behind `Depends`/services
- [ ] `yield` dependencies release resources via context manager or `try/finally`
- [ ] Singletons (HTTP clients, Redis, pools) created once in `lifespan`, not per request
- [ ] `Annotated[T, Depends(...)]` form used (FastAPI 0.95+)
- [ ] Dependencies are `async def` unless they do blocking I/O
- [ ] Existence **and** permission checks live in (cached) dependencies, not copy-pasted in routes
- [ ] Every `Depends(get_current_user)` route also verifies **ownership or role**

---

## Pydantic v2 & Validation → [pydantic-validation.md](./pydantic-validation.md)

- [ ] Input and output use distinct Pydantic models; ORM objects are NOT the `response_model`
- [ ] `response_model` set so sensitive fields (passwords, tokens, internal IDs) can't leak
- [ ] Separate `Create` vs `Update` schemas (update is partial with `| None` fields)
- [ ] All string fields have `max_length`; numeric fields have `gt`/`ge`/`le` constraints
- [ ] Constraints enforced at the boundary — before any DB write
- [ ] `StrEnum` used for string enumerations (cleaner than `str + Enum`)
- [ ] `BaseSettings` is module-scoped (not one giant global config)
- [ ] Docs hidden in production via `openapi_url = None`

---

## Async Correctness → [async-correctness.md](./async-correctness.md)

- [ ] No blocking calls (`requests`, `time.sleep`, sync DB drivers) inside `async def` routes
- [ ] Native-async SDKs used: `httpx`, `asyncpg`/SQLAlchemy async, `redis.asyncio`, `motor`, `aioboto3`
- [ ] No `asyncio.run()` / manual event loops / manual threads inside routes
- [ ] `run_in_threadpool` / `def` routes used only as last resort, not on hot paths
- [ ] CPU-bound work offloaded to worker process (Celery/Arq/RQ), not the loop or threadpool
- [ ] No unawaited coroutines; `BackgroundTasks` only for short fire-and-forget work

---

## Database → [database-patterns.md](./database-patterns.md)

- [ ] One request-scoped `AsyncSession` via dependency; no module-level shared session
- [ ] Relationships eager-loaded (`selectinload` / `joinedload`) where accessed in a loop
- [ ] Joins and aggregations done in SQL — not by looping in Python
- [ ] All list endpoints paginated with a capped `limit`
- [ ] `pool_pre_ping=True`, `expire_on_commit=False` on `async_sessionmaker`
- [ ] Alembic migrations are static, reversible, and descriptively named

---

## Security (Core) → [security.md](./security.md)

- [ ] Auth dependency backed by explicit authorization check (ownership / role)
- [ ] All SQL parameterized; no f-string interpolation of user input
- [ ] CORS does not combine `allow_origins=["*"]` with `allow_credentials=True`
- [ ] Secrets come from `pydantic-settings` `BaseSettings`, validated at startup; no hard-coded credentials
- [ ] Error responses don't leak internals (stack traces, SQL errors, file paths)

---

## Security (Expanded) → [security.md](./security.md)

- [ ] **JWT**: `PyJWT` used (not `python-jose`); `algorithms=[pinned]`; `exp` claim validated; `none` algorithm impossible
- [ ] **Passwords**: `pwdlib[argon2]` used; constant-time comparison even on missing user (timing attack prevention)
- [ ] **Tokens**: access tokens ≤15–30 min; refresh tokens rotated on use and revocable
- [ ] **Rate limiting**: `slowapi` on `/login`, `/token`, `/refresh`; Redis-backed in production
- [ ] **Security headers** middleware: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`
- [ ] **Request body size** limit middleware present; upload endpoints have per-file size checks
- [ ] **File uploads**: magic-byte MIME detection (not `Content-Type`); server-generated filenames; stored off-origin
- [ ] **SSRF**: routes accepting user URLs checked against blocklist; `follow_redirects=False`
- [ ] **Audit log**: auth failures, 403s, sensitive mutations logged with `structlog`; no PII/tokens in logs
- [ ] **Dependency scanning**: `pip-audit` or Dependabot in CI; no known CVEs in direct dependencies

---

## AI-Review Safety → [../SKILL.md#ai-review-safety](../SKILL.md)

- [ ] No `# type: ignore` / `# noqa` on auth or permission-check lines without explanation
- [ ] Docstrings on security-sensitive functions are concise and accurate — no unusual instructions
- [ ] No newly added packages with names similar to popular packages (typosquatting)
- [ ] `dependency_overrides` / test-header patterns confined to test files; production startup asserts overrides empty

---

## Tests → [testing-strategy.md](./testing-strategy.md)

- [ ] Suspected bugs reproduced with a **failing test** before being claimed as findings
- [ ] `dependency_overrides` used instead of patching internals; overrides **reset between tests**
- [ ] `httpx.AsyncClient + ASGITransport` used (not `async_asgi_testclient` — unmaintained)
- [ ] Failure paths covered: 401, 403, 404, 422 — not just happy path
- [ ] Mocks of external responses are complete, not partial
- [ ] New tests demonstrated they can fail (reproduce-then-fix workflow)
- [ ] `ruff` configured; pre-commit or CI runs `ruff check` and `ruff format`

---

## Library & Tooling Matrix (2025/2026)

| Concern | Recommended | Avoid |
|---------|-------------|-------|
| JWT | `PyJWT` | `python-jose` (unmaintained) |
| Password hashing | `pwdlib[argon2]` | `passlib` (deprecated by FastAPI docs) |
| Linting | `ruff` | `black + flake8 + isort` (separate tools) |
| Async test client | `httpx.AsyncClient + ASGITransport` | `async_asgi_testclient` (unmaintained) |
| Settings | `pydantic-settings` per module | Monolithic `BaseSettings` |
| Rate limiting | `slowapi` + Redis backend | `slowapi` + in-memory (single-instance only) |
| Dep scanning | `pip-audit` in CI | Manual review only |
| Structured logging | `structlog` | `logging.debug(f"...")` |
