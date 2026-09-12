# engine/market/capabilities/__init__.py
"""
engine/market/capabilities — Built-in CapabilityProvider implementations.

Each provider registers itself with the capability_registry at engine startup
(see engine/runner.py). Strategies request capabilities via their manifest's
`requirements.capabilities` list and receive results via `compute_capabilities()`.
"""
from engine.market.capabilities.volume_sma_provider import VolumeSmaProvider
from engine.market.capabilities.option_chain_provider import OptionChainProvider
from engine.market.capabilities.greeks_provider import GreeksProvider
from engine.market.capabilities.iv_rank_provider import IVRankProvider

__all__ = [
    "VolumeSmaProvider",
    "OptionChainProvider",
    "GreeksProvider",
    "IVRankProvider",
]
