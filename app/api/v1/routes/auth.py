"""
app/api/v1/routes/auth.py — Kite Connect OAuth 2-step login flow.

Official Kite Connect v3 Login Flow (per https://kite.trade/docs/connect/v3/user/):

  Step 1 — Login URL
    Navigate browser to:
      https://kite.zerodha.com/connect/login?v=3&api_key=<API_KEY>

  Step 2 — User Login on Zerodha
    User enters credentials + TOTP on Zerodha's website.
    Zerodha redirects browser to your registered Redirect URL with:
      ?action=login&type=login&status=success&request_token=<TOKEN>

  Step 3 — Token Exchange (backend)
    POST to https://api.kite.trade/session/token with:
      api_key=xxx  request_token=yyy  checksum=zzz
    where checksum = SHA-256(api_key + request_token + api_secret)
    Response contains access_token (valid until 6 AM next day).

  Step 4 — Subsequent API calls signed with:
    Authorization: token api_key:access_token

IMPORTANT: Your Kite Developer Console has Redirect URL = "http://127.0.0.1"
  Zerodha will redirect to http://127.0.0.1/?... (port 80, no path)
  Run scripts/kite_port80_redirect.py (as Administrator) to catch this and
  forward to http://127.0.0.1:8000/api/v1/auth/callback

Endpoints:
  GET  /api/v1/auth/login      — returns the Kite login URL
  GET  /api/v1/auth/callback   — receives request_token, exchanges for access_token
  GET  /api/v1/auth/status     — checks current saved token
  DELETE /api/v1/auth/token    — deletes saved token (force re-login)
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytz
import structlog
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

log = structlog.get_logger(__name__)
IST_TZ = pytz.timezone("Asia/Kolkata")
router = APIRouter()

# Injected by runner.py via dashboard_router.set_dependencies()
_redis_store: Any = None


def set_redis(rs: Any) -> None:
    global _redis_store
    _redis_store = rs


# ── Step 1: Return Kite Login URL ─────────────────────────────────────────────

@router.get("/login", summary="Get Kite login URL")
async def get_login_url():
    """
    Returns the Kite Connect login URL.
    Open this in your browser to authenticate with your Zerodha account.
    """
    from app.core.config import settings

    login_url = f"https://kite.zerodha.com/connect/login?v=3&api_key={settings.KITE_API_KEY}"
    return {
        "login_url": login_url,
        "redirect_url_configured": settings.KITE_REDIRECT_URL,
        "steps": [
            "1. Open login_url in your browser",
            "2. Login with Zerodha user ID + password + TOTP",
            "3. Zerodha redirects browser to your Redirect URL with ?request_token=...",
            "4. Token is automatically exchanged and saved — engine can start",
        ],
        "note": (
            "If your redirect URL is http://127.0.0.1 (port 80), "
            "run scripts/kite_port80_redirect.py as Administrator first."
        ),
    }


# ── Step 1b: Direct browser redirect to Kite login ────────────────────────────

@router.get("/login-redirect", summary="Redirect browser to Kite login page")
async def login_redirect():
    """
    302 redirect to Kite Connect login URL.

    The dashboard calls window.open('/api/v1/auth/login-redirect', '_blank')
    **synchronously** inside a click handler so the browser's popup-blocker
    never fires.  Doing window.open() after an await fetch() puts it outside
    the user-gesture context, causing it to be silently blocked.
    """
    from fastapi.responses import RedirectResponse
    from app.core.config import settings

    login_url = (
        f"https://kite.zerodha.com/connect/login"
        f"?v=3&api_key={settings.KITE_API_KEY}"
    )
    return RedirectResponse(login_url, status_code=302)


# ── Step 2: OAuth Callback (receives request_token from Zerodha) ───────────────

@router.get("/callback", response_class=HTMLResponse, summary="Kite OAuth callback")
async def kite_callback(request: Request):
    """
    Zerodha redirects the browser here after a successful login.
    Extracts request_token from query params, exchanges it for access_token,
    and saves to .kite_token file + Redis.

    Per Kite docs, callback URL receives:
      ?action=login&type=login&status=success&request_token=<TOKEN>
    """
    from app.core.config import settings

    params = dict(request.query_params)
    request_token = params.get("request_token")
    status = params.get("status", "")

    # ── Validate params ───────────────────────────────────────────────
    if not request_token:
        return _error_page(
            "No Request Token",
            "The request_token is missing from the callback URL.<br><br>"
            "This usually means the Redirect URL in your Kite Developer Console "
            "is not pointing to this server. "
            f"Current params received: {params}"
        )

    # Kite sends status=success on success, status=error on failure
    if status == "error":
        error_msg = params.get("message", "Unknown error")
        return _error_page("Zerodha Login Failed", f"Zerodha returned an error: {error_msg}")

    # ── Exchange request_token → access_token ─────────────────────────
    try:
        from kiteconnect import KiteConnect  # type: ignore[import-untyped]

        kite = KiteConnect(api_key=settings.KITE_API_KEY)
        # generate_session internally computes:
        #   checksum = SHA256(api_key + request_token + api_secret)
        # and POSTs to https://api.kite.trade/session/token
        session_data = kite.generate_session(
            request_token=request_token,
            api_secret=settings.KITE_API_SECRET,
        )

    except Exception as exc:
        err_str = str(exc)
        log.error("kite_session_generation_failed", error=err_str)

        # Common error: request_token already used (each token is one-time only)
        if "Invalid" in err_str or "token" in err_str.lower():
            return _error_page(
                "Token Exchange Failed",
                f"{err_str}<br><br>"
                "<strong>Note:</strong> Each request_token is one-time use only. "
                "If you refreshed the page or this is your second attempt, "
                "you must log in again from scratch."
            )
        return _error_page("Token Exchange Failed", err_str)

    access_token = session_data.get("access_token")
    user_id      = session_data.get("user_id", "unknown")
    user_name    = session_data.get("user_name", "unknown")
    login_time   = session_data.get("login_time", "")
    email        = session_data.get("email", "")

    if not access_token:
        return _error_page("No Access Token", "Kite did not return an access_token.")

    # ── Persist token ─────────────────────────────────────────────────
    token_payload = {
        "access_token": access_token,
        "api_key":      settings.KITE_API_KEY,
        "user_id":      user_id,
        "user_name":    user_name,
        "email":        email,
        "login_time":   str(login_time),
        "generated_at": datetime.now(IST_TZ).isoformat(),
    }

    # 1. Save to file (survives Redis restarts)
    token_path = Path(settings.KITE_TOKEN_PATH)
    token_path.write_text(json.dumps(token_payload, indent=2), encoding="utf-8")
    log.info("kite_token_saved_to_file", user=user_id, path=str(token_path))

    # 2. Save to Redis (fast access by engine — optional, non-blocking)
    if _redis_store:
        try:
            await _redis_store.save_token(token_payload)
            log.info("kite_token_saved_to_redis", user=user_id)
        except Exception as exc:
            log.warning("redis_token_save_skipped", error=str(exc))

    log.info("kite_login_complete", user=user_id, name=user_name)

    # 3. Signal the engine runner (separate process) to re-init via Redis IPC
    if _redis_store:
        try:
            await _redis_store.set_reinit_trigger()
            log.info("reinit_trigger_set_in_redis", user=user_id)
        except Exception as exc:
            log.warning("reinit_trigger_failed", error=str(exc))

    return _success_page(user_name, user_id, email, access_token[:8] + "****")


# ── Token Status ──────────────────────────────────────────────────────────────

@router.get("/status", summary="Check current token status")
async def token_status():
    """
    Returns the current token state from the .kite_token file.
    Use this to verify a valid token exists before starting the engine.

    Note: Does NOT validate the token with Kite API (use /validate for that).
    Per Kite docs, access_token is valid until 6 AM the next day.
    """
    from app.core.config import settings

    path = Path(settings.KITE_TOKEN_PATH)
    if not path.exists():
        return {
            "status": "NO_TOKEN",
            "message": "No .kite_token file found. Please login.",
        }

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        generated_at = data.get("generated_at", "")

        # Check staleness — token expires at 6 AM next day per Kite docs
        is_today = False
        if generated_at:
            try:
                gen_dt = datetime.fromisoformat(generated_at)
                now_ist = datetime.now(IST_TZ)
                is_today = gen_dt.date() == now_ist.date()
            except Exception:
                pass

        return {
            "status": "TOKEN_EXISTS" if is_today else "TOKEN_EXPIRED",
            "user_id":       data.get("user_id"),
            "user_name":     data.get("user_name"),
            "email":         data.get("email"),
            "generated_at":  generated_at,
            "token_preview": data.get("access_token", "")[:8] + "****",
            "is_today":      is_today,
            "warning":       None if is_today else "Token was generated on a previous day — it has expired. Please login again.",
        }
    except Exception as exc:
        return {"status": "CORRUPT_TOKEN", "error": str(exc)}


# ── Delete Token ──────────────────────────────────────────────────────────────

@router.delete("/token", summary="Delete saved token (force re-login)")
async def delete_token():
    """Delete the .kite_token file to force a fresh login next session."""
    from app.core.config import settings

    path = Path(settings.KITE_TOKEN_PATH)
    if path.exists():
        path.unlink()
        log.info("kite_token_deleted")
        return {"status": "deleted", "message": "Token removed. Login again before next session."}
    return {"status": "not_found", "message": "No token file to delete."}


# ── HTML Response Templates ────────────────────────────────────────────────────

def _success_page(name: str, user_id: str, email: str, token_preview: str) -> HTMLResponse:
    from app.core.config import settings
    dashboard_url = f"http://{settings.API_HOST}:{settings.API_PORT}/"
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <title>Login Successful — IVBS</title>
  <meta http-equiv="refresh" content="3; url={dashboard_url}" />
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Inter', system-ui, sans-serif; background: #070c18;
            color: #f0f4ff; display: flex; align-items: center;
            justify-content: center; min-height: 100vh; }}
    .box {{ background: #0d1526; border: 1px solid rgba(16,185,129,0.3);
             border-radius: 16px; padding: 40px 48px; text-align: center;
             max-width: 460px; width: 90%; box-shadow: 0 0 40px rgba(16,185,129,0.1); }}
    .icon {{ font-size: 52px; margin-bottom: 16px; }}
    h2 {{ color: #10b981; margin: 0 0 12px; font-size: 22px; }}
    .info {{ background: #111d35; border-radius: 8px; padding: 12px 16px;
              margin: 12px 0; text-align: left; }}
    .info-row {{ display: flex; justify-content: space-between; font-size: 13px;
                  padding: 3px 0; }}
    .info-label {{ color: #64748b; }}
    .info-value {{ color: #f0f4ff; font-weight: 500; }}
    .token-val {{ font-family: monospace; color: #3b82f6; }}
    .redirect {{ color: #475569; font-size: 12px; margin-top: 20px; }}
    a {{ color: #3b82f6; text-decoration: none; }}
  </style>
</head>
<body>
  <div class="box">
    <div class="icon">✅</div>
    <h2>Login Successful!</h2>
    <div class="info">
      <div class="info-row">
        <span class="info-label">User</span>
        <span class="info-value">{name} ({user_id})</span>
      </div>
      <div class="info-row">
        <span class="info-label">Email</span>
        <span class="info-value">{email}</span>
      </div>
      <div class="info-row">
        <span class="info-label">Token</span>
        <span class="info-value token-val">{token_preview}</span>
      </div>
    </div>
    <p style="color:#94a3b8; font-size:13px; margin-top:12px">
      Token saved to <code>.kite_token</code>. Engine is ready.
    </p>
    <p class="redirect">Auto-redirecting to <a href="{dashboard_url}">dashboard</a> in 3s…</p>
  </div>
</body>
</html>"""
    return HTMLResponse(html)


def _error_page(title: str, detail: str) -> HTMLResponse:
    from app.core.config import settings
    dashboard_url = f"http://{settings.API_HOST}:{settings.API_PORT}/"
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <title>Login Error — IVBS</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Inter', system-ui, sans-serif; background: #070c18;
            color: #f0f4ff; display: flex; align-items: center;
            justify-content: center; min-height: 100vh; }}
    .box {{ background: #0d1526; border: 1px solid rgba(239,68,68,0.35);
             border-radius: 16px; padding: 40px 48px; text-align: center;
             max-width: 500px; width: 90%; }}
    .icon {{ font-size: 52px; margin-bottom: 16px; }}
    h2 {{ color: #ef4444; margin: 0 0 12px; font-size: 20px; }}
    .detail {{ background: #111d35; border-radius: 8px; padding: 12px 16px;
               font-size: 13px; color: #94a3b8; text-align: left;
               margin: 12px 0; line-height: 1.6; }}
    a.btn {{ display: inline-block; margin-top: 20px; padding: 10px 24px;
              background: rgba(59,130,246,0.1); border: 1px solid rgba(59,130,246,0.3);
              border-radius: 8px; color: #3b82f6; font-size: 13px;
              font-weight: 600; text-decoration: none; }}
  </style>
</head>
<body>
  <div class="box">
    <div class="icon">❌</div>
    <h2>{title}</h2>
    <div class="detail">{detail}</div>
    <a class="btn" href="{dashboard_url}">← Back to Dashboard</a>
  </div>
</body>
</html>"""
    return HTMLResponse(html, status_code=400)
