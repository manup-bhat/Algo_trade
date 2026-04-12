"""
engine/market/calendar.py — Market hours check (IST-aware, holiday-aware).

NSE_HOLIDAYS is loaded once from nse_holidays.json at import time.
All time comparisons use Asia/Kolkata timezone explicitly.
"""

from __future__ import annotations

import datetime
import json
import os
from pathlib import Path

import pytz

IST_TZ = pytz.timezone("Asia/Kolkata")

# ── Load NSE Holidays ───────────────────────────────────────────────────────

def _load_holidays(json_path: str | None = None) -> frozenset[datetime.date]:
    """
    Load NSE trading holidays from nse_holidays.json.
    Searches relative to project root (two levels up from this file).
    Returns an empty frozenset on any error — fail-open is safer than fail-closed
    for a holiday file (worst case: bot tries to trade on a holiday and
    Kite rejects the orders; it does NOT place phantom trades).
    """
    if json_path is None:
        # Locate file: trading_bot/nse_holidays.json
        this_dir = Path(__file__).resolve().parent
        # engine/market/ → engine/ → trading_bot/
        candidate = this_dir.parent.parent / "nse_holidays.json"
        json_path = str(candidate)

    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        holidays = frozenset(
            datetime.date.fromisoformat(h["date"]) for h in data.get("holidays", [])
        )
        return holidays
    except FileNotFoundError:
        import warnings
        warnings.warn(
            f"nse_holidays.json not found at {json_path}. "
            "Holiday checks will be skipped — bot may attempt trading on holidays.",
            stacklevel=2,
        )
        return frozenset()
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        import warnings
        warnings.warn(f"Failed to parse nse_holidays.json: {exc}", stacklevel=2)
        return frozenset()


NSE_HOLIDAYS: frozenset[datetime.date] = _load_holidays()


# ── Public API ─────────────────────────────────────────────────────────────


def is_market_open(now: datetime.datetime | None = None) -> bool:
    """
    Returns True if the NSE market is currently open for trading.

    Market hours: Monday–Friday, 09:15 AM – 03:30 PM IST, excluding NSE holidays.
    Accepts an optional `now` parameter for testing (must be timezone-aware IST).
    """
    if now is None:
        now = datetime.datetime.now(IST_TZ)

    # Ensure timezone-aware
    if now.tzinfo is None:
        now = IST_TZ.localize(now)

    # Weekends: Monday=0 … Sunday=6
    if now.weekday() >= 5:
        return False

    # NSE holiday
    if now.date() in NSE_HOLIDAYS:
        return False

    market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)

    return market_open <= now <= market_close


def is_trading_day(date: datetime.date | None = None) -> bool:
    """
    Returns True if the given date is an NSE trading day (not weekend, not holiday).
    Defaults to today in IST.
    """
    if date is None:
        date = datetime.datetime.now(IST_TZ).date()
    if date.weekday() >= 5:
        return False
    return date not in NSE_HOLIDAYS


def next_trading_day(from_date: datetime.date | None = None) -> datetime.date:
    """Return the next trading day after from_date (defaults to today in IST)."""
    if from_date is None:
        from_date = datetime.datetime.now(IST_TZ).date()
    candidate = from_date + datetime.timedelta(days=1)
    while not is_trading_day(candidate):
        candidate += datetime.timedelta(days=1)
    return candidate


def now_ist() -> datetime.datetime:
    """Return the current time in IST. Convenience wrapper."""
    return datetime.datetime.now(IST_TZ)
