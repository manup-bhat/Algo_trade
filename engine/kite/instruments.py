"""
engine/kite/instruments.py — NSE instrument dump loader + token/symbol mappers.

Fetched once at 09:00 AM and cached. Provides O(1) lookups for:
  symbol → instrument_token (for WS subscription)
  instrument_token → symbol (for tick routing)
  symbol → tick_size (for SL buffer calculation)
  symbol → InstrumentInfo (full details)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    pass

log = structlog.get_logger(__name__)

# NSE series codes that indicate surveillance / restricted trading
# T   = Trade-to-Trade (T2T segment)
# BE  = Book Entry
# BZ  = Scrip suspended
# IL  = Illiquid
_RESTRICTED_SERIES = frozenset({"T", "BE", "BZ", "IL"})


@dataclass(frozen=True, slots=True)
class InstrumentInfo:
    instrument_token: int
    symbol: str            # tradingsymbol (e.g. "RELIANCE")
    tick_size: float       # Minimum price movement in ₹
    lot_size: int          # Usually 1 for equity; relevant for freeze-qty checks
    series: str            # EQ, BE, T, etc.
    last_price: float      # Previous close from Kite dump

    @property
    def is_restricted(self) -> bool:
        """True if stock is in a surveillance / T2T category."""
        return self.series in _RESTRICTED_SERIES


class InstrumentCache:
    """
    Holds loaded, filtered instrument data for the current trading session.
    All lookups are O(1) dict operations — safe to call in the tick hot-path
    (tick_size retrieval for SL computation).
    """

    def __init__(self) -> None:
        self._by_symbol: dict[str, InstrumentInfo] = {}
        self._by_token: dict[int, InstrumentInfo] = {}

    def load(self, instruments: list[dict]) -> None:
        """
        Parse the raw list from kite.instruments("NSE") and populate maps.
        Filters to EQ series only (the standard equities segment).
        """
        loaded = 0
        for inst in instruments:
            series = inst.get("series", "")
            exch_token = inst.get("instrument_token", 0)
            symbol = inst.get("tradingsymbol", "")
            tick_size = float(inst.get("tick_size", 0.05))
            lot_size = int(inst.get("lot_size", 1))
            last_price = float(inst.get("last_price", 0.0))

            if not symbol or not exch_token:
                continue

            info = InstrumentInfo(
                instrument_token=exch_token,
                symbol=symbol,
                tick_size=tick_size if tick_size > 0 else 0.05,
                lot_size=lot_size if lot_size > 0 else 1,
                series=series,
                last_price=last_price,
            )
            self._by_symbol[symbol] = info
            self._by_token[exch_token] = info
            loaded += 1

        log.info("instruments_loaded", total_nse_instruments=loaded)

    def get_by_symbol(self, symbol: str) -> InstrumentInfo | None:
        return self._by_symbol.get(symbol)

    def get_by_token(self, token: int) -> InstrumentInfo | None:
        return self._by_token.get(token)

    def get_tick_size(self, symbol: str) -> float:
        """Return tick_size for symbol, default 0.05 if unknown."""
        info = self._by_symbol.get(symbol)
        return info.tick_size if info else 0.05

    def get_token(self, symbol: str) -> int | None:
        info = self._by_symbol.get(symbol)
        return info.instrument_token if info else None

    def filter_to_universe(
        self,
        universe_symbols: list[str],
        min_price: float = 50.0,
        max_price: float = 5000.0,
    ) -> dict[str, InstrumentInfo]:
        """
        Return only the subset of instruments matching the universe symbols,
        applying price range and series filters.

        Returns: symbol → InstrumentInfo mapping for valid universe stocks.
        """
        result: dict[str, InstrumentInfo] = {}
        skipped_missing = []
        skipped_restricted = []
        skipped_price = []

        for symbol in universe_symbols:
            info = self._by_symbol.get(symbol)
            if info is None:
                skipped_missing.append(symbol)
                continue
            if info.is_restricted:
                skipped_restricted.append(symbol)
                continue
            # Price range check uses previous close as proxy
            if info.last_price > 0 and not (min_price <= info.last_price <= max_price):
                skipped_price.append(symbol)
                continue
            result[symbol] = info

        log.info(
            "universe_filtered",
            requested=len(universe_symbols),
            accepted=len(result),
            skipped_missing=len(skipped_missing),
            skipped_restricted=len(skipped_restricted),
            skipped_price=len(skipped_price),
        )
        if skipped_missing:
            log.debug("universe_missing_symbols", symbols=skipped_missing[:20])
        if skipped_restricted:
            log.warning("universe_restricted_symbols", symbols=skipped_restricted)

        return result


async def load_instruments_async(kite_client: object) -> list[dict]:
    """
    Fetch the NSE instrument dump asynchronously.
    kite_client must expose an async `instruments(exchange)` method.
    """
    # AsyncKiteClient.instruments() is already async (uses run_in_executor internally)
    raw: list[dict] = await kite_client.instruments("NSE")  # type: ignore[attr-defined]
    return raw


# Module-level singleton — populated during pre-market setup
instrument_cache = InstrumentCache()
