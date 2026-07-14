# Models & ORM Migration — Django ORM → SQLModel/SQLAlchemy

## Overview

Django ORM uses declarative models with implicit magic (managers, querysets, lazy loading).
SQLModel (built on SQLAlchemy + Pydantic) is explicit, type-safe, and async-capable.

---

## Field Type Mapping

| Django Field | SQLModel/SQLAlchemy | Notes |
|-------------|--------------------| ------|
| `CharField(max_length=N)` | `str = Field(max_length=N)` | SQLModel validates length |
| `TextField()` | `str = Field(default="")` | No max_length needed |
| `IntegerField()` | `int` | Direct type annotation |
| `BigIntegerField()` | `int = Field(sa_type=BigInteger)` | Explicit SA type |
| `FloatField()` | `float` | Direct |
| `DecimalField(max_digits, decimal_places)` | `Decimal = Field(max_digits=N, decimal_places=N)` | Import from `decimal` |
| `BooleanField(default=False)` | `bool = False` | Direct |
| `DateTimeField(auto_now_add=True)` | `datetime = Field(default_factory=datetime.utcnow)` | Or use `server_default` |
| `DateField()` | `date` | From `datetime` module |
| `UUIDField(default=uuid4)` | `uuid.UUID = Field(default_factory=uuid4)` | Import uuid4 |
| `JSONField()` | `dict = Field(default={}, sa_type=JSON)` | Or use `sa_column` |
| `EmailField()` | `EmailStr` | From `pydantic` — validation only |
| `SlugField()` | `str = Field(max_length=50, regex=r'^[-\w]+$')` | Add index |
| `URLField()` | `HttpUrl` or `str` | Pydantic `HttpUrl` for validation |
| `FileField()` / `ImageField()` | Store path as `str`; handle upload separately | Use `UploadFile` in routes |
| `ForeignKey(Model, on_delete=...)` | `Optional[int] = Field(foreign_key="table.id")` | + `Relationship()` |
| `ManyToManyField(Model)` | Link table + `Relationship()` | Explicit association table |
| `OneToOneField(Model)` | `int = Field(foreign_key="table.id", unique=True)` | + `Relationship()` |
| `AutoField` / `BigAutoField` | `int | None = Field(default=None, primary_key=True)` | DB generates it |
| `NullBooleanField` | `bool | None = None` | Deprecated in Django 4+ anyway |
| `PositiveIntegerField` | `int = Field(ge=0)` | Pydantic constraint |
| `choices=[(..)]` | `Literal["a", "b"]` or `Enum` | Type-safe in FastAPI |

---

## Model Conversion Examples

### Simple Django Model → SQLModel

**Django:**
```python
# django_app/apps/posts/models.py
from django.db import models
from django.contrib.auth.models import User

class Post(models.Model):
    title = models.CharField(max_length=200)
    content = models.TextField()
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name="posts")
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        db_table = "posts_post"  # Django's default table naming

    def __str__(self):
        return self.title
```

**SQLModel:**
```python
# fastapi_app/src/posts/models.py
from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel, Relationship


class Post(SQLModel, table=True):
    __tablename__ = "posts_post"  # Match Django's existing table name!

    id: int | None = Field(default=None, primary_key=True)
    title: str = Field(max_length=200, index=True)
    content: str = Field(default="")
    author_id: int = Field(foreign_key="auth_user.id")  # Django's auth_user table
    is_published: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships (not columns — just Python-side)
    author: Optional["User"] = Relationship(back_populates="posts")
```

### Key Differences to Note

1. **`__tablename__`**: Must match Django's existing table name (usually `appname_modelname`)
2. **`id` field**: Django auto-creates it; SQLModel needs it declared explicitly
3. **ForeignKey**: Django uses model reference; SQLModel uses `foreign_key="table.column"` string
4. **`auto_now`/`auto_now_add`**: Use `default_factory` or `server_default=text("NOW()")`
5. **`on_delete`**: Handled at DB level via `sa_column_kwargs={"ondelete": "CASCADE"}`

---

## Model Pattern: Base + Table + Schema Split

For FastAPI, split each Django model into multiple classes:

```python
# Base fields shared by all variants
class PostBase(SQLModel):
    title: str = Field(max_length=200)
    content: str = Field(default="")
    is_published: bool = Field(default=False)

# Table model (actual database table)
class Post(PostBase, table=True):
    __tablename__ = "posts_post"
    id: int | None = Field(default=None, primary_key=True)
    author_id: int = Field(foreign_key="auth_user.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

# Schema for creating (client sends this)
class PostCreate(PostBase):
    pass  # No id, no timestamps — server generates those

# Schema for updating (all fields optional)
class PostUpdate(SQLModel):
    title: str | None = None
    content: str | None = None
    is_published: bool | None = None

# Schema for API response (what clients receive)
class PostPublic(PostBase):
    id: int
    author_id: int
    created_at: datetime
    updated_at: datetime
```

---

## QuerySet → SQLModel Select Patterns

| Django QuerySet | SQLModel/SQLAlchemy | Notes |
|----------------|--------------------| ------|
| `Post.objects.all()` | `session.exec(select(Post)).all()` | |
| `Post.objects.filter(is_published=True)` | `session.exec(select(Post).where(Post.is_published == True)).all()` | |
| `Post.objects.get(id=1)` | `session.get(Post, 1)` | Returns `None` if not found |
| `Post.objects.get_or_404(id=1)` | `session.get(Post, 1)` + `raise HTTPException(404)` | Explicit |
| `Post.objects.filter(title__contains="x")` | `select(Post).where(Post.title.contains("x"))` | |
| `Post.objects.filter(title__icontains="x")` | `select(Post).where(Post.title.ilike(f"%x%"))` | |
| `Post.objects.filter(created_at__gte=date)` | `select(Post).where(Post.created_at >= date)` | |
| `Post.objects.exclude(is_published=False)` | `select(Post).where(Post.is_published != False)` | |
| `Post.objects.order_by("-created_at")` | `select(Post).order_by(Post.created_at.desc())` | |
| `Post.objects.first()` | `session.exec(select(Post).limit(1)).first()` | |
| `Post.objects.count()` | `session.exec(select(func.count()).select_from(Post)).one()` | |
| `Post.objects.filter().exists()` | `session.exec(select(Post).limit(1)).first() is not None` | |
| `Post.objects.values_list("id", flat=True)` | `session.exec(select(Post.id)).all()` | |
| `Post.objects.select_related("author")` | `select(Post).options(joinedload(Post.author))` | Eager load |
| `Post.objects.prefetch_related("tags")` | `select(Post).options(selectinload(Post.tags))` | For collections |
| `Post.objects.annotate(Count("comments"))` | `select(Post, func.count(Comment.id)).join(Comment).group_by(Post.id)` | |
| `Post.objects.aggregate(Avg("rating"))` | `session.exec(select(func.avg(Post.rating))).one()` | |
| `Post.objects[:10]` | `select(Post).limit(10)` | |
| `Post.objects[5:15]` | `select(Post).offset(5).limit(10)` | |
| `post.save()` | `session.add(post); session.commit(); session.refresh(post)` | Explicit |
| `post.delete()` | `session.delete(post); session.commit()` | Explicit |
| `Post.objects.bulk_create([...])` | `session.add_all([...]); session.commit()` | |
| `Post.objects.update(is_published=True)` | `session.exec(update(Post).where(...).values(is_published=True))` | Bulk update |

---

## Relationships & Foreign Keys

### ForeignKey (Many-to-One)

**Django:**
```python
class Comment(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="comments")
    text = models.TextField()
```

**SQLModel:**
```python
class Comment(SQLModel, table=True):
    __tablename__ = "posts_comment"
    id: int | None = Field(default=None, primary_key=True)
    post_id: int = Field(foreign_key="posts_post.id")
    text: str

    post: Optional["Post"] = Relationship(back_populates="comments")

# Add to Post model:
class Post(PostBase, table=True):
    ...
    comments: list["Comment"] = Relationship(back_populates="post")
```

### ManyToMany

**Django:**
```python
class Post(models.Model):
    tags = models.ManyToManyField("Tag", related_name="posts")
```

**SQLModel:**
```python
# Explicit link table (matches Django's auto-created table)
class PostTagLink(SQLModel, table=True):
    __tablename__ = "posts_post_tags"  # Match Django's M2M table name
    post_id: int = Field(foreign_key="posts_post.id", primary_key=True)
    tag_id: int = Field(foreign_key="posts_tag.id", primary_key=True)

class Post(SQLModel, table=True):
    __tablename__ = "posts_post"
    id: int | None = Field(default=None, primary_key=True)
    title: str
    tags: list["Tag"] = Relationship(back_populates="posts", link_model=PostTagLink)

class Tag(SQLModel, table=True):
    __tablename__ = "posts_tag"
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True)
    posts: list["Post"] = Relationship(back_populates="tags", link_model=PostTagLink)
```

---

## Database Session (Dependency)

Replace Django's implicit per-request connection with an explicit session dependency:

```python
# fastapi_app/database.py
from typing import Annotated
from fastapi import Depends
from sqlmodel import Session, create_engine
from .config import settings

engine = create_engine(settings.DATABASE_URL, echo=settings.DEBUG)

def get_session():
    with Session(engine) as session:
        yield session

SessionDep = Annotated[Session, Depends(get_session)]
```

Usage in routes:
```python
@router.get("/posts/{post_id}", response_model=PostPublic)
def get_post(post_id: int, session: SessionDep):
    post = session.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post
```

---

## Alembic Setup (Coexisting with Django Migrations)

```bash
pip install alembic
alembic init alembic
```

Configure `alembic/env.py`:
```python
from sqlmodel import SQLModel
from fastapi_app.src.posts.models import Post  # Import all models
from fastapi_app.config import settings

config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
target_metadata = SQLModel.metadata
```

**During transition**: Only use Alembic for NEW tables that Django doesn't manage.
Once a table is fully migrated to FastAPI, transfer migration ownership to Alembic.

---

## Django Table Naming Convention

Django names tables as `{app_label}_{model_name_lower}`. You MUST match this in SQLModel:

| Django App | Django Model | Table Name | SQLModel `__tablename__` |
|-----------|-------------|-----------|--------------------------|
| `auth` | `User` | `auth_user` | `"auth_user"` |
| `posts` | `Post` | `posts_post` | `"posts_post"` |
| `posts` | `Comment` | `posts_comment` | `"posts_comment"` |
| `users` | `Profile` | `users_profile` | `"users_profile"` |

If Django has `class Meta: db_table = "custom_name"`, use that instead.

---

## N+1 Prevention

Django's lazy loading hides N+1 queries. SQLModel/SQLAlchemy makes them explicit:

```python
# BAD: N+1 — each post.author triggers a query
posts = session.exec(select(Post)).all()
for post in posts:
    print(post.author.name)  # N additional queries!

# GOOD: Eager load with joinedload (single JOIN query)
from sqlalchemy.orm import joinedload
posts = session.exec(
    select(Post).options(joinedload(Post.author))
).all()

# GOOD: Eager load with selectinload (SELECT ... WHERE id IN (...))
from sqlalchemy.orm import selectinload
posts = session.exec(
    select(Post).options(selectinload(Post.comments))
).all()
```

**Rule of thumb:**
- `joinedload` for to-one relationships (ForeignKey)
- `selectinload` for to-many relationships (reverse FK, M2M)
