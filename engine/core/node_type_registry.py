"""
engine/core/node_type_registry.py — IR graph node type registry.

Every node type in a strategy's IR graph is registered here.  When the
RuleEngineStrategy walks the graph, it resolves each node's `type` field
via this registry to get the evaluator function.

This registry is what allows adding a new indicator (e.g., "rsi_cross",
"macd_signal", "pattern.hammer") without touching the IR interpreter —
the new evaluator is just registered here at startup.

Structure:
    node_type_registry.register("volume.sma_multiple", volume_sma_evaluator)
    node_type_registry.register("price.breakout", price_breakout_evaluator)
    node_type_registry.register("logic.and", and_evaluator)

Each evaluator is a callable:
    async def evaluator(node: dict, ctx: NodeContext) -> NodeResult
"""

from __future__ import annotations

from engine.core.registry import Registry


class NodeContext:
    """
    Context passed to each node evaluator.

    Contains all the live data needed to evaluate an IR node:
    the current candle, the CandleBuilder (for SMA, ATR), the Instrument,
    and any previous node results in the same evaluation pass.
    """
    def __init__(
        self,
        symbol: str,
        candle: object,          # engine.market.candle_builder.Candle
        builder: object,         # engine.market.candle_builder.CandleBuilder
        instrument_token: int,
        node_results: dict,      # node_id -> NodeResult (for chained evaluations)
    ) -> None:
        self.symbol = symbol
        self.candle = candle
        self.builder = builder
        self.instrument_token = instrument_token
        self.node_results = node_results


class NodeResult:
    """
    Result of a single node evaluation.

    value: the numeric output (e.g., SMA, ATR, breakout price)
    passed: whether the node's condition evaluated to True
    metadata: optional dict for debugging (actual values vs thresholds)
    """
    def __init__(
        self,
        value: float,
        passed: bool,
        metadata: dict | None = None,
    ) -> None:
        self.value = value
        self.passed = passed
        self.metadata = metadata or {}


# Global node type registry — populated by engine/core/plugins.py at startup.
# Key format: "{category}.{name}" e.g. "volume.sma_multiple", "logic.and"
node_type_registry: Registry[object] = Registry("node_type")
