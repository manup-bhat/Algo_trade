# Serializers → Pydantic — DRF Serializers to Pydantic v2 Models

## Overview

Django REST Framework serializers handle validation, deserialization, and serialization.
In FastAPI, Pydantic v2 models replace all of these concerns with better performance
(5-50× faster) and native type safety.

---

## Core Concept Mapping

| DRF Concept | Pydantic v2 Equivalent |
|------------|----------------------|
| `Serializer` | `BaseModel` |
| `ModelSerializer` | SQLModel base + separate schema classes |
| `serializer.is_valid()` | Automatic on request parsing (raises 422) |
| `serializer.errors` | Auto-generated error response |
| `serializer.data` | Return model instance (auto-serialized) |
| `serializer.save()` | Service layer logic |
| Field declarations | Type annotations |
| `required=True` | No default value on field |
| `required=False` | `field: type = default` or `field: type | None = None` |
| `read_only=True` | Omit from Input model, include in Output model |
| `write_only=True` | Include in Input model, omit from Output model |
| `source="nested.field"` | Computed field or `model_validator` |
| `SerializerMethodField` | `@computed_field` or `@property` |
| `validate_<field>()` | `@field_validator("field")` |
| `validate()` (object-level) | `@model_validator(mode="after")` |
| `to_representation()` | `model_serializer` or custom response model |
| `to_internal_value()` | `@model_validator(mode="before")` |
| Nested serializer | Nested Pydantic model |
| `many=True` | `list[Model]` type annotation |
| `context` | Not needed — use dependency injection |

---

## Basic Serializer Migration

### DRF Serializer

```python
from rest_framework import serializers

class PostSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    title = serializers.CharField(max_length=200)
    content = serializers.CharField(required=False, default="")
    is_published = serializers.BooleanField(default=False)
    author_name = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(read_only=True)

    def get_author_name(self, obj):
        return obj.author.get_full_name()

    def validate_title(self, value):
        if "spam" in value.lower():
            raise serializers.ValidationError("Title contains spam")
        return value

    def validate(self, data):
        if data.get("is_published") and not data.get("content"):
            raise serializers.ValidationError("Published posts must have content")
        return data
```

### Pydantic v2 Equivalent

```python
from pydantic import BaseModel, field_validator, model_validator, computed_field
from datetime import datetime


# Input model (what client sends — replaces serializer for create/update)
class PostCreate(BaseModel):
    title: str  # max_length validated by SQLModel Field, or add Field(max_length=200)
    content: str = ""
    is_published: bool = False

    @field_validator("title")
    @classmethod
    def title_no_spam(cls, v: str) -> str:
        if "spam" in v.lower():
            raise ValueError("Title contains spam")
        return v

    @model_validator(mode="after")
    def published_needs_content(self) -> "PostCreate":
        if self.is_published and not self.content:
            raise ValueError("Published posts must have content")
        return self


# Output model (what client receives — replaces serializer for response)
class PostPublic(BaseModel):
    id: int
    title: str
    content: str
    is_published: bool
    author_name: str  # Populated from service layer
    created_at: datetime

    model_config = {"from_attributes": True}  # Allows ORM object → Pydantic
```

---

## ModelSerializer → SQLModel + Schema Split

### DRF ModelSerializer

```python
from rest_framework import serializers
from .models import Post

class PostSerializer(serializers.ModelSerializer):
    class Meta:
        model = Post
        fields = ["id", "title", "content", "is_published", "author", "created_at"]
        read_only_fields = ["id", "author", "created_at"]
        extra_kwargs = {
            "content": {"required": False, "default": ""},
        }
```

### FastAPI Pattern (Separate Input/Output Models)

```python
from sqlmodel import SQLModel, Field
from datetime import datetime

# Shared base (DRY)
class PostBase(SQLModel):
    title: str = Field(max_length=200)
    content: str = ""
    is_published: bool = False

# Input: what the client sends to CREATE
class PostCreate(PostBase):
    pass  # Only writable fields

# Input: what the client sends to UPDATE (all optional)
class PostUpdate(SQLModel):
    title: str | None = None
    content: str | None = None
    is_published: bool | None = None

# Output: what the API returns (includes read-only fields)
class PostPublic(PostBase):
    id: int
    author_id: int
    created_at: datetime

    model_config = {"from_attributes": True}
```

**Key insight**: Instead of one serializer with `read_only_fields`, you create separate
models for input and output. This is more explicit and gives better auto-generated
API docs.

---

## Nested Serializers → Nested Models

### DRF

```python
class CommentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Comment
        fields = ["id", "text", "created_at"]

class PostDetailSerializer(serializers.ModelSerializer):
    comments = CommentSerializer(many=True, read_only=True)
    author = UserSerializer(read_only=True)

    class Meta:
        model = Post
        fields = ["id", "title", "content", "author", "comments"]
```

### Pydantic

```python
class CommentPublic(BaseModel):
    id: int
    text: str
    created_at: datetime
    model_config = {"from_attributes": True}

class UserPublic(BaseModel):
    id: int
    username: str
    model_config = {"from_attributes": True}

class PostDetail(BaseModel):
    id: int
    title: str
    content: str
    author: UserPublic
    comments: list[CommentPublic]
    model_config = {"from_attributes": True}
```

---

## SerializerMethodField → computed_field

### DRF

```python
class PostSerializer(serializers.ModelSerializer):
    word_count = serializers.SerializerMethodField()
    is_recent = serializers.SerializerMethodField()

    def get_word_count(self, obj):
        return len(obj.content.split())

    def get_is_recent(self, obj):
        from django.utils import timezone
        return (timezone.now() - obj.created_at).days < 7
```

### Pydantic

```python
from pydantic import computed_field
from datetime import datetime, timezone

class PostPublic(BaseModel):
    id: int
    title: str
    content: str
    created_at: datetime

    @computed_field
    @property
    def word_count(self) -> int:
        return len(self.content.split())

    @computed_field
    @property
    def is_recent(self) -> bool:
        return (datetime.now(timezone.utc) - self.created_at).days < 7

    model_config = {"from_attributes": True}
```

---

## Validators

### Field-Level Validation

**DRF:**
```python
def validate_email(self, value):
    if not value.endswith("@company.com"):
        raise serializers.ValidationError("Must be a company email")
    return value
```

**Pydantic:**
```python
from pydantic import field_validator

class UserCreate(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def must_be_company_email(cls, v: str) -> str:
        if not v.endswith("@company.com"):
            raise ValueError("Must be a company email")
        return v
```

### Object-Level Validation

**DRF:**
```python
def validate(self, attrs):
    if attrs["start_date"] > attrs["end_date"]:
        raise serializers.ValidationError("Start date must be before end date")
    return attrs
```

**Pydantic:**
```python
from pydantic import model_validator

class EventCreate(BaseModel):
    start_date: datetime
    end_date: datetime

    @model_validator(mode="after")
    def dates_are_valid(self) -> "EventCreate":
        if self.start_date > self.end_date:
            raise ValueError("Start date must be before end date")
        return self
```

---

## Handling `context` (Request-Dependent Validation)

### DRF (uses `self.context`)

```python
class PostSerializer(serializers.ModelSerializer):
    def validate(self, attrs):
        request = self.context["request"]
        if not request.user.is_staff and attrs.get("is_featured"):
            raise serializers.ValidationError("Only staff can feature posts")
        return attrs
```

### FastAPI (use dependency injection instead)

```python
# No context needed — the route function has access to everything
@router.post("/", response_model=PostPublic)
def create_post(
    data: PostCreate,
    session: SessionDep,
    user: CurrentUserDep,
):
    # Validation that depends on request context goes in service layer
    if data.is_featured and not user.is_staff:
        raise HTTPException(status_code=403, detail="Only staff can feature posts")
    return PostService.create(session, data, user)
```

---

## File Upload Fields

### DRF

```python
class AvatarSerializer(serializers.Serializer):
    file = serializers.ImageField(max_length=None, allow_empty_file=False)
```

### FastAPI

```python
from fastapi import UploadFile, File

@router.post("/avatar")
async def upload_avatar(
    file: UploadFile = File(..., description="User avatar image"),
    user: CurrentUserDep,
):
    # Validate MIME type (magic bytes, not extension)
    contents = await file.read(8192)  # Read first 8KB for magic bytes
    if not contents.startswith(b"\x89PNG") and not contents.startswith(b"\xff\xd8"):
        raise HTTPException(status_code=400, detail="Must be PNG or JPEG")
    await file.seek(0)  # Reset for full read

    # Save file
    ...
```

---

## Error Response Format

### DRF Default Error Format

```json
{
    "title": ["This field is required."],
    "content": ["Ensure this field has no more than 200 characters."]
}
```

### FastAPI/Pydantic Default (422 Validation Error)

```json
{
    "detail": [
        {
            "type": "missing",
            "loc": ["body", "title"],
            "msg": "Field required",
            "input": {}
        },
        {
            "type": "string_too_long",
            "loc": ["body", "content"],
            "msg": "String should have at most 200 characters",
            "input": "..."
        }
    ]
}
```

To match DRF's error format for backwards compatibility during migration:

```python
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

@app.exception_handler(RequestValidationError)
async def drf_compatible_validation_error(request, exc):
    """Format validation errors like DRF for backwards compatibility."""
    errors = {}
    for error in exc.errors():
        field = error["loc"][-1] if error["loc"] else "non_field_errors"
        errors.setdefault(field, []).append(error["msg"])
    return JSONResponse(status_code=400, content=errors)
```

---

## Quick Conversion Checklist

- [ ] Identify all DRF serializers in the project
- [ ] For each serializer, create: `{Model}Create`, `{Model}Update`, `{Model}Public`
- [ ] Convert `validate_<field>` → `@field_validator`
- [ ] Convert `validate()` → `@model_validator(mode="after")`
- [ ] Convert `SerializerMethodField` → `@computed_field`
- [ ] Add `model_config = {"from_attributes": True}` to output models
- [ ] Move context-dependent validation to service layer
- [ ] Update API response format if clients depend on DRF error structure
- [ ] Verify nested serializers → nested Pydantic models
- [ ] Test that validation errors return appropriate HTTP 422 responses
