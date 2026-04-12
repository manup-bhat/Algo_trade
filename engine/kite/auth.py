"""
engine/kite/auth.py — Token load, validate, and save for Kite Connect.

Tokens are stored in two places (file + Redis) for redundancy:
  - .kite_token file: survives Redis restarts
  - Redis session:token: fast access by both processes
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from engine.store.redis_store import RedisStore

log = structlog.get_logger(__name__)


def load_token_from_file(token_path: str = ".kite_token") -> dict | None:
    """Load token data from the .kite_token file. Returns None if not found."""
    path = Path(token_path)
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("token_file_read_error", error=str(exc), path=str(path))
        return None


async def load_token(
    token_path: str = ".kite_token",
    redis_store: "RedisStore | None" = None,
) -> str | None:
    """
    Load the Kite access_token.
    Priority: file → Redis → None.
    Returns the access_token string, or None if not available.
    """
    # Try file first
    data = load_token_from_file(token_path)
    if data and data.get("access_token"):
        log.debug("token_loaded_from_file")
        return data["access_token"]

    # Fall back to Redis
    if redis_store:
        redis_data = await redis_store.load_token()
        if redis_data and redis_data.get("access_token"):
            log.debug("token_loaded_from_redis")
            return redis_data["access_token"]

    log.warning("no_token_found")
    return None


def validate_token(kite: object, token: str) -> bool:
    """
    Validate the token by calling kite.profile().
    Returns True if valid, False on TokenException.
    Logs CRITICAL on failure.
    """
    try:
        kite.set_access_token(token)  # type: ignore[attr-defined]
        kite.profile()  # type: ignore[attr-defined]
        log.info("token_validated")
        return True
    except Exception as exc:
        # kiteconnect raises TokenException for invalid/expired tokens
        exc_name = type(exc).__name__
        if "Token" in exc_name:
            log.critical("token_invalid_re_authenticate", error=str(exc))
        else:
            log.error("token_validation_error", error=str(exc), exc_type=exc_name)
        return False


async def save_token(
    token_data: dict,
    token_path: str = ".kite_token",
    redis_store: "RedisStore | None" = None,
) -> None:
    """
    Persist token to both file and Redis.
    token_data must contain at least: {access_token, user_id, user_name, generated_at}
    """
    # Save to file
    path = Path(token_path)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(token_data, f, indent=2)
        log.info("token_saved_to_file", path=str(path))
    except OSError as exc:
        log.error("token_file_write_error", error=str(exc))

    # Save to Redis
    if redis_store:
        await redis_store.save_token(token_data)
        log.debug("token_saved_to_redis")
