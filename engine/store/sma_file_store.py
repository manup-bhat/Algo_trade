"""
engine/store/sma_file_store.py — Disk-based backup for SMA volume histories.

WHY THIS EXISTS:
  Redis (Memurai) data is lost when the service is stopped or Windows restarts.
  The volume_sma:{symbol} Redis keys have 48h TTL, which is fine for an overnight
  gap — but if Redis is restarted, all SMA histories are gone and the engine must
  re-fetch historical data from Kite (takes ~60s for 500 symbols).

  This file store writes a gzipped JSON snapshot of all SMA histories to disk
  at session end (15:25 PM), and loads it at startup before touching Redis.
  Disk files survive Redis restarts, system reboots, and service failures.

SLIDING WINDOW — HOW IT WORKS:
  NSE market hours: 09:15 AM – 03:30 PM = exactly 375 one-minute candles per day.
  The SMA requires 500 candles = ceil(500/375) = 2 trading days minimum.

  The CandleBuilder uses a deque(maxlen=500). Each day:
    1. Load 500 volumes from this file → builder is instantly warmed (is_warmed_up=True)
    2. Market runs: each new candle appends to deque, oldest falls off automatically
    3. Session end: save 500 volumes back to file (now shifted by ~375 = one day slid)
  This IS the sliding window. The deque enforces it automatically.

  The file also stores `as_of_date` (last trading date included in the snapshot).
  On startup, warmup checks this date:
    - If as_of_date == yesterday: skip SMA re-warmup (already current), just load candles
    - If gap > 0 days: fetch only the MISSING trading days from Kite, slide the deque
    - If no file: fetch 2 trading days (minimum for full 500-period SMA)

  This eliminates the 5-day re-fetch on every startup — only missing days are fetched.

STORAGE:
  ./data/sma_histories.json.gz  — current session snapshot
  ./data/sma_histories.bak.json.gz — previous session backup (auto-rotation)

  File format: {
    "version": 3,
    "as_of_date": "YYYY-MM-DD",     ← last trading date included
    "sma_period": 500,
    "minutes_per_day": 375,         ← NSE trading minutes
    "histories": { symbol: [int, ...max 500...] }
  }

  Gzipped: ~500 symbols × 500 ints ≈ 600KB raw → ~60KB compressed.
"""

from __future__ import annotations

import datetime
import gzip
import json
import shutil
import time
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger(__name__)

# ── NSE market constants ──────────────────────────────────────────────────────
NSE_MINUTES_PER_DAY = 375  # 09:15 AM to 03:30 PM = 375 one-minute candles
SMA_PERIOD = 500           # Must match VOLUME_SMA_PERIOD in config

# Number of trading days whose data covers the SMA period with a safety buffer.
# ceil(500/375) = 2, +1 for safety = 3 days.
# On a fresh install, we fetch 3 days from Kite. On subsequent days, 0–1 days.
SMA_TRADING_DAYS_NEEDED = 3

# ── Default path (relative to project root) ──────────────────────────────────
_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_SMA_FILE = _DATA_DIR / "sma_histories.json.gz"
_SMA_BACKUP = _DATA_DIR / "sma_histories.bak.json.gz"


def _ensure_data_dir() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


# ── Public API ────────────────────────────────────────────────────────────────

def save_sma_histories(
    histories: dict[str, list[int]],
    as_of_date: str | None = None,
) -> bool:
    """
    Write SMA volume histories to disk (gzipped JSON).

    Args:
        histories:   { symbol: [volume_int, ...max_500...] }
        as_of_date:  ISO date string "YYYY-MM-DD" representing the last trading
                     date whose candles are included. Defaults to today (IST).

    Returns:
        True on success, False on failure (non-fatal; Redis is the primary store).
    """
    if not histories:
        return True

    _ensure_data_dir()

    if as_of_date is None:
        try:
            import pytz
            as_of_date = datetime.datetime.now(pytz.timezone("Asia/Kolkata")).date().isoformat()
        except Exception:
            as_of_date = datetime.date.today().isoformat()

    try:
        payload: dict[str, Any] = {
            "version": 3,
            "as_of_date": as_of_date,
            "sma_period": SMA_PERIOD,
            "minutes_per_day": NSE_MINUTES_PER_DAY,
            "histories": {sym: list(vols) for sym, vols in histories.items()},
        }
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")

        # Write to temp file first, then atomically replace
        tmp = _SMA_FILE.with_suffix(".tmp.gz")
        with gzip.open(tmp, "wb") as f:
            f.write(raw)

        # Rotate: current → backup, new → current
        if _SMA_FILE.exists():
            shutil.copy2(_SMA_FILE, _SMA_BACKUP)
        tmp.replace(_SMA_FILE)

        symbol_count = len(histories)
        total_vols = sum(len(v) for v in histories.values())
        size_kb = round(_SMA_FILE.stat().st_size / 1024, 1)
        log.info(
            "sma_file_saved",
            path=str(_SMA_FILE),
            as_of_date=as_of_date,
            symbols=symbol_count,
            total_volumes=total_vols,
            size_kb=size_kb,
        )
        return True

    except Exception as exc:
        log.warning("sma_file_save_failed", error=str(exc), path=str(_SMA_FILE))
        return False


def load_sma_histories() -> dict[str, list[int]]:
    """
    Load SMA volume histories from disk.

    Returns:
        { symbol: [volume_int, ...] } — empty dict if no file or corrupt file.
        Falls back to backup file if primary is corrupt.
    """
    for path in (_SMA_FILE, _SMA_BACKUP):
        if not path.exists():
            continue
        try:
            with gzip.open(path, "rb") as f:
                raw = f.read()
            payload = json.loads(raw.decode("utf-8"))

            # Support version 3 (nested under "histories" key)
            if isinstance(payload, dict) and "histories" in payload:
                data = payload["histories"]
            else:
                # Legacy v2: top-level dict is { symbol: [vols] }
                data = payload

            # Validate and convert
            result: dict[str, list[int]] = {}
            for sym, vols in data.items():
                if isinstance(vols, list) and len(vols) > 0:
                    result[sym] = [int(v) for v in vols]

            log.info(
                "sma_file_loaded",
                path=str(path),
                as_of_date=payload.get("as_of_date", "unknown"),
                symbols=len(result),
                is_backup=(path == _SMA_BACKUP),
            )
            return result

        except Exception as exc:
            log.warning("sma_file_load_failed", path=str(path), error=str(exc))
            continue

    log.info("sma_file_not_found", primary=str(_SMA_FILE), backup=str(_SMA_BACKUP))
    return {}


def get_as_of_date() -> datetime.date | None:
    """
    Return the as_of_date from the file without loading all volumes.
    Used by warmup to check how many trading days of gap to fill.
    Returns None if no file exists or date is unreadable.
    """
    for path in (_SMA_FILE, _SMA_BACKUP):
        if not path.exists():
            continue
        try:
            with gzip.open(path, "rb") as f:
                # Read first 2048 bytes — ensures the metadata header is always fully captured
                # after decompression even with dense gzip compression ratios
                partial = f.read(2048)
            text = partial.decode("utf-8", errors="ignore")
            # Find "as_of_date" key
            idx = text.find('"as_of_date"')
            if idx == -1:
                return None
            # Extract the value (next quoted string after the key)
            val_start = text.index('"', idx + 12) + 1
            val_end = text.index('"', val_start)
            date_str = text[val_start:val_end]
            return datetime.date.fromisoformat(date_str)
        except Exception:
            continue
    return None


def get_file_age_hours() -> float | None:
    """Return age of the SMA file in hours, or None if it doesn't exist."""
    if not _SMA_FILE.exists():
        return None
    try:
        age_seconds = time.time() - _SMA_FILE.stat().st_mtime
        return round(age_seconds / 3600, 1)
    except Exception:
        return None


def count_trading_days_gap(
    as_of_date: datetime.date,
    up_to: datetime.date,
    holidays: frozenset[datetime.date] | None = None,
) -> int:
    """
    Count trading days strictly AFTER as_of_date up to and INCLUDING up_to.

    This is the number of MISSING days we need to fetch from Kite.

    Args:
        as_of_date:  Last date already covered by the SMA file
        up_to:       Target date (usually yesterday = last closed session)
        holidays:    NSE holiday dates to skip (loaded from nse_holidays.json)

    Returns:
        Number of trading days gap. 0 means file is already up to date.
    """
    if as_of_date >= up_to:
        return 0

    if holidays is None:
        # Import lazily to avoid circular imports
        try:
            from engine.market.calendar import NSE_HOLIDAYS
            holidays = NSE_HOLIDAYS
        except Exception:
            holidays = frozenset()

    count = 0
    current = as_of_date + datetime.timedelta(days=1)
    while current <= up_to:
        if current.weekday() < 5 and current not in holidays:  # Mon-Fri, not holiday
            count += 1
        current += datetime.timedelta(days=1)
    return count
