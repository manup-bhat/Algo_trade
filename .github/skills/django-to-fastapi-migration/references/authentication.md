# Authentication Migration — Django Auth → FastAPI OAuth2/JWT

## Overview

Django uses session-based authentication with CSRF protection. FastAPI typically uses
stateless JWT tokens with OAuth2 Bearer scheme. The critical challenge: migrating users
without forcing password resets.

---

## Architecture Comparison

| Aspect | Django | FastAPI |
|--------|--------|---------|
| Default mechanism | Session cookies + CSRF | JWT Bearer tokens |
| State | Server-side (DB session store) | Stateless (token contains claims) |
| Password hashing | PBKDF2 (default), bcrypt, Argon2 | pwdlib with Argon2 (recommended) |
| Auth middleware | `AuthenticationMiddleware` (every request) | `Depends(get_current_user)` (per-route) |
| Permission system | `@login_required`, `@permission_required` | `Depends(require_role(...))` |
| User model | `django.contrib.auth.models.User` | Custom SQLModel `User` |
| Token library | N/A (session-based) | `PyJWT` |

---

## Password Hash Compatibility (CRITICAL)

Django's default password hasher produces hashes like:
```
pbkdf2_sha256$600000$salt$hash
```

**pwdlib can verify these!** This means zero-downtime migration — users don't need to reset passwords.

```python
# fastapi_app/src/auth/password.py
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

# Custom Django PBKDF2 hasher for pwdlib
class DjangoPBKDF2Hasher:
    """Verifies Django's default PBKDF2-SHA256 hashes."""

    def identify(self, hash: str) -> bool:
        return hash.startswith("pbkdf2_sha256$")

    def verify(self, password: str, hash: str) -> bool:
        import hashlib
        import base64
        # Parse Django hash format: algorithm$iterations$salt$hash
        parts = hash.split("$")
        if len(parts) != 4:
            return False
        algorithm, iterations, salt, expected_hash = parts
        iterations = int(iterations)

        # Compute PBKDF2
        dk = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            iterations,
        )
        computed = base64.b64encode(dk).decode("ascii")
        # Constant-time comparison
        import hmac
        return hmac.compare_digest(computed, expected_hash)

    def hash(self, password: str) -> str:
        # We don't create new Django hashes — new passwords use Argon2
        raise NotImplementedError("Use Argon2 for new passwords")


# Configure password hash to support BOTH Django legacy and new Argon2
password_hash = PasswordHash((
    DjangoPBKDF2Hasher(),  # Can VERIFY old Django hashes
    Argon2Hasher(),         # Creates NEW hashes with Argon2
))

# Pre-compute dummy hash for timing-attack prevention
DUMMY_HASH = Argon2Hasher().hash("dummypassword")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against either Django PBKDF2 or Argon2 hash."""
    return password_hash.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    """Hash new password with Argon2 (current best practice)."""
    return Argon2Hasher().hash(password)


def needs_rehash(hashed_password: str) -> bool:
    """Check if password should be rehashed (e.g., still using Django PBKDF2)."""
    return hashed_password.startswith("pbkdf2_sha256$")
```

### Transparent Password Upgrade Strategy

On each successful login, check if the hash is a legacy Django hash and upgrade it:

```python
def authenticate_user(session, username: str, password: str) -> User | None:
    user = get_user_by_username(session, username)
    if not user:
        # Prevent timing attacks
        verify_password(password, DUMMY_HASH)
        return None

    if not verify_password(password, user.hashed_password):
        return None

    # Transparent upgrade: rehash with Argon2 if still using Django PBKDF2
    if needs_rehash(user.hashed_password):
        user.hashed_password = hash_password(password)
        session.add(user)
        session.commit()

    return user
```

---

## JWT Token Implementation

```python
# fastapi_app/src/auth/jwt.py
from datetime import datetime, timedelta, timezone
import jwt
from ..config import settings

ALGORITHM = "HS256"


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=30))
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=7)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and verify JWT. Raises InvalidTokenError on failure."""
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
```

---

## Auth Dependencies (Replacing Django Decorators)

### `@login_required` → `Depends(get_current_user)`

**Django:**
```python
from django.contrib.auth.decorators import login_required

@login_required
def my_view(request):
    user = request.user
    ...
```

**FastAPI:**
```python
# fastapi_app/src/auth/dependencies.py
from typing import Annotated
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from .jwt import decode_token
from .models import User
from ...database import SessionDep

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: SessionDep,
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except InvalidTokenError:
        raise credentials_exception

    user = session.exec(
        select(User).where(User.username == username)
    ).first()
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user


# Reusable type alias for dependency injection
CurrentUserDep = Annotated[User, Depends(get_current_user)]


# Optional user (for endpoints that work with or without auth)
async def get_optional_user(
    token: Annotated[str | None, Depends(OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False))],
    session: SessionDep,
) -> User | None:
    if token is None:
        return None
    try:
        return await get_current_user(token, session)
    except HTTPException:
        return None

OptionalUserDep = Annotated[User | None, Depends(get_optional_user)]
```

### `@permission_required` → `Depends(require_role(...))`

**Django:**
```python
from django.contrib.auth.decorators import permission_required

@permission_required("posts.can_publish")
def publish_post(request, pk):
    ...
```

**FastAPI:**
```python
# fastapi_app/src/auth/dependencies.py
def require_role(*roles: str):
    """Dependency factory for role-based access control."""
    async def role_checker(current_user: CurrentUserDep) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user
    return role_checker

# Usage:
@router.post("/{post_id}/publish")
def publish_post(
    post_id: int,
    session: SessionDep,
    user: Annotated[User, Depends(require_role("admin", "editor"))],
):
    ...
```

### `IsAuthenticatedOrReadOnly` → Conditional Dependency

**Django DRF:**
```python
permission_classes = [IsAuthenticatedOrReadOnly]
```

**FastAPI:**
```python
# Read endpoints — no auth required
@router.get("/posts/")
def list_posts(session: SessionDep):
    ...

# Write endpoints — auth required (just add the dependency)
@router.post("/posts/")
def create_post(session: SessionDep, user: CurrentUserDep):
    ...
```

---

## Auth Router (Login/Token Endpoints)

```python
# fastapi_app/src/auth/router.py
from datetime import timedelta
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from .schemas import Token, TokenRefresh
from .service import authenticate_user
from .jwt import create_access_token, create_refresh_token, decode_token
from ...database import SessionDep
from ..config import settings

router = APIRouter()


@router.post("/token", response_model=Token)
def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: SessionDep,
):
    """OAuth2 compatible token endpoint (replaces Django's login view)."""
    user = authenticate_user(session, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    refresh_token = create_refresh_token(data={"sub": user.username})
    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )


@router.post("/token/refresh", response_model=Token)
def refresh_token(body: TokenRefresh, session: SessionDep):
    """Get new access token using refresh token."""
    try:
        payload = decode_token(body.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=400, detail="Invalid token type")
        username = payload.get("sub")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user = get_user_by_username(session, username)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    access_token = create_access_token(data={"sub": user.username})
    return Token(access_token=access_token, token_type="bearer")
```

---

## User Model Migration

**Django `auth_user` table → SQLModel User:**

```python
# fastapi_app/src/auth/models.py
from sqlmodel import SQLModel, Field
from datetime import datetime


class User(SQLModel, table=True):
    __tablename__ = "auth_user"  # Use Django's existing table!

    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True, max_length=150)
    email: str = Field(default="", max_length=254)
    first_name: str = Field(default="", max_length=150)
    last_name: str = Field(default="", max_length=150)

    # Django stores password hash in this field
    password: str = Field(max_length=128)  # Django's "password" column

    is_active: bool = Field(default=True)
    is_staff: bool = Field(default=False)
    is_superuser: bool = Field(default=False)
    date_joined: datetime = Field(default_factory=datetime.utcnow)
    last_login: datetime | None = Field(default=None)

    @property
    def hashed_password(self) -> str:
        """Alias for Django's 'password' field which stores the hash."""
        return self.password

    @hashed_password.setter
    def hashed_password(self, value: str):
        self.password = value
```

---

## Migration Checklist for Auth

- [ ] User model SQLModel matches Django's `auth_user` table
- [ ] Password verification works with existing Django PBKDF2 hashes
- [ ] New passwords are hashed with Argon2
- [ ] Legacy hashes are transparently upgraded on login
- [ ] JWT token creation and verification works
- [ ] `get_current_user` dependency correctly decodes tokens
- [ ] Role/permission checks migrated from Django's `Permission` model
- [ ] Token refresh endpoint works
- [ ] Timing attack prevention (dummy hash on unknown usernames)
- [ ] Contract tests: same user can log in via both Django and FastAPI
- [ ] CORS configured for frontend token-based auth
- [ ] Swagger UI `/docs` shows "Authorize" button with OAuth2 flow
