"""
engine/market/capabilities/option_chain_provider.py — Option chain capability.

Resolves a full CE+PE strike ladder for a given underlying via InstrumentMaster.
Strategies consuming this capability receive a list of Instrument objects — they
never need to import or know about OptionChainResolver directly.

Registry key: "option_chain"

Input (via ctx.extra):
    underlying:       str   — e.g. "NIFTY", "BANKNIFTY"
    expiry:           date  — specific expiry, or nearest if omitted
    strike_range_pct: float — e.g. 0.05 = ±5% from ATM (default 0.05)
    option_type:      "CE" | "PE" | "BOTH" (default "BOTH")

Output shape:
    {
        "underlying": str,
        "expiry":     str (ISO date),
        "atm_strike": float | None,
        "ce": list[Instrument],   # sorted by strike ascending
        "pe": list[Instrument],   # sorted by strike ascending
        "total": int,
    }
    None if NFO dump not loaded or underlying not found.
"""

from __future__ import annotations

import datetime
from typing import Any

import structlog

from engine.core.capability_registry import CapabilityProvider, MarketContext
from engine.core.instrument import Instrument, OptionType

log = structlog.get_logger(__name__)

# Lazy import to avoid circular deps at module level
_instrument_master = None


def _get_master():
    global _instrument_master
    if _instrument_master is None:
        from engine.market.instrument_master import instrument_master
        _instrument_master = instrument_master
    return _instrument_master


class OptionChainProvider:
    """
    Resolves option chain from the in-memory NFO index (OptionChainResolver).

    No I/O — all data is loaded at pre-market setup. This provider simply wraps
    InstrumentMaster into the capability contract.

    Edge cases:
        - NFO not loaded → logs CRITICAL, returns None.
        - Underlying not in index → logs warning, returns None.
        - spot_price == 0 (no live tick yet) → atm_strike = None, full chain returned.
        - strike_range_pct = 0 → return only ATM strike instruments.
    """

    key = "option_chain"

    async def compute(self, ctx: MarketContext) -> dict[str, Any] | None:
        master = _get_master()
        underlying = ctx.extra.get("underlying") or ctx.underlying or ctx.symbol
        strike_range_pct = float(ctx.extra.get("strike_range_pct", 0.05))
        opt_type_str = ctx.extra.get("option_type", "BOTH").upper()

        # Resolve expiry
        expiry_raw = ctx.extra.get("expiry")
        if expiry_raw is None:
            expiry = master.nearest_expiry(underlying)
        elif isinstance(expiry_raw, datetime.date):
            expiry = expiry_raw
        else:
            try:
                expiry = datetime.date.fromisoformat(str(expiry_raw))
            except ValueError:
                log.error("option_chain_invalid_expiry", expiry=expiry_raw)
                return None

        if expiry is None:
            log.warning(
                "option_chain_no_expiry",
                underlying=underlying,
                hint="NFO dump may not be loaded or underlying has no listed expiry.",
            )
            return None

        resolver = master.option_chain_resolver()

        # ATM strike
        atm_strike: float | None = None
        if ctx.spot_price > 0:
            atm_strike = master.atm_strike(
                underlying, ctx.spot_price, expiry, OptionType.CE
            )

        # Resolve CE instruments
        ce_instruments: list[Instrument] = []
        pe_instruments: list[Instrument] = []

        if opt_type_str in ("CE", "BOTH"):
            ce_instruments = _filter_by_range(
                resolver.strikes(underlying, expiry, OptionType.CE),
                resolver,
                underlying, expiry, OptionType.CE,
                atm_strike, strike_range_pct,
            )

        if opt_type_str in ("PE", "BOTH"):
            pe_instruments = _filter_by_range(
                resolver.strikes(underlying, expiry, OptionType.PE),
                resolver,
                underlying, expiry, OptionType.PE,
                atm_strike, strike_range_pct,
            )

        return {
            "underlying": underlying,
            "expiry": expiry.isoformat(),
            "atm_strike": atm_strike,
            "ce": ce_instruments,
            "pe": pe_instruments,
            "total": len(ce_instruments) + len(pe_instruments),
        }


def _filter_by_range(
    strikes: list[float],
    resolver: Any,
    underlying: str,
    expiry: datetime.date,
    option_type: OptionType,
    atm_strike: float | None,
    range_pct: float,
) -> list[Instrument]:
    """Return instruments within ±range_pct of ATM. Returns all if no ATM."""
    result: list[Instrument] = []
    for s in sorted(strikes):
        if atm_strike is not None and range_pct > 0:
            if abs(s - atm_strike) / atm_strike > range_pct:
                continue
        inst = resolver._chain.get((underlying, expiry, option_type), {}).get(s)
        if inst is not None:
            result.append(inst)
    return result
