"""
scripts/kite_port80_redirect.py — Tiny HTTP server on port 80 to catch the
Kite Connect OAuth redirect and forward it to the main FastAPI app on port 8000.

Why this exists:
  Kite Connect Developer Console only allows "http://127.0.0.1" as redirect URL
  (no custom port, no path). After login, Zerodha redirects the browser to:
    http://127.0.0.1/?action=login&type=login&status=success&request_token=XXX

  Our FastAPI app runs on port 8000. This tiny server runs on port 80, catches
  the redirect, and immediately 302-redirects the browser to:
    http://127.0.0.1:8000/api/v1/auth/callback?<same_params>

Usage (run BEFORE starting the engine, as Administrator if needed):
  python scripts/kite_port80_redirect.py

  OR run it in the background:
  start /b python scripts/kite_port80_redirect.py

Requires no dependencies — uses only Python's built-in http.server.
Note: On Windows, port 80 may require running as Administrator.
"""

from __future__ import annotations

import http.server
import urllib.parse
import sys

import os
import re

def _read_env_port(default: int = 8000) -> int:
    """Read API_PORT from .env file without importing pydantic (no deps)."""
    env_files = [
        os.path.join(os.path.dirname(__file__), "..", ".env"),
        os.path.join(os.path.dirname(__file__), ".env"),
    ]
    for env_file in env_files:
        path = os.path.abspath(env_file)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    m = re.match(r"^\s*API_PORT\s*=\s*(\d+)", line)
                    if m:
                        return int(m.group(1))
    return default

def _read_env_host(default: str = "127.0.0.1") -> str:
    """Read API_HOST from .env file."""
    env_files = [
        os.path.join(os.path.dirname(__file__), "..", ".env"),
        os.path.join(os.path.dirname(__file__), ".env"),
    ]
    for env_file in env_files:
        path = os.path.abspath(env_file)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    m = re.match(r"^\s*API_HOST\s*=\s*(.+)", line)
                    if m:
                        return m.group(1).strip()
    return default

TARGET_HOST = _read_env_host()
TARGET_PORT = _read_env_port()
TARGET_PATH = "/api/v1/auth/callback"

LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = 80


class KiteRedirectHandler(http.server.BaseHTTPRequestHandler):
    """
    Catches the Kite OAuth callback on port 80 and redirects to FastAPI on port 8000.
    """

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        query = parsed.query

        # Only redirect if it looks like a Kite callback (has request_token or status)
        params = urllib.parse.parse_qs(query)
        has_token = "request_token" in params
        is_login  = params.get("action", [None])[0] == "login"
        is_failed = params.get("status", [None])[0] != "success"

        # Always redirect everything to FastAPI's auth callback
        redirect_to = f"http://{TARGET_HOST}:{TARGET_PORT}{TARGET_PATH}?{query}"

        self.send_response(302)
        self.send_header("Location", redirect_to)
        self.send_header("Content-Type", "text/html")
        self.end_headers()

        msg = f"<html><body>Redirecting to IVBS engine on port {TARGET_PORT}...</body></html>"
        self.wfile.write(msg.encode())

        if has_token:
            log(f"✅ Caught Kite callback, forwarding request_token to port {TARGET_PORT}")
        else:
            log(f"ℹ️  Redirecting request (no request_token): {self.path[:80]}")

    def log_message(self, format, *args):
        # Suppress the default noisy logs
        pass


def log(msg: str) -> None:
    print(f"[kite_redirect] {msg}", flush=True)


def main():
    try:
        server = http.server.HTTPServer((LISTEN_HOST, LISTEN_PORT), KiteRedirectHandler)
        log(f"🚀 Listening on http://{LISTEN_HOST}:{LISTEN_PORT}")
        log(f"   Forwarding Kite callbacks → http://{TARGET_HOST}:{TARGET_PORT}{TARGET_PATH}")
        log("   Press Ctrl+C to stop")
        server.serve_forever()
    except PermissionError:
        print(
            "\n❌ PermissionError: Cannot bind to port 80.\n"
            "   On Windows, run this script as Administrator:\n"
            "   Right-click PowerShell → 'Run as Administrator', then run:\n"
            "   python scripts/kite_port80_redirect.py\n"
        )
        sys.exit(1)
    except KeyboardInterrupt:
        log("Stopped.")


if __name__ == "__main__":
    main()
