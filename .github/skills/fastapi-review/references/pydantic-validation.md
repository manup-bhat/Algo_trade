# Pydantic v2 Validation Reference

## Separate Input and Output Models

Never return an ORM model directly — `response_model` is a filter, not just docs.

```python
# ❌ hashed_password leaks to client; client can set id/is_admin
@app.post("/users", response_model=UserTable)
async def create_user(user: UserTable): ...

# ✅ Distinct schemas own the trust boundary
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

class UserOut(BaseModel):
    id: int
    email: EmailStr
    model_config = ConfigDict(from_attributes=True)

@app.post("/users", response_model=UserOut, status_code=201)
async def create_user(payload: UserCreate, session: SessionDep): ...
```

---

## Separate Create vs Update Schemas

```python
# ❌ Every field required on PATCH
class ItemSchema(BaseModel):
    name: str
    price: float

# ✅ Update is partial; validators on both
class ItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    price: float = Field(gt=0)

class ItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    price: float | None = Field(default=None, gt=0)
```

---

## Use All Pydantic v2 Field Constraints

```python
from enum import StrEnum
from pydantic import AnyUrl, BaseModel, EmailStr, Field, field_validator

class MusicBand(StrEnum):     # StrEnum is cleaner than str + Enum
    AEROSMITH = "AEROSMITH"
    QUEEN = "QUEEN"

class UserCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=128)
    username: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9-_]+$")
    email: EmailStr
    age: int = Field(ge=18)
    favorite_band: MusicBand | None = None
    website: AnyUrl | None = None

    @field_validator("username", mode="after")
    @classmethod
    def no_admin_username(cls, v: str) -> str:
        if v.lower() == "admin":
            raise ValueError("Username 'admin' is reserved")
        return v
```

---

## Custom Base Model (Standardize Across App)

```python
from datetime import datetime
from zoneinfo import ZoneInfo
from pydantic import BaseModel, ConfigDict, field_serializer

class AppModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    @field_serializer("*", when_used="json", check_fields=False)
    def _serialize_datetimes(self, value):
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=ZoneInfo("UTC"))
            return value.strftime("%Y-%m-%dT%H:%M:%S%z")
        return value
```

---

## Validate at Boundary, Before DB Write

```python
# ❌ Negative quantity reaches the database
@app.post("/cart")
async def add_to_cart(item_id: int, quantity: int):
    await save(item_id, quantity)

# ✅ Rejected before handler body runs
class CartLine(BaseModel):
    item_id: int
    quantity: int = Field(gt=0, le=1000)

@app.post("/cart")
async def add_to_cart(line: CartLine): ...
```

---

## Decoupled BaseSettings Per Module

```python
# ❌ One giant global config is hard to test and share
class Settings(BaseSettings):
    database_url: str
    jwt_secret: str
    smtp_host: str
    ...

# ✅ Module-scoped settings
# src/auth/config.py
class AuthConfig(BaseSettings):
    JWT_ALG: str = "HS256"
    JWT_SECRET: str                     # required; fails at startup if absent
    JWT_EXP_MINUTES: int = 15
    REFRESH_TOKEN_EXP_DAYS: int = 30
    SECURE_COOKIES: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

auth_settings = AuthConfig()

# src/config.py  (global)
class Config(BaseSettings):
    DATABASE_URL: PostgresDsn
    REDIS_URL: RedisDsn
    CORS_ORIGINS: list[str]
    ENVIRONMENT: Environment = Environment.PRODUCTION
    SHOW_DOCS: bool = False

settings = Config()
```

---

## Hide Docs in Production

```python
app_configs: dict = {"title": "My API"}
if settings.ENVIRONMENT not in ("local", "staging"):
    app_configs["openapi_url"] = None   # disables /docs and /redoc

app = FastAPI(**app_configs)
```

---

## ValueErrors in Pydantic Become 422

```python
# field_validator raising ValueError → FastAPI returns 422 with detail
@field_validator("password", mode="after")
@classmethod
def strong_password(cls, v: str) -> str:
    if not re.search(r"[A-Z]", v):
        raise ValueError("Password must contain at least one uppercase letter")
    return v
```
