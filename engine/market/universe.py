"""
engine/market/universe.py — Load and filter the scanning universe.

Reads universe.txt (one NSE symbol per line).
Applies instrument-level filters in coordination with InstrumentCache.
"""

from __future__ import annotations

from pathlib import Path

import structlog

log = structlog.get_logger(__name__)


def load_universe(path: str | Path | None = None) -> list[str]:
    """
    Load universe symbols from universe.txt.
    Returns a list of uppercase NSE symbols, one per line, ignoring blank lines and comments (#).
    """
    project_root = Path(__file__).resolve().parents[2]

    if path is None:
        try:
            from app.core.config import settings

            configured = Path(settings.UNIVERSE_FILE)
        except Exception:
            configured = Path("universe.txt")

        path = configured if configured.is_absolute() else project_root / configured

    path = Path(path)
    if not path.exists() and path.name != "nifty500.txt":
        fallback = project_root / "nifty500.txt"
        if fallback.exists():
            log.warning(
                "universe_file_missing_using_fallback",
                missing_path=str(path),
                fallback=str(fallback),
            )
            path = fallback

    if not path.exists():
        log.error("universe_file_not_found", path=str(path))
        return []

    symbols: list[str] = []
    with open(path, encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            symbol = line.upper().removeprefix("NSE:").removesuffix(".NS").strip()
            if symbol not in symbols:  # deduplicate
                symbols.append(symbol)

    log.info("universe_loaded_raw", total=len(symbols), path=str(path))
    return symbols


def filter_universe(
    raw_symbols: list[str],
    instrument_infos: dict,  # symbol → InstrumentInfo
    min_price: float = 50.0,
    max_price: float = 5000.0,
) -> list[str]:
    """
    Final filter pass: only keep symbols that are in InstrumentCache
    AND pass price range AND are not restricted series.

    Returns filtered list preserving original order.
    This is a thin wrapper — the actual filtering detail lives in
    InstrumentCache.filter_to_universe(). This function returns just the
    symbol list from the filtered dict.
    """
    return list(instrument_infos.keys())
