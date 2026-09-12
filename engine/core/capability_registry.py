"""
engine/core/capability_registry.py — Capability Provider Registry.

A strategy declares capabilities it needs in its manifest's `requirements.capabilities`
list. At startup the engine resolves each capability key to a registered provider and
makes it available to the strategy through the shared MarketContext.

This is the generalisation of Part2 §6.2 "option_chain / greeks / volume_sma" from a
hard-coded feature list into an open-ended extension point — any future derived-data
need (ML score, news sentiment, IV rank, correlation matrix) registers the same way
without touching StrategyRouter or the manifest schema.

Registry keys (snake_case strings):
    "volume_sma"    — rolling volume SMA from CandleBuilder history
    "option_chain"  — full CE/PE chain for an underlying, resolved from InstrumentMaster
    "greeks"        — Black-Scholes IV, delta, theta, vega for an option instrument
    "iv_rank"       — IV rank vs 52-week IV range (needs HistoricalDataService)

Pattern: Plugin / Extension Point (Part3 §3.1 — §3.2).
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

import structlog

from engine.core.registry import Registry

if TYPE_CHECKING:
    import datetime

    from engine.kite.client import AsyncKiteClient
    from engine.store.redis_store import RedisStore

log = structlog.get_logger(__name__)


# ── MarketContext ─────────────────────────────────────────────────────────────

@dataclasses.dataclass(slots=True)
class MarketContext:
    """
    Snapshot of all market data relevant to a single capability computation.

    Passed to every CapabilityProvider.compute() call. Fields that are not
    available for a given call site are left as None — providers must handle
    None inputs gracefully.

    Attributes:
        symbol:         Primary NSE/NFO tradingsymbol.
        underlying:     Underlying symbol for F&O (e.g. "NIFTY" for "NIFTY23SEP18000CE").
        spot_price:     Last-traded price of `symbol` (or underlying if F&O).
        candle_builder: Active CandleBuilder for symbol — gives access to OHLCV,
                        volume SMA, VWAP history.
        redis_store:    Active Redis store — for cross-strategy state lookups.
        kite:           Live AsyncKiteClient — for real-time quote / option chain.
        extra:          Arbitrary key→value bag for provider-specific inputs.
    """
    symbol: str
    underlying: str = ""
    spot_price: float = 0.0
    candle_builder: Any = None          # CandleBuilder (avoid circular import)
    redis_store: "RedisStore | None" = None
    kite: "AsyncKiteClient | None" = None
    extra: dict[str, Any] = dataclasses.field(default_factory=dict)


# ── CapabilityProvider Protocol ───────────────────────────────────────────────

@runtime_checkable
class CapabilityProvider(Protocol):
    """
    Interface every capability provider must implement.

    A provider is stateless (or holds only shared read-only state like a
    reference to InstrumentMaster). All mutable, per-computation state lives
    in the `MarketContext` passed to `compute()`.

    Implementing classes:
        VolumeSmaProvider, OptionChainProvider, GreeksProvider, IVRankProvider
        (engine/market/capabilities/*.py)
    """

    key: str  # Registry key — must be unique, snake_case

    async def compute(self, ctx: MarketContext) -> Any:
        """
        Compute and return the capability's output.

        Must NOT raise — log and return None on any internal error so that a
        broken capability provider never blocks strategy execution.

        Args:
            ctx: Full market context at the time of the request.

        Returns:
            Provider-specific value (dict, float, list, dataclass, etc.).
            None if computation is not possible (missing data, API error).
        """
        ...


# ── Singleton Registry ────────────────────────────────────────────────────────

#: Global capability registry — populated at engine startup by runner.py.
#: Strategies resolve providers at runtime via ``capability_registry.get(key)``.
capability_registry: Registry[CapabilityProvider] = Registry()


def register_default_capabilities() -> None:
    """Register built-in capability providers if not already registered."""
    try:
        from engine.market.capabilities import (
            GreeksProvider,
            IVRankProvider,
            OptionChainProvider,
            VolumeSmaProvider,
        )
        if "volume_sma" not in capability_registry.list_keys():
            capability_registry.register("volume_sma", VolumeSmaProvider())
        if "option_chain" not in capability_registry.list_keys():
            capability_registry.register("option_chain", OptionChainProvider())
        if "greeks" not in capability_registry.list_keys():
            capability_registry.register("greeks", GreeksProvider())
        if "iv_rank" not in capability_registry.list_keys():
            capability_registry.register("iv_rank", IVRankProvider())
    except Exception as exc:
        log.warning("capability_registry_default_register_failed", error=str(exc))


register_default_capabilities()


# ── Fan-out helper ────────────────────────────────────────────────────────────

async def compute_capabilities(
    keys: list[str],
    ctx: MarketContext,
) -> dict[str, Any]:
    """
    Compute multiple capabilities in sequence and return results as a dict.

    Missing keys (not registered) are logged as warnings and skipped — the
    returned dict will simply not contain those keys. This allows strategies
    to declare capabilities speculatively in their manifest without crashing
    if a provider has not been registered yet.

    Args:
        keys: Capability keys to compute (from manifest requirements block).
        ctx:  Shared MarketContext for this computation round.

    Returns:
        Mapping of key → compute() result for every successfully registered key.

    Edge cases:
        - Empty `keys` → returns {} immediately.
        - Provider raises → logged as ERROR, key excluded from result.
        - Provider returns None → included in result (None is a valid output).
    """
    if not keys:
        return {}

    results: dict[str, Any] = {}
    for key in keys:
        provider = capability_registry.get_or_none(key)
        if provider is None:
            log.warning(
                "capability_provider_not_registered",
                key=key,
                hint="Register a provider in runner.py before this strategy activates.",
            )
            continue
        try:
            results[key] = await provider.compute(ctx)
        except Exception as exc:
            log.error(
                "capability_provider_compute_failed",
                key=key,
                error=str(exc),
                exc_info=True,
            )
    return results
