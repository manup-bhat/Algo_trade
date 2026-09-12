# Security Reference (OWASP 2025)

## 1. Auth vs Authorization — Top Finding

`Depends(get_current_user)` = authentication only. Authorization = separate check.

```python
# ❌ Any authenticated user can mutate any resource
@app.delete("/documents/{doc_id}")
async def delete_document(doc_id: int, user: CurrentUser, session: SessionDep):
    doc = await session.get(Document, doc_id)
    await session.delete(doc)   # owner never checked

# ✅ Ownership verified
    if doc.owner_id != user.id:
        raise HTTPException(403, "Forbidden")
```

---

## 2. JWT — PyJWT (Not python-jose)

FastAPI official docs now use **PyJWT** (`pip install pyjwt`). `python-jose` is unmaintained.

```python
import jwt
from jwt.exceptions import InvalidTokenError

ALGORITHM = "HS256"   # pin explicitly; never accept "none"
ACCESS_TOKEN_EXPIRE_MINUTES = 15   # short-lived

def create_access_token(subject: str | int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": str(subject), "exp": expire}, settings.JWT_SECRET, algorithm=ALGORITHM)

async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> User:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
        username: str | None = payload.get("sub")
        if username is None:
            raise credentials_exception
    except InvalidTokenError:
        raise credentials_exception
    ...
```

Checklist:
- [ ] `algorithms=[...]` list with single pinned value
- [ ] `exp` claim set and validated
- [ ] `sub` claim looked up in DB — don't trust payload claims directly
- [ ] Refresh tokens rotated on each use and revocable (stored in DB/Redis)
- [ ] Secret loaded from `pydantic-settings`, not hard-coded

---

## 3. Password Hashing — pwdlib + Argon2

FastAPI official docs now recommend **pwdlib** (`pip install "pwdlib[argon2]"`).

```python
from pwdlib import PasswordHash

password_hash = PasswordHash.recommended()   # Argon2id by default
DUMMY_HASH = password_hash.hash("dummypassword")   # for timing-safe login

def authenticate_user(db, username: str, password: str) -> User | None:
    user = get_user(db, username)
    if not user:
        password_hash.verify(password, DUMMY_HASH)  # constant-time even on miss
        return None
    if not password_hash.verify(password, user.hashed_password):
        return None
    return user
```

**Timing attack prevention**: always run `verify()` even when user not found.

---

## 4. CORS

```python
# ❌ Wildcard + credentials — browsers reject it AND it's unsafe
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True)

# ✅ Enumerate trusted origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
)
```

---

## 5. Rate Limiting (slowapi)

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address, storage_uri=settings.REDIS_URL)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.post("/auth/login")
@limiter.limit("5/minute")
async def login(request: Request, credentials: LoginRequest): ...

@app.post("/auth/refresh")
@limiter.limit("20/minute")
async def refresh(request: Request, token: RefreshRequest): ...
```

**Production**: use `storage_uri=Redis` — in-memory limits reset on restart and don't
apply across multiple workers.

---

## 6. Secrets — pydantic-settings

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str          # required — app refuses to start if absent
    jwt_secret: str
    redis_url: str = "redis://localhost:6379"
    cors_origins: list[str] = []

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        secrets_dir="/run/secrets",  # Docker/K8s mounted secrets
    )

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

**Grep the codebase for**:
- String literals containing `sk-`, `-----BEGIN`, connection strings with passwords
- Hard-coded `SECRET_KEY = "..."` patterns

---

## 7. SQL Parameterization

```python
# ❌ SQL injection
await session.execute(text(f"SELECT * FROM users WHERE email = '{email}'"))

# ✅ Bound parameter
await session.execute(
    text("SELECT * FROM users WHERE email = :email"),
    {"email": email}
)
```

With SQLAlchemy ORM/Core expressions, parameterization is automatic.
Only raw `text()` calls need explicit `:param` bindings.

---

## 8. Security Headers Middleware

```python
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=()"
        # Strict-Transport-Security only if serving HTTPS:
        # response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

app.add_middleware(SecurityHeadersMiddleware)
```

---

## 9. Request Size Limit

```python
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse

class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_body_size: int = 1 * 1024 * 1024):
        super().__init__(app)
        self.max_body_size = max_body_size

    async def dispatch(self, request, call_next):
        cl = request.headers.get("content-length")
        if cl and int(cl) > self.max_body_size:
            return JSONResponse({"detail": "Request body too large"}, status_code=413)
        return await call_next(request)

app.add_middleware(RequestSizeLimitMiddleware, max_body_size=5 * 1024 * 1024)
```

---

## 10. File Upload Security

```python
import magic   # python-magic (libmagic)
import hashlib

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

@app.post("/uploads", status_code=201)
async def upload_file(file: UploadFile, user: CurrentUser):
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large")

    detected_mime = magic.from_buffer(content, mime=True)   # magic bytes, not Content-Type
    if detected_mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(415, f"Unsupported type: {detected_mime}")

    # Server-generated name — never trust client filename
    safe_name = f"{user.id}/{hashlib.sha256(content).hexdigest()[:16]}.bin"
    await storage.put(safe_name, content)
    return {"key": safe_name}
```

---

## 11. SSRF Prevention

```python
import ipaddress
from urllib.parse import urlparse

BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}

def is_safe_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        if parsed.hostname in BLOCKED_HOSTS:
            return False
        addr = ipaddress.ip_address(parsed.hostname)
        return addr.is_global
    except (ValueError, TypeError):
        return False

@app.post("/webhook-test")
async def test_webhook(url: str, client: httpx.AsyncClient = Depends(get_http)):
    if not is_safe_url(url):
        raise HTTPException(400, "URL not allowed")
    resp = await client.get(url, follow_redirects=False)   # don't follow redirects
    return resp.json()
```

---

## 12. Structured Audit Logging

```python
import structlog

security_log = structlog.get_logger("security")

# Log: auth failures, 403s, sensitive mutations
# Do NOT log: passwords, raw tokens, JWTs, PII beyond what's audit-required

@app.delete("/documents/{doc_id}", status_code=204)
async def delete_document(doc_id: int, user: CurrentUser, session: SessionDep):
    doc = await session.get(Document, doc_id)
    if doc is None:
        security_log.warning("doc_not_found", user_id=user.id, doc_id=doc_id)
        raise HTTPException(404)
    if doc.owner_id != user.id:
        security_log.warning("unauthorized_delete", user_id=user.id, doc_id=doc_id,
                             owner_id=doc.owner_id)
        raise HTTPException(403)
    await session.delete(doc)
    await session.commit()
    security_log.info("doc_deleted", user_id=user.id, doc_id=doc_id)
```

---

## 13. Dependency Scanning (CI)

```yaml
# .github/workflows/security.yml
- name: Audit Python dependencies
  run: |
    pip install pip-audit
    pip-audit --requirement requirements.txt --output json --exit-code 1
```

Also: pin versions in `requirements.txt`; use Dependabot for automatic PR alerts.
