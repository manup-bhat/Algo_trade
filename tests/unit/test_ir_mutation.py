"""
tests/unit/test_ir_mutation.py — AgentIRMutation model tests (Phase 4).

Tests the structural capital guard (no capital field), graph mutation logic
(apply_to), and validation edge cases.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from engine.agent.ir_mutation import AgentIRMutation, IREdge, IRNode, IRNodePatch


# ── Helpers ───────────────────────────────────────────────────────────────────

def _minimal_mutation(**kwargs) -> dict:
    """Minimal valid mutation payload — adds one node."""
    base = {
        "nodes_add": [{"id": "n1", "type": "volume.sma_multiple", "params": {}, "inputs": []}],
        "reason": "Add a volume SMA indicator node",
    }
    base.update(kwargs)
    return base


def _two_node_graph() -> dict:
    return {
        "nodes": [
            {"id": "n1", "type": "volume.sma_multiple", "params": {"lookback": 500}, "inputs": []},
            {"id": "n2", "type": "condition.gte", "params": {}, "inputs": ["n1"]},
        ],
        "edges": [{"from_id": "n1", "to_id": "n2"}],
    }


# ── Capital guard — structural absence of capital field ───────────────────────

class TestCapitalGuard:
    """AgentIRMutation has no capital/risk fields — Pydantic rejects them."""

    def test_capital_field_rejected_as_extra(self):
        """If a caller passes 'capital', Pydantic strips it (extra='ignore') or raises."""
        # AgentIRMutation uses model defaults — extra fields are ignored
        m = AgentIRMutation(**_minimal_mutation(), capital={"allocated": 500000})
        # capital should NOT be accessible on the model — it was silently ignored
        assert not hasattr(m, "capital")

    def test_nodes_only_no_capital_attribute(self):
        m = AgentIRMutation(**_minimal_mutation())
        assert not hasattr(m, "capital")
        assert not hasattr(m, "risk")

    def test_broker_fields_rejected(self):
        """Broker/order fields have no place on the mutation model."""
        m = AgentIRMutation(**_minimal_mutation(), order_type="MARKET", quantity=10)
        assert not hasattr(m, "order_type")
        assert not hasattr(m, "quantity")

    def test_circuit_breaker_field_absent(self):
        m = AgentIRMutation(**_minimal_mutation())
        assert not hasattr(m, "circuit_breaker_pct")

    def test_allocated_field_absent(self):
        m = AgentIRMutation(**_minimal_mutation())
        assert not hasattr(m, "allocated")


# ── Empty mutation rejected ───────────────────────────────────────────────────

class TestEmptyMutation:
    def test_all_empty_lists_rejected(self):
        with pytest.raises(ValidationError, match="empty"):
            AgentIRMutation(reason="This mutation adds nothing at all to test it")

    def test_reason_too_short_rejected(self):
        with pytest.raises(ValidationError):
            AgentIRMutation(
                nodes_add=[IRNode(id="n1", type="volume.sma_multiple")],
                reason="short",
            )

    def test_reason_exactly_10_chars_accepted(self):
        m = AgentIRMutation(
            nodes_add=[IRNode(id="n1", type="volume.sma_multiple")],
            reason="1234567890",
        )
        assert m.reason == "1234567890"


# ── Duplicate node IDs rejected ───────────────────────────────────────────────

class TestDuplicateIds:
    def test_duplicate_in_nodes_add_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate"):
            AgentIRMutation(
                nodes_add=[
                    IRNode(id="n1", type="volume.sma_multiple"),
                    IRNode(id="n1", type="condition.gte"),
                ],
                reason="Duplicate ID should be rejected by validator",
            )

    def test_duplicate_in_nodes_remove_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate"):
            AgentIRMutation(
                nodes_remove=["n1", "n1"],
                reason="Duplicate remove IDs should be rejected here",
            )


# ── apply_to — nodes_add ─────────────────────────────────────────────────────

class TestApplyToNodesAdd:
    def test_add_node_to_empty_graph(self):
        m = AgentIRMutation(**_minimal_mutation())
        result = m.apply_to({"nodes": [], "edges": []})
        assert len(result["nodes"]) == 1
        assert result["nodes"][0]["id"] == "n1"
        assert result["nodes"][0]["type"] == "volume.sma_multiple"

    def test_add_node_preserves_existing_nodes(self):
        m = AgentIRMutation(**_minimal_mutation(nodes_add=[{"id":"n3","type":"logic.and","params":{},"inputs":[]}]))
        result = m.apply_to(_two_node_graph())
        ids = {n["id"] for n in result["nodes"]}
        assert ids == {"n1", "n2", "n3"}

    def test_add_node_duplicate_id_raises(self):
        m = AgentIRMutation(**_minimal_mutation(nodes_add=[{"id":"n1","type":"logic.and","params":{},"inputs":[]}]))
        with pytest.raises(ValueError, match="already exists"):
            m.apply_to(_two_node_graph())

    def test_add_node_with_params(self):
        m = AgentIRMutation(
            nodes_add=[IRNode(id="n5", type="volume.sma_multiple", params={"lookback": 200, "multiple": 15})],
            reason="Adding node with specific params to test this",
        )
        result = m.apply_to({"nodes": [], "edges": []})
        assert result["nodes"][0]["params"] == {"lookback": 200, "multiple": 15}


# ── apply_to — nodes_remove ──────────────────────────────────────────────────

class TestApplyToNodesRemove:
    def test_remove_existing_node(self):
        m = AgentIRMutation(nodes_remove=["n1"], reason="Remove the SMA node from graph")
        result = m.apply_to(_two_node_graph())
        ids = [n["id"] for n in result["nodes"]]
        assert "n1" not in ids
        assert "n2" in ids

    def test_remove_prunesinputs_of_remaining_nodes(self):
        m = AgentIRMutation(nodes_remove=["n1"], reason="Remove n1 and prune inputs of n2 here")
        result = m.apply_to(_two_node_graph())
        n2 = next(n for n in result["nodes"] if n["id"] == "n2")
        assert "n1" not in n2["inputs"]

    def test_remove_nonexistent_node_raises(self):
        m = AgentIRMutation(nodes_remove=["nX"], reason="Attempt to remove a non-existent node ID")
        with pytest.raises(ValueError, match="not found"):
            m.apply_to(_two_node_graph())


# ── apply_to — nodes_patch ───────────────────────────────────────────────────

class TestApplyToNodesPatch:
    def test_patch_existing_node_params(self):
        m = AgentIRMutation(
            nodes_patch=[IRNodePatch(id="n1", params={"lookback": 1000, "multiple": 25})],
            reason="Increase lookback and multiple params of n1 node",
        )
        result = m.apply_to(_two_node_graph())
        n1 = next(n for n in result["nodes"] if n["id"] == "n1")
        assert n1["params"]["lookback"] == 1000
        assert n1["params"]["multiple"] == 25

    def test_patch_merges_not_replaces(self):
        """Patch only updates listed keys — existing keys not in patch are preserved."""
        m = AgentIRMutation(
            nodes_patch=[IRNodePatch(id="n1", params={"multiple": 30})],
            reason="Patch only the multiple param value preserving others",
        )
        graph = {"nodes": [{"id":"n1","type":"volume.sma_multiple","params":{"lookback":500,"multiple":20},"inputs":[]}], "edges":[]}
        result = m.apply_to(graph)
        assert result["nodes"][0]["params"]["lookback"] == 500  # preserved
        assert result["nodes"][0]["params"]["multiple"] == 30   # updated

    def test_patch_nonexistent_node_raises(self):
        m = AgentIRMutation(
            nodes_patch=[IRNodePatch(id="nX", params={"lookback": 100})],
            reason="Patch a node that does not exist in the graph here",
        )
        with pytest.raises(ValueError, match="not found"):
            m.apply_to(_two_node_graph())


# ── apply_to — edges ─────────────────────────────────────────────────────────

class TestApplyToEdges:
    def test_add_edge(self):
        m = AgentIRMutation(
            nodes_add=[IRNode(id="n3", type="logic.and", inputs=["n2"])],
            edges_add=[IREdge(from_id="n2", to_id="n3")],
            reason="Add a logic.and combiner node wired to condition",
        )
        result = m.apply_to(_two_node_graph())
        edge_pairs = {(e["from_id"], e["to_id"]) for e in result["edges"]}
        assert ("n2", "n3") in edge_pairs

    def test_remove_edge(self):
        m = AgentIRMutation(
            edges_remove=[IREdge(from_id="n1", to_id="n2")],
            reason="Remove the edge between n1 and n2 nodes in graph",
        )
        result = m.apply_to(_two_node_graph())
        edge_pairs = {(e["from_id"], e["to_id"]) for e in result["edges"]}
        assert ("n1", "n2") not in edge_pairs

    def test_add_duplicate_edge_not_duplicated(self):
        m = AgentIRMutation(
            edges_add=[IREdge(from_id="n1", to_id="n2")],
            reason="Adding an edge that already exists should not duplicate it",
        )
        result = m.apply_to(_two_node_graph())
        pairs = [(e["from_id"], e["to_id"]) for e in result["edges"]]
        assert pairs.count(("n1", "n2")) == 1


# ── apply_to — immutability of base graph ───────────────────────────────────

class TestApplyToImmutability:
    def test_base_graph_not_mutated(self):
        base = _two_node_graph()
        import copy
        original = copy.deepcopy(base)
        m = AgentIRMutation(nodes_remove=["n1"], reason="Test that apply_to does not mutate base graph")
        m.apply_to(base)
        assert base == original
