"""
engine/market/watchlist.py — Editable, hot-reloadable scanning watchlist.

The dashboard (a separate FastAPI process) edits the watchlist and persists it
to the shared ``universe.txt`` file, then signals the engine via Redis
(``set_pending_watchlist``). The engine's ``_poll_config`` loop consumes that
signal and reconciles its live CandleBuilders + WebSocket subscription without a
restart.

This module owns ONLY file persistence + symbol validation so it is trivially
unit-testable with an injected path. The cross-process signalling lives in
``RedisStore`` and the live builder/subscription reconciliation lives in
``Coordinator.apply_watchlist`` / ``AsyncKiteTicker.add_tokens``.
"""

from __future__ import annotations

from pathlib import Path

import structlog

from engine.market.universe import load_universe

log = structlog.get_logger(__name__)

# Hard cap to avoid a runaway edit accidentally subscribing to thousands of
# tokens (Kite WS has a practical per-connection instrument limit of ~3000).
MAX_WATCHLIST_SIZE = 2000


def normalize_symbol(symbol: str) -> str:
    """Uppercase and strip NSE:/.NS decoration — matches ``load_universe``."""
    return str(symbol).strip().upper().removeprefix("NSE:").removesuffix(".NS").strip()


def validate_symbols(
    symbols: list[str],
    known: set[str] | None = None,
) -> tuple[list[str], list[str]]:
    """
    Normalize + de-duplicate a list of symbols, preserving first-seen order.

    If ``known`` is provided (the set of valid tradable NSE symbols), any symbol
    not present is rejected. When ``known`` is ``None`` no membership check is
    performed (fail-open — used when the instrument cache is not yet available).

    Returns ``(valid, rejected)``.
    """
    valid: list[str] = []
    rejected: list[str] = []
    seen: set[str] = set()
    for raw in symbols:
        sym = normalize_symbol(raw)
        if not sym or sym in seen:
            continue
        seen.add(sym)
        if known is not None and sym not in known:
            rejected.append(sym)
            continue
        valid.append(sym)
    return valid, rejected


def _default_watchlist_path() -> Path:
    """Resolve the configured ``universe.txt`` path (repo-root relative)."""
    project_root = Path(__file__).resolve().parents[2]
    try:
        from app.core.config import settings

        configured = Path(settings.UNIVERSE_FILE)
    except Exception:
        configured = Path("universe.txt")
    return configured if configured.is_absolute() else project_root / configured


class WatchlistManager:
    """
    File-backed watchlist persistence with delta reporting.

    The watchlist is stored as ``universe.txt`` so the existing startup loader
    (``load_universe``) and the engine's pre-market setup pick it up on the next
    restart without any extra wiring.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path is not None else _default_watchlist_path()

    @property
    def path(self) -> Path:
        return self._path

    def get(self) -> list[str]:
        """Return the current watchlist symbols (empty list if file missing).

        Note: we intentionally bypass ``load_universe``'s nifty500 fallback here
        so a missing/empty watchlist reads as empty rather than silently
        expanding to the default 500-symbol universe.
        """
        if not self._path.exists():
            return []
        return load_universe(self._path)

    def save(self, symbols: list[str]) -> None:
        """Persist ``symbols`` to the watchlist file (one per line)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            f.write("# Scanning watchlist — one NSE symbol per line.\n")
            f.write("# Edited via the dashboard; hot-reloaded by the engine.\n")
            for sym in symbols:
                f.write(sym + "\n")

    def set(
        self,
        symbols: list[str],
        known: set[str] | None = None,
    ) -> dict:
        """
        Validate, persist, and report the change relative to the current file.

        Returns a dict with ``symbols`` (the new list), ``added``, ``removed``,
        ``rejected``, and ``count``.

        Raises ``ValueError`` if the resulting watchlist would be empty or
        exceeds :data:`MAX_WATCHLIST_SIZE` — both are treated as operator errors
        rather than silently applied.
        """
        valid, rejected = validate_symbols(symbols, known)
        if not valid:
            raise ValueError("watchlist_empty")
        if len(valid) > MAX_WATCHLIST_SIZE:
            raise ValueError(f"watchlist_too_large:{len(valid)}>{MAX_WATCHLIST_SIZE}")

        previous = set(self.get())
        self.save(valid)

        new_set = set(valid)
        added = sorted(new_set - previous)
        removed = sorted(previous - new_set)
        log.info(
            "watchlist_saved",
            count=len(valid),
            added=len(added),
            removed=len(removed),
            rejected=len(rejected),
        )
        return {
            "symbols": valid,
            "added": added,
            "removed": removed,
            "rejected": rejected,
            "count": len(valid),
        }
