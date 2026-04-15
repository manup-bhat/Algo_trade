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

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import asyncio
import structlog
from contextlib import asynccontextmanager

log = structlog.get_logger(__name__)

from app.core.config import settings
from app.api.dashboard_router import router as dashboard_router
from app.api.v1.routes.auth import router as auth_router

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
        
    yield
    
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
