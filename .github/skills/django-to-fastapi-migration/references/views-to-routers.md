# Views → Routers Migration — Django Views to FastAPI Path Operations

## Overview

Django views (function-based, class-based, DRF ViewSets) map to FastAPI path operations
organized in `APIRouter` instances. The key shift: Django uses URL conf + view functions;
FastAPI uses decorator-based routing with type-annotated parameters.

---

## Function-Based Views → Path Operations

### Simple GET View

**Django:**
```python
# django_app/apps/posts/views.py
from django.http import JsonResponse
from .models import Post

def post_list(request):
    if request.method != "GET":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    posts = Post.objects.filter(is_published=True).values("id", "title", "created_at")
    return JsonResponse({"posts": list(posts)})
```

```python
# django_app/apps/posts/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path("api/posts/", views.post_list, name="post-list"),
]
```

**FastAPI:**
```python
# fastapi_app/src/posts/router.py
from fastapi import APIRouter, Query
from typing import Annotated
from .schemas import PostPublic
from .service import PostService
from ...database import SessionDep

router = APIRouter()

@router.get("/", response_model=list[PostPublic])
def list_posts(
    session: SessionDep,
    offset: int = 0,
    limit: Annotated[int, Query(le=100)] = 20,
):
    return PostService.list_published(session, offset=offset, limit=limit)
```

### POST/Create View

**Django:**
```python
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
import json

@csrf_exempt
@login_required
def post_create(request):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    data = json.loads(request.body)
    post = Post.objects.create(
        title=data["title"],
        content=data.get("content", ""),
        author=request.user,
    )
    return JsonResponse({"id": post.id, "title": post.title}, status=201)
```

**FastAPI:**
```python
from fastapi import APIRouter, status
from .schemas import PostCreate, PostPublic
from .service import PostService
from ..auth.dependencies import CurrentUserDep
from ...database import SessionDep

router = APIRouter()

@router.post("/", response_model=PostPublic, status_code=status.HTTP_201_CREATED)
def create_post(
    post_data: PostCreate,    # Auto-validated from request body (JSON)
    session: SessionDep,
    current_user: CurrentUserDep,  # Replaces @login_required
):
    return PostService.create(session, post_data, author=current_user)
```

---

## URL Pattern → Path Parameter Conversion

| Django URL Pattern | FastAPI Path | Notes |
|-------------------|-------------|-------|
| `path("posts/", view)` | `@router.get("/posts/")` | Static path |
| `path("posts/<int:pk>/", view)` | `@router.get("/posts/{pk}")` | Path param (auto int validation) |
| `path("posts/<slug:slug>/", view)` | `@router.get("/posts/{slug}")` | Add regex with `Path(regex=...)` |
| `path("posts/<uuid:id>/", view)` | `@router.get("/posts/{id}")` with `id: UUID` | Type annotation validates |
| `re_path(r"^posts/(?P<year>\d{4})/")` | `@router.get("/posts/{year}")` with `year: int = Path(ge=1900)` | Constraints via `Path()` |

### Query Parameters

**Django:**
```python
def post_list(request):
    page = int(request.GET.get("page", 1))
    search = request.GET.get("search", "")
    category = request.GET.get("category")
```

**FastAPI:**
```python
@router.get("/posts/")
def list_posts(
    page: int = 1,                              # Default value = optional
    search: str = "",                            # Default value = optional
    category: str | None = None,                 # None default = optional
    limit: Annotated[int, Query(ge=1, le=100)] = 20,  # With validation
):
    ...
```

---

## Class-Based Views → Router Functions

### Django CBV (DetailView-style)

**Django:**
```python
from django.views import View
from django.http import JsonResponse

class PostDetailView(View):
    def get(self, request, pk):
        try:
            post = Post.objects.get(pk=pk, is_published=True)
        except Post.DoesNotExist:
            return JsonResponse({"error": "Not found"}, status=404)
        return JsonResponse({"id": post.id, "title": post.title})

    def put(self, request, pk):
        # update logic
        ...

    def delete(self, request, pk):
        # delete logic
        ...
```

**FastAPI (explicit functions — preferred over classes):**
```python
@router.get("/{post_id}", response_model=PostPublic)
def get_post(post_id: int, session: SessionDep):
    post = session.get(Post, post_id)
    if not post or not post.is_published:
        raise HTTPException(status_code=404, detail="Post not found")
    return post

@router.put("/{post_id}", response_model=PostPublic)
def update_post(post_id: int, data: PostUpdate, session: SessionDep, user: CurrentUserDep):
    return PostService.update(session, post_id, data, user)

@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(post_id: int, session: SessionDep, user: CurrentUserDep):
    PostService.delete(session, post_id, user)
```

---

## DRF ViewSet → FastAPI Router (Full CRUD)

### Django REST Framework ViewSet

**Django DRF:**
```python
from rest_framework import viewsets, permissions
from .models import Post
from .serializers import PostSerializer

class PostViewSet(viewsets.ModelViewSet):
    queryset = Post.objects.all()
    serializer_class = PostSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == "list":
            return qs.filter(is_published=True)
        return qs
```

```python
# urls.py
from rest_framework.routers import DefaultRouter
router = DefaultRouter()
router.register("posts", PostViewSet)
```

**FastAPI equivalent:**
```python
# fastapi_app/src/posts/router.py
from fastapi import APIRouter, HTTPException, Query, status
from typing import Annotated
from .models import Post
from .schemas import PostCreate, PostUpdate, PostPublic
from .service import PostService
from ..auth.dependencies import CurrentUserDep, OptionalUserDep
from ...database import SessionDep

router = APIRouter(prefix="/posts", tags=["posts"])


@router.get("/", response_model=list[PostPublic])
def list_posts(
    session: SessionDep,
    offset: int = 0,
    limit: Annotated[int, Query(le=100)] = 20,
):
    """List published posts (public)."""
    return PostService.list_published(session, offset=offset, limit=limit)


@router.get("/{post_id}", response_model=PostPublic)
def get_post(post_id: int, session: SessionDep):
    """Retrieve a single post."""
    post = PostService.get_or_404(session, post_id)
    return post


@router.post("/", response_model=PostPublic, status_code=status.HTTP_201_CREATED)
def create_post(data: PostCreate, session: SessionDep, user: CurrentUserDep):
    """Create a new post (authenticated)."""
    return PostService.create(session, data, author=user)


@router.patch("/{post_id}", response_model=PostPublic)
def update_post(
    post_id: int, data: PostUpdate, session: SessionDep, user: CurrentUserDep
):
    """Update a post (owner only)."""
    return PostService.update(session, post_id, data, user)


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(post_id: int, session: SessionDep, user: CurrentUserDep):
    """Delete a post (owner only)."""
    PostService.delete(session, post_id, user)
```

### Service Layer (Business Logic)

```python
# fastapi_app/src/posts/service.py
from fastapi import HTTPException
from sqlmodel import select
from .models import Post
from .schemas import PostCreate, PostUpdate


class PostService:
    @staticmethod
    def list_published(session, offset: int = 0, limit: int = 20) -> list[Post]:
        stmt = (
            select(Post)
            .where(Post.is_published == True)
            .order_by(Post.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return session.exec(stmt).all()

    @staticmethod
    def get_or_404(session, post_id: int) -> Post:
        post = session.get(Post, post_id)
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        return post

    @staticmethod
    def create(session, data: PostCreate, author) -> Post:
        post = Post.model_validate(data, update={"author_id": author.id})
        session.add(post)
        session.commit()
        session.refresh(post)
        return post

    @staticmethod
    def update(session, post_id: int, data: PostUpdate, user) -> Post:
        post = PostService.get_or_404(session, post_id)
        if post.author_id != user.id:
            raise HTTPException(status_code=403, detail="Not the post owner")
        post_data = data.model_dump(exclude_unset=True)
        post.sqlmodel_update(post_data)
        session.add(post)
        session.commit()
        session.refresh(post)
        return post

    @staticmethod
    def delete(session, post_id: int, user) -> None:
        post = PostService.get_or_404(session, post_id)
        if post.author_id != user.id:
            raise HTTPException(status_code=403, detail="Not the post owner")
        session.delete(post)
        session.commit()
```

---

## Pagination Patterns

### Django (DRF built-in)

```python
# DRF settings.py
REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 20,
}
```

### FastAPI (explicit — no magic)

```python
from fastapi import Query
from typing import Annotated, Generic, TypeVar
from pydantic import BaseModel

T = TypeVar("T")

class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    offset: int
    limit: int

@router.get("/", response_model=PaginatedResponse[PostPublic])
def list_posts(
    session: SessionDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
):
    total = session.exec(select(func.count()).select_from(Post)).one()
    items = session.exec(
        select(Post).offset(offset).limit(limit).order_by(Post.created_at.desc())
    ).all()
    return PaginatedResponse(items=items, total=total, offset=offset, limit=limit)
```

---

## Response Handling

| Django Pattern | FastAPI Equivalent |
|---------------|-------------------|
| `JsonResponse(data)` | Return dict/model (auto-serialized) |
| `JsonResponse(data, status=201)` | `status_code=201` in decorator |
| `HttpResponse(status=204)` | Return `None` with `status_code=204` |
| `HttpResponseRedirect(url)` | `from fastapi.responses import RedirectResponse` |
| `StreamingHttpResponse` | `StreamingResponse` |
| `FileResponse` (Django 4.1+) | `from fastapi.responses import FileResponse` |
| Custom content type | `Response(content=..., media_type="text/xml")` |

---

## Router Organization (Bigger Applications)

```python
# fastapi_app/main.py
from fastapi import FastAPI
from .src.posts.router import router as posts_router
from .src.users.router import router as users_router
from .src.comments.router import router as comments_router
from .src.auth.router import router as auth_router

app = FastAPI()

app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(users_router, prefix="/api/users", tags=["users"])
app.include_router(posts_router, prefix="/api/posts", tags=["posts"])
app.include_router(comments_router, prefix="/api/comments", tags=["comments"])
```

This replaces Django's `include()` URL conf pattern:
```python
# Django urls.py equivalent
urlpatterns = [
    path("api/auth/", include("apps.auth.urls")),
    path("api/users/", include("apps.users.urls")),
    path("api/posts/", include("apps.posts.urls")),
]
```

---

## Common Gotchas

1. **Django's `request.data` (DRF)** → FastAPI auto-parses body into typed parameter
2. **`request.query_params`** → Function parameters with defaults
3. **`request.FILES`** → `UploadFile` parameter
4. **`@api_view(["GET", "POST"])`** → Separate functions per method (cleaner)
5. **`@action(detail=True)`** → Just another `@router.post("/{id}/action")` endpoint
6. **`self.get_object()`** → `session.get(Model, id)` + 404 check
7. **`permission_classes`** → `Depends()` on the function
8. **Throttling** → `slowapi` rate limiter
