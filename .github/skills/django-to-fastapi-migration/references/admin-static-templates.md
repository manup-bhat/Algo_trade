# Admin, Static Files & Templates Migration

## Overview

Django provides a powerful admin panel, static file serving, and template rendering.
FastAPI has lighter alternatives for each. Choose based on your actual needs.

---

## Django Admin → SQLAdmin

### Why SQLAdmin?

| Feature | Django Admin | SQLAdmin |
|---------|-------------|---------|
| ORM Integration | Django ORM (tight) | SQLAlchemy/SQLModel |
| Async support | No | Yes |
| Customization | Complex (ModelAdmin) | Simpler (similar API) |
| Authentication | Django auth | Pluggable (any auth) |
| Deployment | Same app | Same app (mounted) |

### Installation

```bash
pip install sqladmin
```

### Setup

```python
# fastapi_app/admin.py
from sqladmin import Admin, ModelView
from fastapi import FastAPI
from .database import engine
from .src.posts.models import Post
from .src.auth.models import User


def setup_admin(app: FastAPI):
    admin = Admin(app, engine)

    class UserAdmin(ModelView, model=User):
        column_list = [User.id, User.username, User.email, User.is_active]
        column_searchable_list = [User.username, User.email]
        column_sortable_list = [User.id, User.username, User.date_joined]
        can_create = True
        can_edit = True
        can_delete = False  # Safety: don't allow user deletion from admin
        name = "User"
        name_plural = "Users"
        icon = "fa-solid fa-user"

    class PostAdmin(ModelView, model=Post):
        column_list = [Post.id, Post.title, Post.is_published, Post.created_at]
        column_searchable_list = [Post.title]
        column_sortable_list = [Post.id, Post.created_at]
        form_excluded_columns = [Post.created_at, Post.updated_at]
        name = "Post"
        name_plural = "Posts"
        icon = "fa-solid fa-newspaper"

    admin.add_view(UserAdmin)
    admin.add_view(PostAdmin)
```

```python
# main.py
from .admin import setup_admin

app = FastAPI()
setup_admin(app)  # Admin available at /admin
```

### SQLAdmin Authentication

```python
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request


class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        username = form.get("username")
        password = form.get("password")
        # Verify against your auth system
        user = authenticate_user(session, username, password)
        if user and user.is_staff:
            request.session.update({"admin_user": username})
            return True
        return False

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return "admin_user" in request.session


# Use it:
admin = Admin(app, engine, authentication_backend=AdminAuth(secret_key=settings.SECRET_KEY))
```

---

## Static Files

### Django Static Files

```python
# settings.py
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

# urls.py (dev only)
from django.conf import settings
from django.conf.urls.static import static
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
```

### FastAPI Static Files

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# Mount static files directory
app.mount("/static", StaticFiles(directory="static"), name="static")
```

For production, serve static files via nginx/CDN (same recommendation as Django):

```nginx
# nginx.conf
location /static/ {
    alias /app/static/;
    expires 30d;
    add_header Cache-Control "public, immutable";
}
```

---

## Media Files (User Uploads)

### Django Media Files

```python
# settings.py
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# models.py
class UserProfile(models.Model):
    avatar = models.ImageField(upload_to="avatars/")
```

### FastAPI File Uploads

```python
import os
import uuid
from fastapi import UploadFile, File, HTTPException
from pathlib import Path

UPLOAD_DIR = Path("media/avatars")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    user: CurrentUserDep = None,
):
    # Validate file type (magic bytes)
    content = await file.read(8192)
    if not (content.startswith(b"\x89PNG") or content.startswith(b"\xff\xd8")):
        raise HTTPException(400, "Only PNG/JPEG allowed")
    await file.seek(0)

    # Generate safe filename (NEVER use user-provided filename)
    ext = ".png" if content.startswith(b"\x89PNG") else ".jpg"
    filename = f"{uuid.uuid4()}{ext}"
    filepath = UPLOAD_DIR / filename

    # Save file
    with open(filepath, "wb") as f:
        while chunk := await file.read(8192):
            f.write(chunk)

    # Update user profile
    user.avatar_path = f"avatars/{filename}"
    session.add(user)
    session.commit()

    return {"avatar_url": f"/media/avatars/{filename}"}


# Serve media files (dev only — use nginx/S3 in production)
app.mount("/media", StaticFiles(directory="media"), name="media")
```

---

## Templates (Django Templates → Jinja2)

### When You Need Server-Side Rendering

Most Django-to-FastAPI migrations move to a separate frontend (React/Next.js).
But if you need server-rendered HTML:

### Django Template

```python
# views.py
from django.shortcuts import render

def post_detail(request, pk):
    post = Post.objects.get(pk=pk)
    return render(request, "posts/detail.html", {"post": post})
```

```html
<!-- templates/posts/detail.html -->
{% extends "base.html" %}
{% block content %}
<h1>{{ post.title }}</h1>
<p>{{ post.content }}</p>
<small>By {{ post.author.username }} on {{ post.created_at|date:"M d, Y" }}</small>
{% endblock %}
```

### FastAPI + Jinja2

```bash
pip install jinja2
```

```python
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

templates = Jinja2Templates(directory="templates")


@router.get("/posts/{post_id}", response_class=HTMLResponse)
def post_detail(request: Request, post_id: int, session: SessionDep):
    post = session.get(Post, post_id)
    if not post:
        raise HTTPException(404)
    return templates.TemplateResponse(
        request=request,
        name="posts/detail.html",
        context={"post": post},
    )
```

```html
<!-- templates/posts/detail.html -->
{% extends "base.html" %}
{% block content %}
<h1>{{ post.title }}</h1>
<p>{{ post.content }}</p>
<small>By {{ post.author.username }} on {{ post.created_at.strftime("%b %d, %Y") }}</small>
{% endblock %}
```

### Template Syntax Differences

| Django Template | Jinja2 | Notes |
|----------------|--------|-------|
| `{{ var }}` | `{{ var }}` | Same |
| `{% if %}` | `{% if %}` | Same |
| `{% for x in list %}` | `{% for x in list %}` | Same |
| `{{ var\|date:"Y-m-d" }}` | `{{ var.strftime("%Y-%m-%d") }}` | Python methods |
| `{{ var\|default:"N/A" }}` | `{{ var \| default("N/A") }}` | Filter syntax |
| `{% url "name" pk %}` | Use `url_for()` or hardcode | No reverse by default |
| `{% csrf_token %}` | Not needed (JWT auth) | Or add manually |
| `{% include "partial.html" %}` | `{% include "partial.html" %}` | Same |
| `{% block name %}` | `{% block name %}` | Same |
| `{{ var\|safe }}` | `{{ var \| safe }}` | Same (autoescaping on by default) |
| `{% load static %}` | Not needed | Use `/static/...` paths directly |

---

## Django Forms → FastAPI Form Handling

### Django Form

```python
from django import forms

class ContactForm(forms.Form):
    name = forms.CharField(max_length=100)
    email = forms.EmailField()
    message = forms.CharField(widget=forms.Textarea)
```

### FastAPI Form (API-style — JSON body)

```python
from pydantic import BaseModel, EmailStr

class ContactForm(BaseModel):
    name: str
    email: EmailStr
    message: str

@router.post("/contact")
def submit_contact(form: ContactForm):
    # Process form
    ...
```

### FastAPI Form (HTML form — multipart/form-data)

```python
from fastapi import Form

@router.post("/contact")
def submit_contact(
    name: str = Form(..., max_length=100),
    email: str = Form(...),
    message: str = Form(...),
):
    # Process form
    ...
```

---

## Decision Guide

| Django Feature | FastAPI Replacement | When to Use |
|---------------|--------------------| ------------|
| Django Admin | SQLAdmin | Need CRUD admin panel |
| Django Admin | No admin (API-only) | Frontend handles all UI |
| Static files | `StaticFiles` mount (dev) / nginx/CDN (prod) | Always |
| Media uploads | `UploadFile` + S3/local storage | When users upload files |
| Django Templates | Jinja2Templates | Server-rendered pages needed |
| Django Templates | None (separate frontend) | React/Vue/Next.js frontend |
| Django Forms | Pydantic models (JSON) | API consumers |
| Django Forms | `Form(...)` parameters | HTML form submissions |
| `collectstatic` | Build step copies to nginx/CDN | Production deployment |
