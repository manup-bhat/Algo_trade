"""
engine/agent/ir_mutation.py — Agent IR Mutation model.

Defines the ONLY shape an agent may submit to the platform (Part 3 §Phase 4.1):
  - Nodes/edges to add, remove, or patch.
  - A mandatory reason string (agent must justify every mutation).

Fields explicitly ABSENT (structural capital guard):
  - capital / capital.allocated  — remains human-set via CapitalAllocatorRule.
  - risk.circuit_breaker_pct     — remains human-set.
  - Any broker or order fields   — agents never issue broker calls.

Pydantic validates this structurally: a caller cannot pass `capital` because
the model has no such field — FastAPI returns HTTP 422 before any handler code
runs. This is the correct enforcement layer (schema, not runtime check).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Sub-models ────────────────────────────────────────────────────────────────

class IRNode(BaseModel):
    """A single node in the StrategyIR graph."""
    id: str = Field(..., min_length=1, description="Unique node ID within the graph")
    type: str = Field(..., min_length=1, description="Node type key (must be in node_type_registry)")
    params: dict[str, Any] = Field(default_factory=dict, description="Node-specific parameters")
    inputs: list[str] = Field(
        default_factory=list,
        description="IDs of upstream nodes whose output feeds into this node",
    )


class IRNodePatch(BaseModel):
    """A partial update to an existing node's params (does not change type or wiring)."""
    id: str = Field(..., min_length=1, description="ID of the node to patch")
    params: dict[str, Any] = Field(
        ...,
        min_length=1,
        description="Param keys to update — only listed keys are changed, others are preserved",
    )


class IREdge(BaseModel):
    """A directed data-flow edge between two nodes."""
    from_id: str = Field(..., min_length=1, description="Source node ID")
    to_id: str = Field(..., min_length=1, description="Destination node ID")


# ── Main mutation model ───────────────────────────────────────────────────────

class AgentIRMutation(BaseModel):
    """
    The complete specification of a StrategyIR mutation proposed by the agent.

    Only structural graph changes are allowed:
      - nodes_add    : new IRNode objects to insert into the graph
      - nodes_remove : IDs of existing nodes to delete (and their edges)
      - nodes_patch  : partial param updates to existing nodes
      - edges_add    : new directed edges to wire nodes together
      - edges_remove : existing edges to remove
      - reason       : mandatory agent rationale for audit/lineage

    No capital, risk, or broker fields. FastAPI/Pydantic enforce this at
    the schema level — no extra validation code required.

    At least one of nodes_add / nodes_remove / nodes_patch / edges_add /
    edges_remove must be non-empty (empty proposals are rejected).
    """

    # ── Graph mutations ───────────────────────────────────────────────────────
    nodes_add: list[IRNode] = Field(
        default_factory=list,
        description="New nodes to add to the graph",
    )
    nodes_remove: list[str] = Field(
        default_factory=list,
        description="IDs of existing nodes to remove (their edges are also removed)",
    )
    nodes_patch: list[IRNodePatch] = Field(
        default_factory=list,
        description="Partial param updates to existing nodes",
    )
    edges_add: list[IREdge] = Field(
        default_factory=list,
        description="New directed data-flow edges to add",
    )
    edges_remove: list[IREdge] = Field(
        default_factory=list,
        description="Existing edges to remove",
    )

    # ── Mandatory audit field ─────────────────────────────────────────────────
    reason: str = Field(
        ...,
        min_length=10,
        description=(
            "Agent-provided rationale for this mutation — required for lineage "
            "and human review. Must be at least 10 characters."
        ),
    )

    # ── Validators ────────────────────────────────────────────────────────────

    @field_validator("nodes_add", mode="before")
    @classmethod
    def _validate_nodes_add(cls, v: list) -> list:
        """Ensure no duplicate IDs in the add list."""
        ids = [n.get("id") if isinstance(n, dict) else getattr(n, "id", None) for n in v]
        seen = set()
        for nid in ids:
            if nid in seen:
                raise ValueError(f"Duplicate node ID in nodes_add: {nid!r}")
            seen.add(nid)
        return v

    @field_validator("nodes_remove", mode="before")
    @classmethod
    def _validate_nodes_remove(cls, v: list) -> list:
        """Ensure no duplicate IDs in the remove list."""
        if len(set(v)) != len(v):
            raise ValueError("Duplicate IDs in nodes_remove")
        return v

    @model_validator(mode="after")
    def _at_least_one_change(self) -> "AgentIRMutation":
        """Reject empty mutations — at least one list must be non-empty."""
        if not any([
            self.nodes_add,
            self.nodes_remove,
            self.nodes_patch,
            self.edges_add,
            self.edges_remove,
        ]):
            raise ValueError(
                "Mutation is empty — at least one of nodes_add / nodes_remove / "
                "nodes_patch / edges_add / edges_remove must be non-empty"
            )
        return self

    # ── Helpers ───────────────────────────────────────────────────────────────

    def apply_to(self, base_graph: dict[str, Any]) -> dict[str, Any]:
        """
        Apply this mutation to a base StrategyIR graph and return the new graph.

        The base_graph is never mutated in place — a deep copy is made first.

        Args:
            base_graph: Current graph dict with keys ``nodes`` and optionally
                        ``edges``. Nodes are dicts with at minimum ``id``,
                        ``type``, ``params``, ``inputs``.

        Returns:
            New graph dict after applying all changes in this mutation.

        Raises:
            ValueError: If a nodes_remove or nodes_patch targets a non-existent
                        node ID, or if an edges_remove targets a non-existent edge.
        """
        import copy
        graph = copy.deepcopy(base_graph)
        nodes: list[dict] = graph.get("nodes", [])
        edges: list[dict] = graph.get("edges", [])

        node_by_id: dict[str, dict] = {n["id"]: n for n in nodes}

        # 1. Remove nodes (and prune their edges from inputs of remaining nodes)
        removed_ids: set[str] = set(self.nodes_remove)
        for rid in removed_ids:
            if rid not in node_by_id:
                raise ValueError(f"nodes_remove: node ID {rid!r} not found in graph")
        nodes = [n for n in nodes if n["id"] not in removed_ids]
        node_by_id = {n["id"]: n for n in nodes}
        # Prune dangling inputs on remaining nodes
        for n in nodes:
            n["inputs"] = [i for i in n.get("inputs", []) if i not in removed_ids]

        # 2. Remove edges
        remove_edge_set = {(e.from_id, e.to_id) for e in self.edges_remove}
        edges = [
            e for e in edges
            if (e.get("from_id"), e.get("to_id")) not in remove_edge_set
        ]

        # 3. Patch existing nodes
        for patch in self.nodes_patch:
            if patch.id not in node_by_id:
                raise ValueError(f"nodes_patch: node ID {patch.id!r} not found in graph")
            node_by_id[patch.id]["params"].update(patch.params)

        # 4. Add nodes
        for new_node in self.nodes_add:
            if new_node.id in node_by_id:
                raise ValueError(f"nodes_add: node ID {new_node.id!r} already exists in graph")
            node_dict = new_node.model_dump()
            nodes.append(node_dict)
            node_by_id[new_node.id] = node_dict

        # 5. Add edges
        existing_edge_set = {(e.get("from_id"), e.get("to_id")) for e in edges}
        for edge in self.edges_add:
            pair = (edge.from_id, edge.to_id)
            if pair not in existing_edge_set:
                edges.append({"from_id": edge.from_id, "to_id": edge.to_id})
                existing_edge_set.add(pair)
            # Also wire into the destination node's inputs list if not already there
            if edge.to_id in node_by_id:
                inputs = node_by_id[edge.to_id].get("inputs", [])
                if edge.from_id not in inputs:
                    node_by_id[edge.to_id]["inputs"] = inputs + [edge.from_id]

        graph["nodes"] = nodes
        graph["edges"] = edges
        return graph
