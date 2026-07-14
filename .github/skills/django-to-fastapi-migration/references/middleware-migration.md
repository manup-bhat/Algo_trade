# Middleware Migration — Django Middleware → FastAPI Middleware & Dependencies

## Overview

Django middleware is a class-based pipeline that processes every request/response globally.
FastAPI offers two patterns: ASGI middleware (global) and dependencies (per-route).
Choose based on scope.

---

## When to Use Middleware vs Dependencies

| Need | Use Middleware | Use Dependency |
|------|---------------|---------------|
| Runs on EVERY request | Yes | No |
| Adds response headers | Yes | Possible but awkward |
| Timing/logging | Yes | No |
| Authentication | Possible but not recommended | Yes (per-route) |
| Request validation/parsing | No | Yes |
| Database session | No | Yes (yield dependency) |
| CORS | Yes (built-in) | No |
| Rate limiting | Yes (`slowapi`) | Per-route possible |

---

## Django Middleware → FastAPI Mapping

| Django Middleware | FastAPI Equivalent |
|-----------------|-------------------|
| `SecurityMiddleware` | `app.add_middleware(TrustedHostMiddleware)` + headers middleware |
| `SessionMiddleware` | Not needed (stateless JWT) |
| `CsrfViewMiddleware` | Not needed for API (JWT replaces CSRF) |
| `AuthenticationMiddleware` | `Depends(get_current_user)` per route |
| `MessageMiddleware` | Not needed (API responses carry messages) |
| `CommonMiddleware` (APPEND_SLASH, etc.) | FastAPI handles trailing slashes via `redirect_slashes=True` |
| `CorsMiddleware` (django-cors-headers) | `CORSMiddleware` from `fastapi.middleware.cors` |
| `GZipMiddleware` | `GZipMiddleware` from `fastapi.middleware.gzip` |
| Custom logging middleware | `@app.middleware("http")` |
| Custom exception middleware | Exception handlers |

---

## Converting Custom Django Middleware

### Django Middleware Structure

```python
# Django middleware
class TimingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # BEFORE view (process_request)
        import time
        start = time.perf_counter()

        response = self.get_response(request)

        # AFTER view (process_response)
        duration = time.perf_counter() - start
        response["X-Request-Duration"] = str(duration)
        return response
```

### FastAPI Equivalent (Decorator Middleware)

```python
# fastapi_app/middleware.py
import time
from fastapi import FastAPI, Request

app = FastAPI()

@app.middleware("http")
async def timing_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start
    response.headers["X-Request-Duration"] = f"{duration:.4f}"
    return response
```

### FastAPI Equivalent (Class-Based — for complex middleware)

```python
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class TimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start
        response.headers["X-Request-Duration"] = f"{duration:.4f}"
        return response

# Register:
app.add_middleware(TimingMiddleware)
```

---

## CORS Migration

### Django (django-cors-headers)

```python
# settings.py
INSTALLED_APPS = [..., "corsheaders", ...]
MIDDLEWARE = ["corsheaders.middleware.CorsMiddleware", ...]

CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "https://myapp.com",
]
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = ["*"]
```

### FastAPI

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://myapp.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-Duration"],  # Custom headers visible to browser
)
```

**Warning**: Never use `allow_origins=["*"]` with `allow_credentials=True` — this is a security vulnerability.

---

## Security Headers Middleware

Django's `SecurityMiddleware` adds several security headers. Replicate in FastAPI:

```python
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Equivalent to Django's SecurityMiddleware settings
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

        return response

app.add_middleware(SecurityHeadersMiddleware)
```

Or use the `secure` library:
```python
pip install secure
```

```python
import secure

security_headers = secure.Secure()

@app.middleware("http")
async def set_security_headers(request: Request, call_next):
    response = await call_next(request)
    security_headers.framework.fastapi(response)
    return response
```

---

## Request Logging Middleware

### Django

```python
import logging
logger = logging.getLogger("django.request")

class RequestLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        logger.info(f"{request.method} {request.path} - User: {request.user}")
        response = self.get_response(request)
        logger.info(f"{request.method} {request.path} - Status: {response.status_code}")
        return response
```

### FastAPI

```python
import logging
import uuid
from fastapi import Request

logger = logging.getLogger("api.request")

@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    logger.info(
        f"[{request_id}] {request.method} {request.url.path} "
        f"- Client: {request.client.host}"
    )

    response = await call_next(request)

    logger.info(
        f"[{request_id}] {request.method} {request.url.path} "
        f"- Status: {response.status_code}"
    )
    response.headers["X-Request-ID"] = request_id
    return response
```

---

## Exception Handling (Replaces Django's Exception Middleware)

### Django

```python
class CustomExceptionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def process_exception(self, request, exception):
        if isinstance(exception, PermissionDenied):
            return JsonResponse({"error": "Forbidden"}, status=403)
        return None  # Let Django handle it
```

### FastAPI (Exception Handlers)

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

class BusinessLogicError(Exception):
    def __init__(self, message: str, code: str = "BUSINESS_ERROR"):
        self.message = message
        self.code = code

@app.exception_handler(BusinessLogicError)
async def business_logic_exception_handler(request: Request, exc: BusinessLogicError):
    return JSONResponse(
        status_code=422,
        content={"error": exc.code, "message": exc.message},
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "INTERNAL_ERROR", "message": "An unexpected error occurred"},
    )
```

---

## Middleware Execution Order

### Django (top to bottom in MIDDLEWARE list)

```python
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",      # 1st
    "corsheaders.middleware.CorsMiddleware",              # 2nd
    "django.middleware.common.CommonMiddleware",          # 3rd
    ...
]
```

### FastAPI (last added = outermost = runs first)

```python
# Execution order: SecurityHeaders → CORS → Timing → route
app.add_middleware(TimingMiddleware)          # 3rd added = innermost = runs last
app.add_middleware(CORSMiddleware, ...)      # 2nd added
app.add_middleware(SecurityHeadersMiddleware) # 1st added = outermost = runs first
```

**Important**: In FastAPI, `add_middleware` works as a stack — the last one added wraps
the outermost layer and runs first on requests.

---

## Request Size Limiting

### Django

```python
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 2621440  # 2.5MB
```

### FastAPI

```python
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_size: int = 10 * 1024 * 1024):
        super().__init__(app)
        self.max_size = max_size

    async def dispatch(self, request: Request, call_next) -> Response:
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.max_size:
            return JSONResponse(
                status_code=413,
                content={"detail": "Request body too large"},
            )
        return await call_next(request)

app.add_middleware(RequestSizeLimitMiddleware, max_size=10 * 1024 * 1024)
```

---

## Trusted Host / Allowed Hosts

### Django

```python
ALLOWED_HOSTS = ["myapp.com", "www.myapp.com", "localhost"]
```

### FastAPI

```python
from starlette.middleware.trustedhost import TrustedHostMiddleware

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["myapp.com", "www.myapp.com", "localhost"],
)
```
