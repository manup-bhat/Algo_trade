# Database Patterns Reference

## One Request-Scoped Session via Dependency

```python
# ❌ Shared across concurrent requests — race conditions, leaked state
session = SessionLocal()   # module-level

# ✅ Request-scoped, released on error
async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session

SessionDep = Annotated[AsyncSession, Depends(get_session)]
```

---

## Avoid N+1 — Eager-Load Relationships

```python
# ❌ 1 query for orders + N queries for customer names
orders = (await session.execute(select(Order))).scalars().all()
return [{"id": o.id, "customer": o.customer.name} for o in orders]  # N+1

# ✅ Single query with eager load
stmt = select(Order).options(selectinload(Order.customer))
orders = (await session.execute(stmt)).scalars().all()
return [{"id": o.id, "customer": o.customer.name} for o in orders]
```

**Review trigger**: relationship access (`.customer`, `.items`, `.tags`) inside a loop
without a matching `options(selectinload(...))` or `options(joinedload(...))`.

---

## Paginate Every List Endpoint

```python
# ❌ Returns every row; degrades as table grows
@app.get("/users")
async def list_users(session: SessionDep):
    return (await session.execute(select(User))).scalars().all()

# ✅ Bounded page
@app.get("/users", response_model=list[UserOut])
async def list_users(
    session: SessionDep,
    limit: int = Query(default=50, le=200, ge=1),
    offset: int = Query(default=0, ge=0),
):
    stmt = select(User).order_by(User.id).limit(limit).offset(offset)
    return (await session.execute(stmt)).scalars().all()
```

For large tables, prefer **keyset/cursor pagination** over offset — offset gets
slower as the table grows because the DB must scan and skip rows.

---

## SQL-First: Aggregate in the Database

```python
# ❌ Fetch all orders, tally in Python
orders = (await session.execute(select(Order))).scalars().all()
totals: dict[int, float] = {}
for o in orders:
    totals[o.customer_id] = totals.get(o.customer_id, 0) + o.amount

# ✅ Let the database do the grouping
stmt = (
    select(Order.customer_id, func.sum(Order.amount).label("total"))
    .group_by(Order.customer_id)
)
totals = {row.customer_id: row.total for row in (await session.execute(stmt)).all()}
```

Build JSON for nested response objects in the DB with `func.json_build_object`
rather than Python dicts assembled in a loop.

---

## SQLAlchemy 2.0 Async Best Practices

```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
```

Key flags:
- `pool_pre_ping=True` — recycles stale connections automatically
- `expire_on_commit=False` — attributes remain accessible after `commit()` without an extra SELECT

---

## Alembic Migration Rules

1. Migrations must be **static and reversible** — no dynamic data generation in `upgrade()`
2. Use descriptive slugs: `alembic revision --autogenerate -m "add_post_content_fts_index"`
3. Set human-readable filename template in `alembic.ini`:
   ```ini
   file_template = %%(year)d-%%(month).2d-%%(day).2d_%%(slug)s
   ```

---

## DB Naming Conventions

| Convention | Rule |
|-----------|------|
| Case | `lower_case_snake` |
| Form | singular (`post`, `post_like`) |
| Module prefix | `payment_account`, `payment_bill` |
| Datetime suffix | `created_at`, `published_at` |
| Date suffix | `birth_date` |
| FK naming | `profile_id` (consistent), `creator_id` (concrete when meaningful) |
