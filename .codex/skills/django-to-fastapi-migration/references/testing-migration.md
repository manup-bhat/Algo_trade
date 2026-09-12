# Testing Migration — Django TestCase → pytest + httpx

## Overview

Django uses its own `TestCase` class with `self.client`. FastAPI testing uses
pytest fixtures with `httpx.AsyncClient` and `ASGITransport`. The shift enables
faster, more flexible, async-native testing.

---

## Framework Comparison

| Django Testing | FastAPI Testing |
|---------------|----------------|
| `django.test.TestCase` | `pytest` functions |
| `self.client.get("/url/")` | `client.get("/url/")` with httpx |
| `self.assertEqual(resp.status_code, 200)` | `assert response.status_code == 200` |
| `django.test.override_settings` | `app.dependency_overrides` |
| `TestCase.setUp()` | pytest fixtures |
| `TransactionTestCase` | pytest with `session.rollback()` |
| `@mock.patch` | `app.dependency_overrides` (preferred) |
| `reverse("url-name")` | Direct URL strings |
| `APIClient` (DRF) | `httpx.AsyncClient` |
| `factory_boy` | `factory_boy` (works with SQLModel too) |

---

## Test Setup: Fixtures

### Django Test Setup

```python
from django.test import TestCase
from django.contrib.auth.models import User

class PostTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )
        self.client.force_login(self.user)

    def test_create_post(self):
        response = self.client.post("/api/posts/", {
            "title": "Test Post",
            "content": "Hello world",
        }, content_type="application/json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["title"], "Test Post")
```

### FastAPI Test Setup

```python
# tests/conftest.py
import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from fastapi_app.main import app
from fastapi_app.database import get_session
from fastapi_app.src.auth.dependencies import get_current_user
from fastapi_app.src.auth.models import User


@pytest.fixture(name="session")
def session_fixture():
    """Create a fresh in-memory database for each test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
async def client_fixture(session: Session):
    """Async test client with dependency overrides."""

    def get_session_override():
        return session

    app.dependency_overrides[get_session] = get_session_override

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture(name="authenticated_client")
async def authenticated_client_fixture(session: Session):
    """Client with authentication pre-configured."""
    # Create test user
    user = User(username="testuser", email="test@example.com", is_active=True)
    session.add(user)
    session.commit()
    session.refresh(user)

    def get_session_override():
        return session

    def get_current_user_override():
        return user

    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides[get_current_user] = get_current_user_override

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
```

### Test Functions

```python
# tests/test_posts.py
import pytest
from httpx import AsyncClient


@pytest.mark.anyio
async def test_create_post(authenticated_client: AsyncClient):
    response = await authenticated_client.post("/api/posts/", json={
        "title": "Test Post",
        "content": "Hello world",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test Post"
    assert "id" in data


@pytest.mark.anyio
async def test_create_post_unauthenticated(client: AsyncClient):
    response = await client.post("/api/posts/", json={
        "title": "Test Post",
        "content": "Hello world",
    })
    assert response.status_code == 401


@pytest.mark.anyio
async def test_list_posts(client: AsyncClient, session):
    # Setup: create test data
    from fastapi_app.src.posts.models import Post
    post = Post(title="Existing Post", content="Content", author_id=1, is_published=True)
    session.add(post)
    session.commit()

    response = await client.get("/api/posts/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert data[0]["title"] == "Existing Post"
```

---

## pytest Configuration

```ini
# pytest.ini (or pyproject.toml [tool.pytest.ini_options])
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_functions = test_*
```

```toml
# pyproject.toml alternative
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

Required packages:
```
pytest
pytest-asyncio
httpx
anyio
```

---

## dependency_overrides (Replacing Django Mocks)

FastAPI's `dependency_overrides` is the primary mocking mechanism — cleaner than `@mock.patch`:

### Override Database Session

```python
def get_session_override():
    return test_session

app.dependency_overrides[get_session] = get_session_override
```

### Override Authentication

```python
# Skip auth entirely in tests
def fake_current_user():
    return User(id=1, username="testuser", is_active=True)

app.dependency_overrides[get_current_user] = fake_current_user
```

### Override External Services

```python
# Django: @mock.patch("myapp.services.send_email")
# FastAPI: override the dependency

def fake_email_service():
    return MockEmailService()

app.dependency_overrides[get_email_service] = fake_email_service
```

### Always Clean Up

```python
# In fixture teardown or test cleanup:
app.dependency_overrides.clear()
```

---

## Contract Tests (Run Against BOTH Django and FastAPI)

During migration, maintain tests that verify both implementations return identical responses:

```python
# tests/contract/test_posts_contract.py
import pytest
import httpx

DJANGO_BASE = "http://localhost:8000"
FASTAPI_BASE = "http://localhost:8001"


@pytest.mark.parametrize("base_url", [DJANGO_BASE, FASTAPI_BASE])
async def test_list_posts_contract(base_url):
    """Both Django and FastAPI must return the same shape."""
    async with httpx.AsyncClient(base_url=base_url) as client:
        response = await client.get("/api/posts/")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)

    if data:
        post = data[0]
        assert "id" in post
        assert "title" in post
        assert "created_at" in post


@pytest.mark.parametrize("base_url", [DJANGO_BASE, FASTAPI_BASE])
async def test_get_post_404_contract(base_url):
    """Both must return 404 for non-existent post."""
    async with httpx.AsyncClient(base_url=base_url) as client:
        response = await client.get("/api/posts/999999/")

    assert response.status_code == 404
```

---

## Testing Database Isolation

### Django Approach

Django wraps each test in a transaction and rolls back.

### FastAPI Equivalent

```python
@pytest.fixture(name="session")
def session_fixture():
    """Each test gets its own in-memory SQLite database."""
    engine = create_engine(
        "sqlite://",  # In-memory — destroyed after test
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    # Engine and all data is garbage collected
```

For PostgreSQL tests (closer to production):
```python
@pytest.fixture(name="session")
def session_fixture():
    """Use transaction rollback for test isolation."""
    engine = create_engine(settings.TEST_DATABASE_URL)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()
```

---

## Testing File Uploads

### Django

```python
from django.core.files.uploadedfile import SimpleUploadedFile

def test_upload_avatar(self):
    file = SimpleUploadedFile("avatar.png", b"file_content", content_type="image/png")
    response = self.client.post("/api/avatar/", {"file": file})
    self.assertEqual(response.status_code, 200)
```

### FastAPI

```python
@pytest.mark.anyio
async def test_upload_avatar(authenticated_client: AsyncClient):
    # Create a minimal valid PNG file
    png_header = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

    response = await authenticated_client.post(
        "/api/avatar/",
        files={"file": ("avatar.png", png_header, "image/png")},
    )
    assert response.status_code == 200
```

---

## Testing WebSockets

### FastAPI WebSocket Test

```python
from fastapi.testclient import TestClient

def test_websocket_connection():
    client = TestClient(app)
    with client.websocket_connect("/ws/notifications") as ws:
        ws.send_json({"type": "subscribe", "channel": "posts"})
        data = ws.receive_json()
        assert data["type"] == "subscribed"
```

---

## Migration Checklist for Tests

- [ ] Set up `pytest.ini` / `pyproject.toml` with asyncio_mode
- [ ] Create `conftest.py` with session and client fixtures
- [ ] Install: `pytest`, `pytest-asyncio`, `httpx`, `anyio`
- [ ] Migrate each Django `TestCase` → pytest async function
- [ ] Replace `self.client` → `AsyncClient` fixture
- [ ] Replace `@mock.patch` → `app.dependency_overrides`
- [ ] Replace `reverse("name")` → direct URL strings
- [ ] Replace `self.assertEqual` → plain `assert`
- [ ] Add contract tests for migrated endpoints
- [ ] Verify test isolation (no state leaks between tests)
- [ ] Set up CI to run both Django and FastAPI tests during transition
