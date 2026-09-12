"""
tests/unit/test_agent_router.py — Agent API router integration tests (Phase 4).

Uses FastAPI TestClient with SQLite in-memory DB injected via the module-level
_session_factory hook.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.db.base import Base
from app.models.db.strategy_manifest import StrategyManifest


# ── Per-test client with fresh in-memory DB ───────────────────────────────────

@pytest.fixture()
def client(tmp_path):
    """Per-test TestClient with fresh SQLite DB and seeded ivbs manifest."""
    db_path = str(tmp_path / "test_agent.db")
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    # Seed ivbs manifest
    s = TestSession()
    s.add(StrategyManifest(
        strategy_id="ivbs",
        requirements={"instruments": {"mode": "watchlist"}, "capabilities": ["volume_sma"]},
        capital={"allocated": 200000, "currency": "INR"},
        risk={"max_concurrent": 3, "circuit_breaker_pct": 2.0},
        ui={"panels": []},
        version=1,
        graph={
            "nodes": [{"id": "n0", "type": "volume.sma_multiple", "params": {"lookback": 500}, "inputs": []}],
            "edges": [],
        },
    ))
    s.commit()
    s.close()

    # Inject test session factory
    import app.api.agent_router as ar
    original = ar._session_factory
    ar._session_factory = TestSession

    # Build minimal FastAPI app with just the agent router
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(ar.router, prefix="/api/v1/agent")
    c = TestClient(app, raise_server_exceptions=True)

    yield c

    # Restore
    ar._session_factory = original
    engine.dispose()


# ── GET /proposals ─────────────────────────────────────────────────────────────

class TestListProposals:
    def test_empty_list_returns_200(self, client):
        r = client.get("/api/v1/agent/proposals")
        assert r.status_code == 200
        data = r.json()
        assert "proposals" in data
        assert "count" in data

    def test_returns_proposals_after_propose(self, client):
        payload = {
            "strategy_id": "ivbs",
            "mutation": {
                "nodes_add": [{"id": "n1", "type": "condition.gte", "params": {}, "inputs": ["n0"]}],
                "reason": "Add condition node to test list endpoint works",
            },
            "agent_run_id": "test-run-list",
        }
        r = client.post("/api/v1/agent/propose", json=payload)
        assert r.status_code == 200
        r2 = client.get("/api/v1/agent/proposals")
        assert r2.json()["count"] >= 1


# ── POST /propose ──────────────────────────────────────────────────────────────

class TestPropose:
    def test_valid_proposal_returns_200_with_proposal_id(self, client):
        payload = {
            "strategy_id": "ivbs",
            "mutation": {
                "nodes_add": [{"id": "nx1", "type": "condition.gte", "params": {}, "inputs": ["n0"]}],
                "reason": "Valid proposal for testing the propose endpoint here",
            },
            "agent_run_id": "run-api-001",
        }
        r = client.post("/api/v1/agent/propose", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert "proposal_id" in data
        assert data["status"] == "pending_backtest"
        assert data["strategy_id"] == "ivbs"

    def test_capital_field_in_mutation_is_ignored(self, client):
        """
        Capital field in mutation should be silently ignored by Pydantic.
        AgentIRMutation has no capital field — extra fields are ignored.
        The proposal must succeed (HTTP 200, not 422).
        This is the structural capital guard test.
        """
        payload = {
            "strategy_id": "ivbs",
            "mutation": {
                "nodes_add": [{"id": "nc1", "type": "condition.gte", "params": {}, "inputs": ["n0"]}],
                "reason": "Capital guard test: capital field must be silently ignored here",
                "capital": {"allocated": 9999999},  # must be silently ignored
            },
            "agent_run_id": "capital-guard-test",
        }
        r = client.post("/api/v1/agent/propose", json=payload)
        assert r.status_code == 200  # NOT 422 — capital is simply unknown

    def test_nonexistent_strategy_returns_400(self, client):
        payload = {
            "strategy_id": "does_not_exist_here",
            "mutation": {
                "nodes_add": [{"id": "n1", "type": "condition.gte", "params": {}, "inputs": []}],
                "reason": "Testing non-existent strategy error response code",
            },
            "agent_run_id": "test",
        }
        r = client.post("/api/v1/agent/propose", json=payload)
        assert r.status_code == 400
        assert "not found" in r.json()["detail"]["message"].lower()

    def test_empty_mutation_returns_422(self, client):
        payload = {
            "strategy_id": "ivbs",
            "mutation": {
                "reason": "This mutation is completely empty which should fail here",
            },
            "agent_run_id": "empty-mut",
        }
        r = client.post("/api/v1/agent/propose", json=payload)
        assert r.status_code == 422

    def test_short_reason_returns_422(self, client):
        payload = {
            "strategy_id": "ivbs",
            "mutation": {
                "nodes_add": [{"id": "nx2", "type": "condition.gte", "params": {}, "inputs": ["n0"]}],
                "reason": "short",
            },
            "agent_run_id": "test",
        }
        r = client.post("/api/v1/agent/propose", json=payload)
        assert r.status_code == 422


# ── POST /{id}/backtest ─────────────────────────────────────────────────────────

class TestBacktest:
    def _propose(self, client, suffix="bt"):
        payload = {
            "strategy_id": "ivbs",
            "mutation": {
                "nodes_add": [{"id": f"nbt_{suffix}", "type": "condition.gte", "params": {}, "inputs": ["n0"]}],
                "reason": f"Proposal for backtest testing with suffix {suffix} here",
            },
            "agent_run_id": f"run-{suffix}",
        }
        r = client.post("/api/v1/agent/propose", json=payload)
        assert r.status_code == 200
        return r.json()["proposal_id"]

    def test_backtest_returns_metrics(self, client):
        pid = self._propose(client, "bt1")
        r = client.post(f"/api/v1/agent/{pid}/backtest", json={})
        assert r.status_code == 200
        data = r.json()
        assert "metrics" in data
        assert "win_rate_pct" in data["metrics"]

    def test_backtest_twice_returns_400(self, client):
        pid = self._propose(client, "bt2")
        client.post(f"/api/v1/agent/{pid}/backtest", json={})
        r2 = client.post(f"/api/v1/agent/{pid}/backtest", json={})
        assert r2.status_code == 400

    def test_backtest_nonexistent_returns_404(self, client):
        r = client.post("/api/v1/agent/00000000-0000-0000-0000-000000000000/backtest", json={})
        assert r.status_code == 404


# ── POST /{id}/approve ──────────────────────────────────────────────────────────

class TestApprove:
    def _bt_done(self, client, suffix="ap"):
        payload = {
            "strategy_id": "ivbs",
            "mutation": {
                "nodes_add": [{"id": f"nap_{suffix}", "type": "condition.gte", "params": {}, "inputs": ["n0"]}],
                "reason": f"Proposal for approve testing with suffix {suffix} here",
            },
            "agent_run_id": f"run-{suffix}",
        }
        pid = client.post("/api/v1/agent/propose", json=payload).json()["proposal_id"]
        client.post(f"/api/v1/agent/{pid}/backtest", json={})
        return pid

    def test_approve_backtest_done_returns_200(self, client):
        pid = self._bt_done(client, "ap1")
        r = client.post(f"/api/v1/agent/{pid}/approve", json={"approved_by": "human"})
        assert r.status_code == 200
        assert r.json()["status"] == "pending_paper"

    def test_approve_pending_backtest_returns_400(self, client):
        payload = {
            "strategy_id": "ivbs",
            "mutation": {
                "nodes_add": [{"id": "nap_early", "type": "condition.gte", "params": {}, "inputs": ["n0"]}],
                "reason": "Proposal for early approve test case rejection check",
            },
            "agent_run_id": "early-ap",
        }
        pid = client.post("/api/v1/agent/propose", json=payload).json()["proposal_id"]
        r = client.post(f"/api/v1/agent/{pid}/approve", json={"approved_by": "human"})
        assert r.status_code == 400


# ── POST /{id}/reject ───────────────────────────────────────────────────────────

class TestReject:
    def test_reject_returns_200_with_rejected_status(self, client):
        payload = {
            "strategy_id": "ivbs",
            "mutation": {
                "nodes_add": [{"id": "nrj1", "type": "condition.gte", "params": {}, "inputs": ["n0"]}],
                "reason": "Proposal for rejection endpoint testing this case",
            },
            "agent_run_id": "rej-run",
        }
        pid = client.post("/api/v1/agent/propose", json=payload).json()["proposal_id"]
        r = client.post(f"/api/v1/agent/{pid}/reject", json={"reason": "Does not pass minimum threshold test"})
        assert r.status_code == 200
        assert r.json()["status"] == "rejected"

    def test_reject_already_rejected_returns_400(self, client):
        payload = {
            "strategy_id": "ivbs",
            "mutation": {
                "nodes_add": [{"id": "nrj2", "type": "condition.gte", "params": {}, "inputs": ["n0"]}],
                "reason": "Proposal for double rejection test case endpoint check",
            },
            "agent_run_id": "rej2-run",
        }
        pid = client.post("/api/v1/agent/propose", json=payload).json()["proposal_id"]
        client.post(f"/api/v1/agent/{pid}/reject", json={"reason": "Initial rejection reason is given"})
        r2 = client.post(f"/api/v1/agent/{pid}/reject", json={"reason": "Trying to reject again fails"})
        assert r2.status_code == 400


# ── GET /status-summary ─────────────────────────────────────────────────────────

class TestStatusSummary:
    def test_status_summary_returns_all_statuses(self, client):
        r = client.get("/api/v1/agent/status-summary")
        assert r.status_code == 200
        data = r.json()
        assert "by_status" in data
        assert "pending_action" in data
        from app.models.db.agent_proposal import ProposalStatus
        for s in ProposalStatus:
            assert s.value in data["by_status"]

    def test_pending_action_is_integer(self, client):
        r = client.get("/api/v1/agent/status-summary")
        assert isinstance(r.json()["pending_action"], int)
