"""
app/main.py — FastAPI application entry point for the IVBS dashboard.

Serves:
  /                       → dashboard.html
                            Also catches Kite OAuth callback if request_token present
                            (handles both http://127.0.0.1/ and http://127.0.0.1:8000/)
  /api/v1/auth/login      → Kite login URL
  /api/v1/auth/callback   → Kite OAuth callback (receives request_token)
  /api/v1/auth/status     → current token status
  /api/v1/auth/token      → DELETE to revoke token
  /api/v1/status          → engine status, capital, daily P&L
  /api/v1/positions       → active positions
  /api/v1/signals         → recent scan signals
  /api/v1/orders          → today's orders
  /api/v1/emergency_stop  → POST to halt engine
  /api/v1/ws              → WebSocket real-time feed
  /docs                   → Swagger UI
  /health                 → health check

Kite Redirect URL note:
  If your Kite Developer Console has Redirect URL = "http://127.0.0.1" (port 80),
  run scripts/kite_port80_redirect.py (as Administrator) to forward callbacks to port 8000.
  This main.py also catches any request_token arriving at the root URL as a safety net.

Usage (from trading_bot/):
  python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import shlex
import subprocess
import sys
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import structlog

log = structlog.get_logger(__name__)

from app.core.config import settings
from app.api.dashboard_router import router as dashboard_router
from app.api.v1.routes.auth import router as auth_router

_ENGINE_AUTOSTART_LOCK_KEY = "engine:autostart:backend"
_ENGINE_AUTOSTART_LOCK_TTL_SECONDS = 60
_engine_process: subprocess.Popen | None = None
_engine_autostart_lock_token: str | None = None


def _build_engine_runner_command() -> list[str]:
    """Build the command used to launch engine.runner as a child process."""
    if settings.ENGINE_RUNNER_CMD.strip():
        return shlex.split(settings.ENGINE_RUNNER_CMD, posix=(os.name != "nt"))
    return [sys.executable, "-m", "engine.runner"]


async def _acquire_engine_autostart_lock(redis_client) -> bool:
    """Acquire a short-lived lock to avoid duplicate engine spawns on backend restarts."""
    global _engine_autostart_lock_token

    token = uuid4().hex
    acquired = await redis_client.set(
        _ENGINE_AUTOSTART_LOCK_KEY,
        token,
        nx=True,
        ex=_ENGINE_AUTOSTART_LOCK_TTL_SECONDS,
    )
    if acquired:
        _engine_autostart_lock_token = token
    return bool(acquired)


async def _release_engine_autostart_lock(redis_client) -> None:
    """Release lock only if this process owns it."""
    global _engine_autostart_lock_token

    if _engine_autostart_lock_token is None:
        return

    try:
        current = await redis_client.get(_ENGINE_AUTOSTART_LOCK_KEY)
        if current == _engine_autostart_lock_token:
            await redis_client.delete(_ENGINE_AUTOSTART_LOCK_KEY)
    except Exception as exc:
        log.debug("engine_autostart_lock_release_failed", error=str(exc))
    finally:
        _engine_autostart_lock_token = None


async def _release_engine_autostart_lock_from_pool() -> None:
    if _engine_autostart_lock_token is None:
        return
    try:
        from app.store.redis_client import get_redis

        await _release_engine_autostart_lock(get_redis())
    except Exception as exc:
        log.debug("engine_autostart_lock_release_skipped", error=str(exc))


async def _maybe_start_engine_subprocess() -> None:
    """Optionally spawn engine.runner when backend starts."""
    global _engine_process

    if not settings.AUTO_START_ENGINE_WITH_BACKEND:
        return

    try:
        from app.store.redis_client import get_redis
        from engine.store.redis_store import RedisStore
    except Exception as exc:
        log.warning("engine_autostart_import_failed", error=str(exc))
        return

    redis_client = get_redis()
    redis_store = RedisStore(redis_client)

    if not await redis_store.ping():
        log.warning(
            "engine_autostart_skipped_redis_unreachable",
            redis_url=settings.REDIS_URL,
        )
        return

    if not await _acquire_engine_autostart_lock(redis_client):
        log.info("engine_autostart_skipped_lock_held")
        return

    started = False
    try:
        existing_status = await redis_store.get_engine_status() or {}
        status_name = str(existing_status.get("status", "")).upper()
        if status_name and status_name not in {"OFFLINE", "EMERGENCY_STOP"}:
            log.info(
                "engine_autostart_skipped_engine_already_active",
                status=status_name,
            )
            return

        if _engine_process is not None and _engine_process.poll() is None:
            log.info(
                "engine_autostart_skipped_child_already_running",
                pid=_engine_process.pid,
            )
            return

        command = _build_engine_runner_command()
        project_root = Path(__file__).resolve().parent.parent
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

        _engine_process = subprocess.Popen(
            command,
            cwd=str(project_root),
            creationflags=creationflags,
        )
        started = True
        log.info(
            "engine_autostart_started",
            pid=_engine_process.pid,
            command=command,
        )
    except Exception as exc:
        log.error("engine_autostart_failed", error=str(exc))
    finally:
        if not started:
            await _release_engine_autostart_lock(redis_client)


async def _stop_engine_subprocess() -> None:
    """Optionally stop backend-started engine process on API shutdown."""
    global _engine_process

    proc = _engine_process
    _engine_process = None
    if proc is None:
        return

    if proc.poll() is not None:
        return

    if not settings.AUTO_STOP_ENGINE_WITH_BACKEND:
        log.info(
            "engine_autostart_leave_child_running",
            pid=proc.pid,
        )
        return

    log.info("engine_autostart_stopping", pid=proc.pid)
    try:
        proc.terminate()
        await asyncio.to_thread(proc.wait, 15)
    except Exception:
        log.warning("engine_autostart_force_kill", pid=proc.pid)
        try:
            proc.kill()
            await asyncio.to_thread(proc.wait, 5)
        except Exception:
            pass

# ── Port 80 Interceptor Background Task ──────────────────────────────────────

async def handle_port80_redirect(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    try:
        data = await reader.read(4096)
        http_request = data.decode("utf-8", errors="ignore")
        first_line = http_request.split("\r\n")[0] if "\r\n" in http_request else ""
        if first_line.startswith("GET"):
            parts = first_line.split()
            if len(parts) >= 2:
                path = parts[1]
                response = (
                    "HTTP/1.1 302 Found\r\n"
                    f"Location: http://{settings.API_HOST}:{settings.API_PORT}/api/v1/auth/callback{path.replace('/?','?',1) if path.startswith('/?') else path}\r\n"
                    "Content-Length: 0\r\n"
                    "Connection: close\r\n"
                    "\r\n"
                )
                writer.write(response.encode("utf-8"))
                await writer.drain()
                log.info("port80_redirect_success", path=path)
    except Exception:
        pass
    finally:
        writer.close()
        await writer.wait_closed()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Try to spin up background port 80 proxy listener
    server = None
    try:
        server = await asyncio.start_server(handle_port80_redirect, "127.0.0.1", 80)
        log.info("port80_listener_started", message="Listening internally for Kite OAuth callbacks")
    except Exception as exc:
        log.warning("port80_listener_failed", error=str(exc))

    await _maybe_start_engine_subprocess()

    try:
        yield
    finally:
        await _stop_engine_subprocess()
        await _release_engine_autostart_lock_from_pool()

        if server:
            server.close()
            await server.wait_closed()

# ── Application ───────────────────────────────────────────────────────────────
app = FastAPI(
    lifespan=lifespan,
    title="IVBS Trading Dashboard",
    description=(
        "Real-time monitoring for the Institutional Volume Breakout Strategy engine. "
        "Authenticate via /api/v1/auth/login before starting the engine. "
        "See /api/v1/auth/status to check current token."
    ),
    version="4.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static files ──────────────────────────────────────────────────────────────
STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ── API Routes ────────────────────────────────────────────────────────────────
app.include_router(auth_router,      prefix="/api/v1/auth", tags=["auth"])
app.include_router(dashboard_router, prefix="/api/v1",      tags=["dashboard"])


# ── Root ──────────────────────────────────────────────────────────────────────
@app.get("/", include_in_schema=False)
async def serve_dashboard(request: Request):
    """
    Serve the trading dashboard.

    Safety net: Kite Developer Console only allows 'http://127.0.0.1' as Redirect URL
    (no port, no path). If the port-80 redirect script is not running, Zerodha may
    redirect to this URL instead of /api/v1/auth/callback. We detect the presence of
    request_token and forward it to the proper callback endpoint automatically.
    """
    if "request_token" in request.query_params:
        # Forward all Kite callback params to the proper auth callback
        qs = str(request.url.query)
        return RedirectResponse(f"/api/v1/auth/callback?{qs}", status_code=302)

    dashboard_path = STATIC_DIR / "dashboard.html"
    if dashboard_path.exists():
        return FileResponse(str(dashboard_path))
    return RedirectResponse("/docs")


@app.get("/health")
async def health_check():
    """Health check for monitoring / load balancers."""
    return {"status": "ok", "service": "ivbs-dashboard", "version": "4.0.0"}
