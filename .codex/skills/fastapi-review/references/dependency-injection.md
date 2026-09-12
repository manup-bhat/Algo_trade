# Dependency Injection Reference

## Core Principle

Routes declare **what** they need. Dependencies own **how** to fulfill it.
Business logic, DB access, and auth checks live behind `Depends`, not inline.

---

## yield Dependencies Must Clean Up

```python
# ❌ Resource leaks if route raises
async def get_session() -> AsyncSession:
    return SessionLocal()

# ✅ Cleanup runs on success AND exception
async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
```

**Review**: Any `yield` dependency holding a resource (DB session, file handle, HTTP client)
must release it via a context manager or `try/finally`.

---

## No Singletons Per Request

```python
# ❌ New connection pool every request
@app.get("/proxy")
async def proxy(client: httpx.AsyncClient = Depends(lambda: httpx.AsyncClient())):
    ...

# ✅ One client for the app lifetime
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http = httpx.AsyncClient()
    yield
    await app.state.http.aclose()

def get_http(request: Request) -> httpx.AsyncClient:
    return request.app.state.http
```

---

## Annotated Form (FastAPI 0.95+)

```python
# ⚠️ Old form — still works
async def list_items(session: AsyncSession = Depends(get_session)): ...

# ✅ Annotated form — define once, reuse everywhere
SessionDep = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]

async def list_items(session: SessionDep): ...
```

---

## Auth ≠ Authorization — The #1 Bug

`Depends(get_current_user)` proves **who** — it does NOT prove **they may**.

```python
# ❌ Any authenticated user can delete anyone's document
@app.delete("/documents/{doc_id}")
async def delete_document(doc_id: int, user: CurrentUser, session: SessionDep):
    doc = await session.get(Document, doc_id)
    await session.delete(doc)        # ownership never checked

# ✅ Ownership verified before mutation
@app.delete("/documents/{doc_id}", status_code=204)
async def delete_document(doc_id: int, user: CurrentUser, session: SessionDep):
    doc = await session.get(Document, doc_id)
    if doc is None:
        raise HTTPException(404, "Not found")
    if doc.owner_id != user.id:
        raise HTTPException(403, "Forbidden")
    await session.delete(doc)
    await session.commit()
```

**Move to a reusable dependency:**

```python
async def owned_document(
    doc_id: int,
    user: CurrentUser,
    session: SessionDep,
) -> Document:
    doc = await session.get(Document, doc_id)
    if doc is None:
        raise HTTPException(404, "Not found")
    if doc.owner_id != user.id:
        raise HTTPException(403, "Forbidden")
    return doc

OwnedDoc = Annotated[Document, Depends(owned_document)]
```

---

## Chain Dependencies for Reuse

```python
async def valid_post_id(post_id: UUID4, session: SessionDep) -> Post:
    post = await service.get_by_id(post_id)
    if not post:
        raise PostNotFound()
    return post

async def valid_owned_post(
    post: Annotated[Post, Depends(valid_post_id)],
    token_data: Annotated[dict, Depends(parse_jwt_data)],
) -> Post:
    if post.creator_id != token_data["user_id"]:
        raise UserNotOwner()
    return post
```

FastAPI **caches** each dependency's result within a single request — chaining costs nothing.

---

## Prefer async dependencies

Sync (`def`) dependencies run in the threadpool — unnecessary overhead for small non-I/O checks.

```python
# ❌ Runs in threadpool even though it does no I/O
def get_current_user_id(token_data: dict = Depends(parse_jwt_data)) -> str:
    return token_data["user_id"]

# ✅ Runs on the event loop
async def get_current_user_id(token_data: dict = Depends(parse_jwt_data)) -> str:
    return token_data["user_id"]
```
