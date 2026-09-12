"""
engine/market/instrument_master.py — Unified instrument facade.

Single point of truth for all instrument lookups: NSE equity (from InstrumentCache)
and NFO derivatives (from OptionChainResolver), plus freeze-quantity lookup.

This is the generalisation called for in Part 2 §4.2 and Part 3 §5 Phase 1 item 2.
It wraps the two existing singletons rather than replacing them, so no existing
call sites break.

Key responsibilities:
  1. Unified token/symbol/tick-size lookups for any exchange.
  2. Option-chain builder: resolve a manifest `requirements.instruments` block to
     a concrete list of instrument tokens for MarketDataGateway subscription.
  3. Freeze-quantity lookups (NSE/SEBI per-contract order size caps).
  4. ATM strike + nearest expiry convenience wrappers (re-exported from OptionChainResolver).

Thread safety: stateless after load() — safe to call from any coroutine.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any

import structlog

from engine.core.instrument import Instrument, OptionType
from engine.kite.instruments import InstrumentCache, InstrumentInfo
from engine.market.option_chain import OptionChainResolver

if TYPE_CHECKING:
    pass

log = structlog.get_logger(__name__)


class InstrumentMaster:
    """
    Unified instrument lookup facade.

    Owns both the NSE equity cache and the NFO derivatives index.
    Loaded once at pre-market setup; reloaded daily (idempotent).

    Usage:
        master = InstrumentMaster()
        master.load_nse(nse_dump)
        master.load_nfo(nfo_dump)

        token = master.get_token("RELIANCE")           # int | None
        info  = master.get_instrument("RELIANCE")      # InstrumentInfo | None
        toks  = master.build_subscription_tokens(      # list[int]
            {"mode": "option_chain", "underlying": "NIFTY", ...}
        )
    """

    def __init__(self) -> None:
        self._equity = InstrumentCache()
        self._derivatives = OptionChainResolver()
        # Freeze quantity overrides (populated from NFO dump or config table)
        self._freeze_qty: dict[str, int] = {}
        self._nfo_loaded = False
        self._nse_loaded = False

    # ── Loading ───────────────────────────────────────────────────────────────

    def load_nse(self, instruments: list[dict]) -> None:
        """
        Load and index the NSE equity instrument dump.
        Idempotent — calling twice replaces the prior index.
        """
        self._equity.load(instruments)
        self._nse_loaded = True

    def load_nfo(self, nfo_dump: list[dict]) -> None:
        """
        Load and index the NFO derivatives dump.
        Also extracts freeze_qty values per tradingsymbol where present.

        Edge cases:
          - Empty dump (NFO fetch failed) → logs CRITICAL, does not raise.
          - No freeze_qty field in an NFO row → falls back to conservative defaults.
        """
        if not nfo_dump:
            log.critical(
                "instrument_master_nfo_dump_empty",
                hint="Option chain resolution will not work until NFO is loaded.",
            )
            return

        self._derivatives.load(nfo_dump)
        self._extract_freeze_quantities(nfo_dump)
        self._nfo_loaded = True

    def _extract_freeze_quantities(self, nfo_dump: list[dict]) -> None:
        """
        Extract freeze_qty values from the NFO dump into the lookup dict.

        NSE revises freeze quantities periodically — never hardcode them.
        The Kite NFO instrument dump includes `freeze_qty` for most index F&O
        contracts.  Equity F&O is covered by conservative defaults.
        """
        extracted = 0
        for row in nfo_dump:
            symbol = row.get("tradingsymbol", "")
            fq = row.get("freeze_qty", 0)
            if symbol and fq and int(fq) > 0:
                self._freeze_qty[symbol] = int(fq)
                extracted += 1
        log.info("freeze_quantities_extracted", count=extracted)

    # ── Lookups — Equity ──────────────────────────────────────────────────────

    def get_token(self, symbol: str, exchange: str = "NSE") -> int | None:
        """Return the instrument token for *symbol* (None if not found)."""
        if exchange in ("NSE", "BSE"):
            return self._equity.get_token(symbol)
        # NFO — look up by tradingsymbol in derivatives index
        inst = self._derivatives.by_symbol(symbol)
        return inst.instrument_token if inst and inst.instrument_token else None

    def get_instrument(
        self, symbol: str, exchange: str = "NSE"
    ) -> InstrumentInfo | Instrument | None:
        """Return the instrument record for *symbol* (None if not found)."""
        if exchange in ("NSE", "BSE"):
            return self._equity.get_by_symbol(symbol)
        return self._derivatives.by_symbol(symbol)

    def get_tick_size(self, symbol: str) -> float:
        """Return tick size for *symbol* (defaults to 0.05 if unknown)."""
        info = self._equity.get_by_symbol(symbol)
        if info:
            return info.tick_size
        inst = self._derivatives.by_symbol(symbol)
        return inst.tick_size if inst else 0.05

    def get_lot_size(self, symbol: str) -> int:
        """Return lot size for *symbol* (1 for equity, N for F&O)."""
        info = self._equity.get_by_symbol(symbol)
        if info:
            return info.lot_size
        inst = self._derivatives.by_symbol(symbol)
        return inst.lot_size if inst and inst.lot_size else 1

    # ── Lookups — Freeze Quantity ─────────────────────────────────────────────

    def get_freeze_quantity(self, symbol: str) -> int:
        """
        Return the NSE freeze quantity (max qty per single order) for *symbol*.

        If not found in the NFO dump, returns a conservative per-category default:
          - Index options (CE/PE):  1,800
          - Equity F&O:             2,500 (NSE default for most contracts)
          - Equity:                 999,999 (effectively no cap)

        This value is used by OrderService to auto-split orders exceeding it.
        """
        if symbol in self._freeze_qty:
            return self._freeze_qty[symbol]

        sym_upper = symbol.upper()

        # Check derivatives index first if loaded
        if self._nfo_loaded and self._derivatives.by_symbol(symbol):
            if sym_upper.startswith(("NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY")):
                return 1_800
            return 2_500

        # Check equity cache if loaded
        if self._nse_loaded and self._equity.get_by_symbol(symbol):
            return 999_999

        # Category-based heuristic fallback
        import re
        if sym_upper.startswith(("NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY")):
            return 1_800  # NSE index option freeze qty (as of FY2024)
        if re.search(r"\d+(CE|PE)$", sym_upper) or sym_upper.endswith("FUT"):
            return 2_500  # Conservative equity F&O default
        return 999_999   # Equity: no effective freeze

    # ── Lookups — Derivatives ─────────────────────────────────────────────────

    def nearest_expiry(
        self, underlying: str, ref_date: datetime.date | None = None
    ) -> datetime.date | None:
        """Return nearest expiry on/after ref_date for *underlying*."""
        return self._derivatives.nearest_expiry(underlying, ref_date)

    def atm_option(
        self,
        underlying: str,
        spot: float,
        option_type: OptionType,
        expiry: datetime.date | None = None,
    ) -> Instrument | None:
        """Resolve ATM CE/PE for given underlying + spot + expiry."""
        return self._derivatives.atm_option(underlying, spot, option_type, expiry)

    def atm_strike(
        self,
        underlying: str,
        spot: float,
        expiry: datetime.date,
        option_type: OptionType = OptionType.CE,
    ) -> float | None:
        """Return ATM strike (nearest listed to spot)."""
        return self._derivatives.atm_strike(underlying, spot, expiry, option_type)

    def option_chain_resolver(self) -> OptionChainResolver:
        """Return the underlying OptionChainResolver for advanced F&O queries."""
        return self._derivatives

    # ── Subscription token resolution ────────────────────────────────────────

    def build_subscription_tokens(
        self,
        instruments_block: dict[str, Any],
        universe_symbols: list[str] | None = None,
    ) -> list[int]:
        """
        Resolve a manifest `requirements.instruments` block to instrument tokens.

        Args:
            instruments_block: The `requirements.instruments` dict from the manifest.
            universe_symbols:  Current active universe (for mode=watchlist with no
                               explicit symbols list).

        Returns:
            List of integer instrument tokens to subscribe on the WS.
            Returns [] (not raises) on any resolution error — callers must handle
            an empty list gracefully (log alert, strategy gets no ticks).

        Supported modes:
          watchlist:
            Uses `symbols` list if present, otherwise falls back to universe_symbols.
            Skips symbols not found in InstrumentCache (logs warning per missing sym).

          option_chain:
            Resolves CE + PE tokens for the given underlying/expiry/strike_range_pct.
            Requires NFO dump to be loaded (logs CRITICAL if not).
            Returns [] if no strikes found in range.

        Edge cases handled:
          - No instruments_block or empty → return [].
          - Unknown mode → log warning, return [].
          - NFO not loaded when mode=option_chain → CRITICAL log, return [].
          - Symbol in universe but not in NSE dump (delisted intraday) → skip, warn.
          - strike_range_pct produces no strikes → return [], alert.
        """
        if not instruments_block:
            return []

        mode = instruments_block.get("mode", "watchlist")

        if mode == "watchlist":
            return self._resolve_watchlist(instruments_block, universe_symbols or [])
        elif mode == "option_chain":
            return self._resolve_option_chain(instruments_block)
        else:
            log.warning(
                "instrument_master_unknown_mode",
                mode=mode,
                known_modes=["watchlist", "option_chain"],
            )
            return []

    def _resolve_watchlist(
        self,
        block: dict[str, Any],
        universe_symbols: list[str],
    ) -> list[int]:
        symbols = block.get("symbols") or universe_symbols
        tokens: list[int] = []
        missing: list[str] = []

        for sym in symbols:
            token = self._equity.get_token(sym)
            if token is None:
                missing.append(sym)
            else:
                tokens.append(token)

        if missing:
            log.warning(
                "instrument_master_symbols_not_found",
                count=len(missing),
                symbols=missing[:20],  # cap log size
            )

        log.info("watchlist_tokens_resolved", count=len(tokens))
        return tokens

    def _resolve_option_chain(self, block: dict[str, Any]) -> list[int]:
        if not self._nfo_loaded:
            log.critical(
                "instrument_master_nfo_not_loaded",
                hint="Call load_nfo() before resolving option_chain mode subscriptions.",
            )
            return []

        underlying = block.get("underlying", "")
        expiry_spec = block.get("expiry", "nearest_weekly")
        strike_range_pct = float(block.get("strike_range_pct", 5))

        if not underlying:
            log.error("instrument_master_option_chain_no_underlying", block=block)
            return []

        # Resolve expiry
        expiry = self._derivatives.nearest_expiry(underlying)
        if expiry is None:
            log.error(
                "instrument_master_no_expiry_found",
                underlying=underlying,
            )
            return []

        # Gather all strikes in range for CE + PE
        tokens: list[int] = []
        for ot in (OptionType.CE, OptionType.PE):
            strikes = self._derivatives.strikes(underlying, expiry, ot)
            if not strikes:
                continue
            # Use the midpoint of strikes as a proxy for spot (for ranging)
            # In production, the actual spot is passed via ctx.extra or from Redis LTP.
            # Here we use the full strike ladder within range_pct of the midpoint.
            mid_strike = strikes[len(strikes) // 2]
            lo = mid_strike * (1 - strike_range_pct / 100)
            hi = mid_strike * (1 + strike_range_pct / 100)
            for strike in strikes:
                if lo <= strike <= hi:
                    inst = self._derivatives.resolve(underlying, expiry, ot, strike)
                    if inst and inst.instrument_token:
                        tokens.append(inst.instrument_token)

        if not tokens:
            log.warning(
                "instrument_master_option_chain_no_tokens",
                underlying=underlying,
                expiry=str(expiry),
                strike_range_pct=strike_range_pct,
            )

        log.info(
            "option_chain_tokens_resolved",
            underlying=underlying,
            expiry=str(expiry),
            count=len(tokens),
        )
        return tokens

    # ── Filter helpers (re-exported for convenience) ──────────────────────────

    def filter_to_universe(
        self,
        universe_symbols: list[str],
        min_price: float = 50.0,
        max_price: float = 5000.0,
    ) -> dict[str, InstrumentInfo]:
        """Delegate to InstrumentCache.filter_to_universe()."""
        return self._equity.filter_to_universe(universe_symbols, min_price, max_price)


# Module-level singleton — loaded during pre-market setup via runner.py
instrument_master = InstrumentMaster()
