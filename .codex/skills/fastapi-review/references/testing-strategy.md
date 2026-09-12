# Testing Strategy Reference

## Principle: Reproduce, Don't Assert

A prose finding is a hypothesis. A failing test is proof.

For every suspected bug:
1. Write a test asserting the **secure/correct** behavior
2. Run it — it must **FAIL** against the current buggy code
3. Apply the fix
4. Run it — it must **PASS**
5. A test that was never red proves nothing

---

## Canonical Async Test Setup

Use `httpx.AsyncClient` with `ASGITransport`. **Do NOT** use `async_asgi_testclient` — it is unmaintained.

```python
# conftest.py
from typing import AsyncGenerator
import pytest
from httpx import AsyncClient, ASGITransport
from src.main import app

@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

@pytest.mark.asyncio
async def test_create_post(client: AsyncClient):
    resp = await client.post("/posts", json={"title": "Hello"})
    assert resp.status_code == 201
```

**Set async from day 0** — migrating from sync `TestClient` later is painful once
any route or fixture becomes async.

---

## dependency_overrides — Not monkeypatch

```python
# ❌ Brittle — couples test to import paths, breaks on refactor
@patch("app.routes.orders.asyncpg.connect")
def test_get_order(mock_connect): ...

# ✅ Override the seam FastAPI provides
from src.auth.dependencies import parse_jwt_data
from src.main import app

def fake_user():
    return {"user_id": "00000000-0000-0000-0000-000000000001"}

@pytest.fixture(autouse=True)
def _override_auth():
    app.dependency_overrides[parse_jwt_data] = fake_user
    yield
    app.dependency_overrides.clear()   # MUST reset between tests
```

**Always** clear `dependency_overrides` in fixture teardown to prevent state leaking.

---

## Reproducing a Security Bug (Example)

Suspected bug: `DELETE /documents/{doc_id}` does not check ownership.

```python
# test_document_authorization.py
# ⚠️ TEST FILE ONLY — X-Test-User header must NEVER reach production code

import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import Header
from src.main import app
from src.auth.dependencies import get_current_user
from src.db.dependencies import get_session

USERS = {
    "alice": User(id=1, email="alice@example.com"),
    "bob":   User(id=2, email="bob@example.com"),
}

def fake_current_user(x_test_user: str = Header(default="alice")) -> User:
    return USERS[x_test_user]

@pytest.mark.asyncio
async def test_user_cannot_delete_another_users_document(db_session):
    # Arrange: document owned by Alice
    db_session.add(Document(id=10, owner_id=1, title="Alice's doc"))
    await db_session.commit()

    app.dependency_overrides[get_current_user] = fake_current_user
    app.dependency_overrides[get_session] = lambda: db_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.delete("/documents/10", headers={"X-Test-User": "bob"})

    # Assert the SECURE behavior
    assert resp.status_code == 403, f"Expected 403 but got {resp.status_code}"
    app.dependency_overrides.clear()
```

Run against unfixed code → should show `assert 204 == 403` (vulnerability confirmed).
Apply fix → should show `PASSED`.

---

## Production Safety — dependency_overrides Must Not Exist in Prod

```python
# In lifespan or startup: fail loudly if overrides are set outside test context
@asynccontextmanager
async def lifespan(app: FastAPI):
    if app.dependency_overrides and not os.getenv("TESTING"):
        raise RuntimeError("dependency_overrides must not be set in production")
    yield
```

---

## Test Coverage Requirements

| Path | Priority | Tests Required |
|------|---------|----------------|
| Happy path | Medium | Basic correctness |
| 401 Unauthorized | **High** | Missing/invalid token |
| 403 Forbidden | **High** | Valid token, wrong owner/role |
| 404 Not Found | High | Non-existent resource |
| 422 Validation | High | Invalid input shapes |
| 409 Conflict | Medium | Duplicate creation |

```python
# ❌ Happy-path only — proves nothing about auth
def test_create_item():
    resp = client.post("/items", json={"name": "x", "price": 5})
    assert resp.status_code == 201

# ✅ Boundary paths — where bugs live
def test_create_item_rejects_negative_price():
    resp = client.post("/items", json={"name": "x", "price": -5})
    assert resp.status_code == 422

def test_create_item_requires_authentication():
    resp = client_without_auth.post("/items", json={"name": "x", "price": 5})
    assert resp.status_code == 401
```

---

## Evaluate the PR's Own Tests

A PR that ships tests is not automatically well-tested. Ask:

- Does the assertion test **behavior**, or just that a mock was called?
- Are **failure paths** covered (401, 403, 404, 422)?
- Is the mock **complete** — does it include all fields the handler reads?
- Were tests **written after the fact and always green**? Green from birth proves little.
- For DB tests: is the test using a real async session or mocking everything out?

---

## Ruff for Code Quality

```bash
# pyproject.toml
[tool.ruff]
line-length = 100
select = ["E", "F", "I", "UP", "S", "B", "A"]

[tool.ruff.lint]
ignore = ["S101"]   # allow assert in tests
```

Ruff replaces `black`, `flake8`, `isort`, `pyupgrade` — single tool, 600+ rules, 10-100× faster.
