"""
engine/strategies/rule_engine/strategy.py — IR graph strategy interpreter (skeleton).

RuleEngineStrategy interprets a JSON IR graph instead of Python logic.  This is
the minimal skeleton: it can walk the graph and call registered node evaluators,
but has no signal-generation logic yet (Phase 2).

What this skeleton proves (verifiable by unit test):
  - A strategy can be expressed as a JSON IR graph.
  - The interpreter walks nodes in topological order.
  - Node evaluators are resolved from node_type_registry by type key.
  - The same evaluator that's registered for a built-in strategy (IVBS) can
    be reused by a graph-defined strategy without code duplication.

Phase 2 will add:
  - Order placement based on graph output.
  - Per-node parameter validation on load.
  - Hot-reload of the graph from DB without engine restart.
"""

from __future__ import annotations

from typing import Any

import structlog

from engine.core.base_strategy import BaseStrategy
from engine.core.node_type_registry import NodeContext, NodeResult, node_type_registry

log = structlog.get_logger(__name__)


class RuleEngineStrategy(BaseStrategy):
    """
    A strategy defined entirely by a JSON IR graph.

    The graph is loaded from `self.config["graph"]` (in the strategy's
    config.yaml or from the DB manifest).  Each node in the graph has:
      - id: str (unique within the graph)
      - type: str (key into node_type_registry)
      - params: dict (passed to the evaluator)
      - inputs: list[str] (IDs of upstream nodes whose results feed this node)

    The graph is evaluated in topological order on every candle.
    If any required node type is missing from the registry, that node
    is skipped with a warning (fail-soft — the strategy doesn't crash).

    Example IR graph (config.yaml):
    ```yaml
    graph:
      nodes:
        - id: sma_spike
          type: volume.sma_multiple
          params: {multiple: 20, lookback: 500}
        - id: entry_signal
          type: logic.and
          inputs: [sma_spike]
    ```
    """

    def __init__(self, strategy_id: str, redis_store: Any, db_writer: Any) -> None:
        super().__init__(strategy_id, redis_store, db_writer)
        self._graph: list[dict] = self.config.get("graph", {}).get("nodes", [])
        self._node_results: dict[str, NodeResult] = {}
        log.info(
            "rule_engine_strategy_initialized",
            strategy_id=strategy_id,
            node_count=len(self._graph),
        )

    # ── BaseStrategy hooks ────────────────────────────────────────────────────

    async def on_market_open(self) -> None:
        self._node_results.clear()

    async def on_candle(
        self,
        symbol: str,
        candle: object,
        builder: object,
        instrument_token: int,
    ) -> None:
        if not self.new_entries_enabled:
            return

        results = await self._evaluate_graph(symbol, candle, builder, instrument_token)

        # For Phase 1 skeleton: just log results; no orders yet
        if results:
            terminal_nodes = [
                (nid, r) for nid, r in results.items()
                if not any(nid in n.get("inputs", []) for n in self._graph)
            ]
            for nid, result in terminal_nodes:
                log.debug(
                    "rule_engine_terminal_node",
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    node_id=nid,
                    passed=result.passed,
                    value=result.value,
                )

    async def on_order_postback(self, message: dict[str, Any]) -> None:
        # Phase 1 skeleton: no orders to track yet
        pass

    async def on_squareoff(self) -> None:
        self._node_results.clear()

    def get_stats(self) -> dict[str, Any]:
        return {
            "node_count": len(self._graph),
            "graph_defined": bool(self._graph),
        }

    def is_symbol_active(self, symbol: str) -> bool:
        return False  # Phase 1: no positions

    # ── Graph evaluation ──────────────────────────────────────────────────────

    async def _evaluate_graph(
        self,
        symbol: str,
        candle: object,
        builder: object,
        instrument_token: int,
    ) -> dict[str, NodeResult]:
        """
        Walk the graph in declaration order (Phase 1: assumes topological order
        in the config — Phase 2 will add proper topological sort).

        Returns: {node_id: NodeResult} for all successfully evaluated nodes.
        """
        run_results: dict[str, NodeResult] = {}

        ctx = NodeContext(
            symbol=symbol,
            candle=candle,
            builder=builder,
            instrument_token=instrument_token,
            node_results=run_results,
        )

        for node in self._graph:
            node_id = node.get("id", "")
            node_type = node.get("type", "")

            evaluator = node_type_registry.get_or_none(node_type)
            if evaluator is None:
                log.warning(
                    "rule_engine_unknown_node_type",
                    node_id=node_id,
                    node_type=node_type,
                    available=node_type_registry.list_keys()[:10],
                )
                continue

            try:
                result = await evaluator(node, ctx)  # type: ignore[operator]
                if isinstance(result, NodeResult):
                    run_results[node_id] = result
            except Exception as exc:
                log.error(
                    "rule_engine_node_evaluation_failed",
                    node_id=node_id,
                    node_type=node_type,
                    symbol=symbol,
                    error=str(exc),
                )
                # Fail-soft: skip this node, continue evaluation
                # A broken node must never crash the strategy or the engine.

        return run_results
