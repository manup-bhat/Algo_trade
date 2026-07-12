"""
engine/market/option_chain.py — F&O instrument index + option-chain resolver.

Parses the Zerodha NFO instrument dump (kite.instruments("NFO")) into normalized
engine.core.instrument.Instrument objects and provides option-chain queries:
nearest expiry, ATM strike (from strikes actually listed), and CE/PE/FUT lookup.

Pure, dependency-light logic — fully unit-testable with a synthetic dump. No I/O.
"""

from __future__ import annotations

import datetime

import structlog

from engine.core.instrument import AssetClass, Instrument, OptionType

log = structlog.get_logger(__name__)


class OptionChainResolver:
    """In-memory index of F&O instruments with option-chain resolution."""

    def __init__(self) -> None:
        self._by_symbol: dict[str, Instrument] = {}
        self._by_token: dict[int, Instrument] = {}
        # (underlying, expiry, option_type) -> {strike: Instrument}
        self._chain: dict[tuple[str, datetime.date, OptionType], dict[float, Instrument]] = {}
        # underlying -> {expiry: future Instrument}
        self._futures: dict[str, dict[datetime.date, Instrument]] = {}
        # underlying -> sorted unique expiries (options + futures)
        self._expiries: dict[str, list[datetime.date]] = {}

    # ── Loading ──────────────────────────────────────────────────────────────

    def load(self, nfo_dump: list[dict]) -> None:
        """Parse a kite.instruments('NFO') dump. Idempotent (clears prior state)."""
        self._by_symbol.clear()
        self._by_token.clear()
        self._chain.clear()
        self._futures.clear()
        self._expiries.clear()

        expiry_sets: dict[str, set[datetime.date]] = {}
        opts = futs = 0

        for row in nfo_dump:
            inst = Instrument.from_kite_dict(row)
            if not inst.is_derivative or not inst.underlying:
                continue
            self._by_symbol[inst.tradingsymbol] = inst
            if inst.instrument_token:
                self._by_token[inst.instrument_token] = inst

            und = inst.underlying
            if inst.is_option and inst.expiry is not None and inst.strike is not None:
                key = (und, inst.expiry, inst.option_type)  # type: ignore[arg-type]
                self._chain.setdefault(key, {})[inst.strike] = inst
                expiry_sets.setdefault(und, set()).add(inst.expiry)
                opts += 1
            elif inst.is_future and inst.expiry is not None:
                self._futures.setdefault(und, {})[inst.expiry] = inst
                expiry_sets.setdefault(und, set()).add(inst.expiry)
                futs += 1

        for und, exps in expiry_sets.items():
            self._expiries[und] = sorted(exps)

        log.info(
            "option_chain_loaded",
            options=opts,
            futures=futs,
            underlyings=len(self._expiries),
        )

    # ── Lookups ──────────────────────────────────────────────────────────────

    def by_symbol(self, tradingsymbol: str) -> Instrument | None:
        return self._by_symbol.get(tradingsymbol)

    def by_token(self, token: int) -> Instrument | None:
        return self._by_token.get(token)

    def expiries(self, underlying: str) -> list[datetime.date]:
        return list(self._expiries.get(underlying, []))

    def nearest_expiry(
        self, underlying: str, ref_date: datetime.date | None = None
    ) -> datetime.date | None:
        """Smallest expiry on/after ref_date (today if None); None if all past."""
        ref = ref_date or datetime.date.today()
        for exp in self._expiries.get(underlying, []):
            if exp >= ref:
                return exp
        return None

    def strikes(
        self, underlying: str, expiry: datetime.date, option_type: OptionType
    ) -> list[float]:
        chain = self._chain.get((underlying, expiry, option_type), {})
        return sorted(chain.keys())

    def atm_strike(
        self,
        underlying: str,
        spot: float,
        expiry: datetime.date,
        option_type: OptionType = OptionType.CE,
    ) -> float | None:
        """The listed strike nearest to spot (uses strikes actually in the chain)."""
        available = self.strikes(underlying, expiry, option_type)
        if not available:
            return None
        return min(available, key=lambda k: abs(k - spot))

    def resolve(
        self,
        underlying: str,
        expiry: datetime.date,
        option_type: OptionType,
        strike: float,
    ) -> Instrument | None:
        return self._chain.get((underlying, expiry, option_type), {}).get(strike)

    def atm_option(
        self,
        underlying: str,
        spot: float,
        option_type: OptionType,
        expiry: datetime.date | None = None,
    ) -> Instrument | None:
        """Resolve the ATM CE/PE for the given (or nearest) expiry."""
        exp = expiry or self.nearest_expiry(underlying)
        if exp is None:
            return None
        strike = self.atm_strike(underlying, spot, exp, option_type)
        if strike is None:
            return None
        return self.resolve(underlying, exp, option_type, strike)

    def future(
        self, underlying: str, expiry: datetime.date | None = None
    ) -> Instrument | None:
        """Resolve the future for the given (or nearest) expiry."""
        by_exp = self._futures.get(underlying, {})
        if not by_exp:
            return None
        exp = expiry or self.nearest_expiry(underlying)
        if exp is None:
            return None
        return by_exp.get(exp)
