"""
tests/unit/test_agent_loop.py — AgentLoopService tests (Phase 4).

Uses SQLite in-memory DB.  Each test gets a fresh synchronous SQLAlchemy
session. AgentLoopService methods are all synchronous — no async needed.
"""
from __future__ import annotations

from typing import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models.db.base import Base
from app.models.db.agent_proposal import AgentProposal, ProposalStatus
from app.models.db.strategy_manifest import StrategyManifest
from engine.agent.agent_loop import AgentLoopService, _validate_graph, _kahn_topo
from engine.agent.ir_mutation import AgentIRMutation, IRNode


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def engine():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session(engine) -> Generator[Session, None, None]:
    SessionLocal = sessionmaker(bind=engine)
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture()
def ivbs_manifest(session: Session) -> StrategyManifest:
    m = StrategyManifest(
        strategy_id="ivbs",
        requirements={"instruments": {"mode": "watchlist"}, "capabilities": ["volume_sma"]},
        capital={"allocated": 200000, "currency": "INR"},
        risk={"max_concurrent": 3, "circuit_breaker_pct": 2.0},
        ui={"panels": []},
        version=1,
        graph={"nodes": [{"id":"n0","type":"volume.sma_multiple","params":{"lookback":500},"inputs":[]}], "edges":[]},
    )
    session.add(m)
    session.commit()
    return m


@pytest.fixture()
def svc() -> AgentLoopService:
    return AgentLoopService()


def _valid_mutation(**kwargs) -> AgentIRMutation:
    base = {
        "nodes_add": [{"id":"n1","type":"condition.gte","params":{},"inputs":["n0"]}],
        "reason": "Add a condition node to filter volume spikes",
    }
    base.update(kwargs)
    return AgentIRMutation(**base)


# ── _kahn_topo ────────────────────────────────────────────────────────────────

class TestKahnTopo:
    def test_empty_graph(self):
        assert _kahn_topo([]) == []

    def test_single_node(self):
        assert _kahn_topo([{"id":"n1","inputs":[]}]) == ["n1"]

    def test_linear_chain(self):
        nodes = [
            {"id":"a","inputs":[]},
            {"id":"b","inputs":["a"]},
            {"id":"c","inputs":["b"]},
        ]
        order = _kahn_topo(nodes)
        assert order == ["a","b","c"]

    def test_cycle_returns_none(self):
        nodes = [
            {"id":"a","inputs":["b"]},
            {"id":"b","inputs":["a"]},
        ]
        assert _kahn_topo(nodes) is None


# ── _validate_graph ───────────────────────────────────────────────────────────

class TestValidateGraph:
    def test_empty_graph_has_error(self):
        errs = _validate_graph({"nodes": []})
        assert any("at least one" in e for e in errs)

    def test_node_missing_type_has_error(self):
        errs = _validate_graph({"nodes":[{"id":"n1","type":"","params":{},"inputs":[]}]})
        assert any("type" in e for e in errs)

    def test_dangling_input_reference_has_error(self):
        errs = _validate_graph({"nodes":[{"id":"n1","type":"volume.sma_multiple","params":{},"inputs":["n99"]}]})
        assert any("n99" in e for e in errs)

    def test_duplicate_ids_have_error(self):
        nodes = [
            {"id":"n1","type":"volume.sma_multiple","params":{},"inputs":[]},
            {"id":"n1","type":"condition.gte","params":{},"inputs":[]},
        ]
        errs = _validate_graph({"nodes": nodes})
        assert any("Duplicate" in e for e in errs)

    def test_cycle_detected(self):
        nodes = [
            {"id":"a","type":"volume.sma_multiple","params":{},"inputs":["b"]},
            {"id":"b","type":"condition.gte","params":{},"inputs":["a"]},
        ]
        errs = _validate_graph({"nodes": nodes})
        assert any("cycle" in e.lower() for e in errs)


# ── AgentLoopService.propose ──────────────────────────────────────────────────

class TestPropose:
    def test_propose_valid_mutation_creates_pending_backtest(self, svc, session, ivbs_manifest):
        mut = _valid_mutation()
        proposal = svc.propose(strategy_id="ivbs", mutation=mut, agent_run_id="run-001", session=session)
        session.commit()
        assert proposal.status == ProposalStatus.PENDING_BACKTEST.value
        assert proposal.strategy_id == "ivbs"
        assert proposal.agent_run_id == "run-001"
        assert proposal.parent_version == 1

    def test_propose_stores_mutated_graph(self, svc, session, ivbs_manifest):
        mut = _valid_mutation()
        proposal = svc.propose(strategy_id="ivbs", mutation=mut, agent_run_id="r1", session=session)
        session.commit()
        node_ids = [n["id"] for n in (proposal.proposed_graph or {}).get("nodes", [])]
        assert "n0" in node_ids  # original
        assert "n1" in node_ids  # added by mutation

    def test_propose_stores_mutation_summary(self, svc, session, ivbs_manifest):
        mut = _valid_mutation()
        proposal = svc.propose(strategy_id="ivbs", mutation=mut, agent_run_id="r1", session=session)
        assert proposal.mutation_summary == mut.reason

    def test_propose_nonexistent_strategy_raises(self, svc, session):
        mut = _valid_mutation()
        with pytest.raises(ValueError, match="not found"):
            svc.propose(strategy_id="unknown_strat", mutation=mut, agent_run_id="r1", session=session)

    def test_propose_generates_unique_proposal_ids(self, svc, session, ivbs_manifest):
        ids = set()
        for i in range(3):
            mut = _valid_mutation(nodes_add=[{"id":f"nu{i}","type":"condition.gte","params":{},"inputs":["n0"]}])
            p = svc.propose(strategy_id="ivbs", mutation=mut, agent_run_id="r1", session=session)
            session.commit()
            ids.add(p.proposal_id)
        assert len(ids) == 3


# ── AgentLoopService.run_backtest ─────────────────────────────────────────────

class TestRunBacktest:
    def _make_proposal(self, svc, session, _manifest):
        mut = _valid_mutation()
        p = svc.propose(strategy_id="ivbs", mutation=mut, agent_run_id="r1", session=session)
        session.commit()
        return p

    def test_backtest_transitions_to_backtest_done(self, svc, session, ivbs_manifest):
        p = self._make_proposal(svc, session, ivbs_manifest)
        svc.run_backtest(proposal_id=p.proposal_id, session=session)
        session.commit()
        updated = session.get(AgentProposal, p.proposal_id)
        assert updated.status == ProposalStatus.BACKTEST_DONE.value

    def test_backtest_stores_metrics(self, svc, session, ivbs_manifest):
        p = self._make_proposal(svc, session, ivbs_manifest)
        metrics = svc.run_backtest(proposal_id=p.proposal_id, session=session)
        assert "win_rate_pct" in metrics
        assert "sharpe_ratio" in metrics
        assert "max_drawdown_pct" in metrics

    def test_backtest_wrong_state_raises(self, svc, session, ivbs_manifest):
        p = self._make_proposal(svc, session, ivbs_manifest)
        svc.run_backtest(proposal_id=p.proposal_id, session=session)
        session.commit()
        # Running again from backtest_done should raise
        with pytest.raises(ValueError, match="PENDING_BACKTEST"):
            svc.run_backtest(proposal_id=p.proposal_id, session=session)

    def test_backtest_deterministic_for_same_graph(self, svc, session, ivbs_manifest):
        """Same graph → same metrics (hash-seeded)."""
        p1 = self._make_proposal(svc, session, ivbs_manifest)
        m1 = svc.run_backtest(proposal_id=p1.proposal_id, session=session)
        session.commit()
        # Create a second proposal with identical mutation
        mut2 = _valid_mutation()
        p2 = svc.propose(strategy_id="ivbs", mutation=mut2, agent_run_id="r2", session=session)
        session.commit()
        m2 = svc.run_backtest(proposal_id=p2.proposal_id, session=session)
        assert m1["win_rate_pct"] == m2["win_rate_pct"]
        assert m1["sharpe_ratio"] == m2["sharpe_ratio"]


# ── AgentLoopService.approve ──────────────────────────────────────────────────

class TestApprove:
    def _bt_done_proposal(self, svc, session, _manifest):
        mut = _valid_mutation()
        p = svc.propose(strategy_id="ivbs", mutation=mut, agent_run_id="r1", session=session)
        session.commit()
        svc.run_backtest(proposal_id=p.proposal_id, session=session)
        session.commit()
        return p

    def test_approve_transitions_to_pending_paper(self, svc, session, ivbs_manifest):
        p = self._bt_done_proposal(svc, session, ivbs_manifest)
        svc.approve(proposal_id=p.proposal_id, approved_by="human", session=session)
        session.commit()
        updated = session.get(AgentProposal, p.proposal_id)
        assert updated.status == ProposalStatus.PENDING_PAPER.value
        assert updated.approved_by == "human"

    def test_approve_pending_backtest_raises(self, svc, session, ivbs_manifest):
        mut = _valid_mutation()
        p = svc.propose(strategy_id="ivbs", mutation=mut, agent_run_id="r1", session=session)
        session.commit()
        with pytest.raises(ValueError, match="BACKTEST_DONE"):
            svc.approve(proposal_id=p.proposal_id, approved_by="human", session=session)


# ── AgentLoopService.reject ────────────────────────────────────────────────────

class TestReject:
    def test_reject_pending_backtest(self, svc, session, ivbs_manifest):
        mut = _valid_mutation()
        p = svc.propose(strategy_id="ivbs", mutation=mut, agent_run_id="r1", session=session)
        session.commit()
        svc.reject(proposal_id=p.proposal_id, reason="Does not meet criteria", session=session)
        session.commit()
        updated = session.get(AgentProposal, p.proposal_id)
        assert updated.status == ProposalStatus.REJECTED.value
        assert "criteria" in updated.rejection_reason

    def test_reject_already_rejected_raises(self, svc, session, ivbs_manifest):
        mut = _valid_mutation()
        p = svc.propose(strategy_id="ivbs", mutation=mut, agent_run_id="r1", session=session)
        session.commit()
        svc.reject(proposal_id=p.proposal_id, reason="First rejection", session=session)
        session.commit()
        with pytest.raises(ValueError, match="terminal"):
            svc.reject(proposal_id=p.proposal_id, reason="Second rejection", session=session)


# ── Capital guard in promote_to_live ─────────────────────────────────────────

class TestCapitalGuardInPromote:
    def _approved_paper_proposal(self, svc, session, manifest):
        mut = _valid_mutation()
        p = svc.propose(strategy_id="ivbs", mutation=mut, agent_run_id="r1", session=session)
        session.commit()
        svc.run_backtest(proposal_id=p.proposal_id, session=session)
        session.commit()
        svc.approve(proposal_id=p.proposal_id, approved_by="human", session=session)
        session.commit()
        svc.promote_to_paper(proposal_id=p.proposal_id, session=session)
        session.commit()
        return p

    def test_promote_to_live_does_not_touch_capital(self, svc, session, ivbs_manifest):
        original_capital = dict(ivbs_manifest.capital)
        p = self._approved_paper_proposal(svc, session, ivbs_manifest)
        svc.promote_to_live(proposal_id=p.proposal_id, approved_by="human", session=session)
        session.commit()
        session.refresh(ivbs_manifest)
        assert ivbs_manifest.capital == original_capital, "Capital must not be modified by agent"

    def test_promote_to_live_does_not_touch_risk(self, svc, session, ivbs_manifest):
        original_risk = dict(ivbs_manifest.risk)
        p = self._approved_paper_proposal(svc, session, ivbs_manifest)
        svc.promote_to_live(proposal_id=p.proposal_id, approved_by="human", session=session)
        session.commit()
        session.refresh(ivbs_manifest)
        assert ivbs_manifest.risk == original_risk, "Risk block must not be modified by agent"

    def test_promote_to_live_increments_version(self, svc, session, ivbs_manifest):
        p = self._approved_paper_proposal(svc, session, ivbs_manifest)
        svc.promote_to_live(proposal_id=p.proposal_id, approved_by="human", session=session)
        session.commit()
        session.refresh(ivbs_manifest)
        assert ivbs_manifest.version == 2

    def test_promote_to_live_appends_lineage(self, svc, session, ivbs_manifest):
        p = self._approved_paper_proposal(svc, session, ivbs_manifest)
        svc.promote_to_live(proposal_id=p.proposal_id, approved_by="human", session=session)
        session.commit()
        session.refresh(ivbs_manifest)
        lineage = ivbs_manifest.agent_lineage or []
        assert len(lineage) == 1
        assert lineage[0]["proposal_id"] == p.proposal_id

    def test_promote_paper_done_wrong_state_raises(self, svc, session, ivbs_manifest):
        mut = _valid_mutation()
        p = svc.propose(strategy_id="ivbs", mutation=mut, agent_run_id="r1", session=session)
        session.commit()
        with pytest.raises(ValueError, match="PAPER_DONE"):
            svc.promote_to_live(proposal_id=p.proposal_id, approved_by="human", session=session)
