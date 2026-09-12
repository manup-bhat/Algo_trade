"""
app/api/agent_router.py — Agentic Strategy Loop API (Phase 4).

Exposes the human-facing REST interface for proposing, reviewing, approving,
and promoting AI-generated StrategyIR mutations.

Endpoints:
    POST /api/v1/agent/propose                      — Submit an AgentIRMutation
    POST /api/v1/agent/{proposal_id}/backtest       — Run backtest on proposal
    GET  /api/v1/agent/proposals                    — List proposals (filterable)
    GET  /api/v1/agent/proposals/{proposal_id}      — Proposal detail
    POST /api/v1/agent/{proposal_id}/approve        — Human approve → paper gate
    POST /api/v1/agent/{proposal_id}/reject         — Human reject with reason
    POST /api/v1/agent/{proposal_id}/promote-paper  — Move to paper trading
    POST /api/v1/agent/{proposal_id}/promote-live   — Move to live (approved)

Capital guard (Part 3 §Phase 4.1):
    AgentIRMutation has NO capital / risk.circuit_breaker_pct fields.
    FastAPI/Pydantic return HTTP 422 before any handler code runs if a caller
    tries to pass those fields — structural enforcement, not a runtime check.

Human approval gates:
    1. backtest_done → approve → pending_paper       (gate 1 — must call /approve)
    2. paper_done   → promote-live → approved         (gate 2 — must call /promote-live)
    The agent can never self-approve either gate.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.models.db.agent_proposal import ProposalStatus
from engine.agent.ir_mutation import AgentIRMutation

log = structlog.get_logger(__name__)
router = APIRouter()


# ── DB session factory ────────────────────────────────────────────────────────
# Module-level variable — can be replaced by tests without patching settings.
# Default implementation reads DATABASE_URL from env (or falls back to sqlite).

def _default_session_factory():
    """Create a SQLAlchemy sync session for the configured DB."""
    import os
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models.db.base import Base

    db_url = os.environ.get("DATABASE_URL", "sqlite:///./trading_bot.db")
    # Strip async prefix if mistakenly set
    if db_url.startswith("sqlite+aiosqlite"):
        db_url = db_url.replace("sqlite+aiosqlite", "sqlite")
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


# Reassign this in tests to inject a test DB session.
_session_factory = _default_session_factory


# ── Request / Response schemas ────────────────────────────────────────────────

class ProposeRequest(BaseModel):
    """Body for POST /agent/propose."""
    strategy_id: str = Field(..., min_length=1, description="Target strategy ID")
    mutation: AgentIRMutation = Field(..., description="The IR mutation to apply")
    agent_run_id: str = Field(
        default="manual",
        min_length=1,
        description="Caller-provided run identifier for lineage (e.g. 'run-001', 'llm-gpt4o-v3')",
    )


class ApproveRequest(BaseModel):
    """Body for POST /agent/{proposal_id}/approve."""
    approved_by: str = Field(
        default="human",
        min_length=1,
        description="Human approver identifier (username, email, or 'human')",
    )


class RejectRequest(BaseModel):
    """Body for POST /agent/{proposal_id}/reject."""
    reason: str = Field(
        ...,
        min_length=5,
        description="Mandatory rejection reason for audit trail",
    )


class PromoteLiveRequest(BaseModel):
    """Body for POST /agent/{proposal_id}/promote-live."""
    approved_by: str = Field(
        default="human",
        min_length=1,
        description="Human approver identifier confirming live promotion",
    )


class BacktestRequest(BaseModel):
    """Optional body for POST /agent/{proposal_id}/backtest."""
    lookback_days: int = Field(default=30, ge=5, le=252, description="Lookback window in trading days")


def _proposal_to_dict(proposal) -> dict[str, Any]:
    """Serialize an AgentProposal ORM row to a JSON-safe dict."""
    return {
        "proposal_id": proposal.proposal_id,
        "strategy_id": proposal.strategy_id,
        "parent_version": proposal.parent_version,
        "mutation_summary": proposal.mutation_summary,
        "agent_run_id": proposal.agent_run_id,
        "status": proposal.status,
        "backtest_metrics": proposal.backtest_metrics,
        "paper_metrics": proposal.paper_metrics,
        "approved_by": proposal.approved_by,
        "rejection_reason": proposal.rejection_reason,
        "node_count": len((proposal.proposed_graph or {}).get("nodes", [])),
        "created_at": proposal.created_at.isoformat() if proposal.created_at else None,
        "updated_at": proposal.updated_at.isoformat() if proposal.updated_at else None,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/propose", summary="Propose a StrategyIR mutation")
async def propose_mutation(body: ProposeRequest) -> dict[str, Any]:
    """
    Submit a StrategyIR mutation for a strategy.

    The agent (caller) provides:
    - Which strategy to mutate (strategy_id)
    - What to change (AgentIRMutation — nodes/edges only, no capital fields)
    - A run identifier for lineage tracing (agent_run_id)

    The service:
    1. Loads the current graph from the strategy manifest.
    2. Applies the mutation.
    3. Validates the resulting graph (DAG check, registered node types, etc.).
    4. Persists an AgentProposal in PENDING_BACKTEST state.

    Returns the created proposal with its proposal_id.

    Raises:
        422: If AgentIRMutation contains capital/risk fields or fails Pydantic validation.
        400: If the strategy doesn't exist or the mutated graph fails graph validation.
    """
    import asyncio
    from engine.agent.agent_loop import AgentLoopService

    def _sync_propose():
        svc = AgentLoopService()
        session = _session_factory()
        try:
            proposal = svc.propose(
                strategy_id=body.strategy_id,
                mutation=body.mutation,
                agent_run_id=body.agent_run_id,
                session=session,
            )
            session.commit()
            return _proposal_to_dict(proposal)
        except ValueError as exc:
            session.rollback()
            raise exc
        finally:
            session.close()

    try:
        result = await asyncio.to_thread(_sync_propose)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"message": str(exc)})

    log.info("agent_propose_ok", proposal_id=result["proposal_id"])
    return result


@router.post("/{proposal_id}/backtest", summary="Run backtest on a proposal")
async def run_backtest(proposal_id: str, body: BacktestRequest = BacktestRequest()) -> dict[str, Any]:
    """
    Run a deterministic synthetic backtest on the proposal's graph.

    Transitions the proposal from PENDING_BACKTEST → BACKTEST_DONE and
    stores metrics (win rate, Sharpe, max drawdown, etc.) on the row.

    Raises:
        404: If proposal_id not found.
        400: If proposal is not in PENDING_BACKTEST state.
    """
    import asyncio
    from engine.agent.agent_loop import AgentLoopService

    def _sync_backtest():
        svc = AgentLoopService()
        session = _session_factory()
        try:
            metrics = svc.run_backtest(
                proposal_id=proposal_id,
                session=session,
                lookback_days=body.lookback_days,
            )
            session.commit()
            return metrics
        except ValueError as exc:
            session.rollback()
            raise exc
        finally:
            session.close()

    try:
        metrics = await asyncio.to_thread(_sync_backtest)
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail={"message": msg})
        raise HTTPException(status_code=400, detail={"message": msg})

    return {"proposal_id": proposal_id, "status": "backtest_done", "metrics": metrics}


@router.get("/proposals", summary="List agent proposals")
async def list_proposals(
    strategy_id: str | None = Query(None, description="Filter by strategy ID"),
    status: str | None = Query(None, description="Filter by status (e.g. pending_backtest)"),
    agent_run_id: str | None = Query(None, description="Filter by agent run ID"),
    limit: int = Query(50, ge=1, le=200, description="Maximum rows to return"),
) -> dict[str, Any]:
    """List agent proposals with optional filters."""
    import asyncio

    def _sync_list():
        from sqlalchemy import select
        from app.models.db.agent_proposal import AgentProposal
        session = _session_factory()
        try:
            q = select(AgentProposal).order_by(AgentProposal.created_at.desc()).limit(limit)
            if strategy_id:
                q = q.where(AgentProposal.strategy_id == strategy_id)
            if status:
                q = q.where(AgentProposal.status == status)
            if agent_run_id:
                q = q.where(AgentProposal.agent_run_id == agent_run_id)
            rows = session.execute(q).scalars().all()
            return [_proposal_to_dict(r) for r in rows]
        finally:
            session.close()

    rows = await asyncio.to_thread(_sync_list)
    return {
        "proposals": rows,
        "count": len(rows),
        "filters": {"strategy_id": strategy_id, "status": status, "agent_run_id": agent_run_id},
    }


@router.get("/proposals/{proposal_id}", summary="Get proposal detail")
async def get_proposal(proposal_id: str) -> dict[str, Any]:
    """Return full detail for a single proposal including proposed_graph."""
    import asyncio

    def _sync_get():
        from sqlalchemy import select
        from app.models.db.agent_proposal import AgentProposal
        session = _session_factory()
        try:
            row = session.execute(
                select(AgentProposal).where(AgentProposal.proposal_id == proposal_id)
            ).scalar_one_or_none()
            if row is None:
                return None
            d = _proposal_to_dict(row)
            d["proposed_graph"] = row.proposed_graph
            return d
        finally:
            session.close()

    result = await asyncio.to_thread(_sync_get)
    if result is None:
        raise HTTPException(status_code=404, detail={"message": f"Proposal {proposal_id!r} not found"})
    return result


@router.post("/{proposal_id}/approve", summary="Human approves proposal for paper trading")
async def approve_proposal(proposal_id: str, body: ApproveRequest = ApproveRequest()) -> dict[str, Any]:
    """Human gate 1: approve a backtest_done proposal for paper trading."""
    import asyncio
    from engine.agent.agent_loop import AgentLoopService

    def _sync_approve():
        svc = AgentLoopService()
        session = _session_factory()
        try:
            proposal = svc.approve(proposal_id=proposal_id, approved_by=body.approved_by, session=session)
            session.commit()
            return _proposal_to_dict(proposal)
        except ValueError as exc:
            session.rollback()
            raise exc
        finally:
            session.close()

    try:
        result = await asyncio.to_thread(_sync_approve)
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail={"message": msg})
        raise HTTPException(status_code=400, detail={"message": msg})
    return result


@router.post("/{proposal_id}/reject", summary="Human rejects proposal")
async def reject_proposal(proposal_id: str, body: RejectRequest) -> dict[str, Any]:
    """Reject a proposal at any non-terminal stage. Requires mandatory reason."""
    import asyncio
    from engine.agent.agent_loop import AgentLoopService

    def _sync_reject():
        svc = AgentLoopService()
        session = _session_factory()
        try:
            proposal = svc.reject(proposal_id=proposal_id, reason=body.reason, session=session)
            session.commit()
            return _proposal_to_dict(proposal)
        except ValueError as exc:
            session.rollback()
            raise exc
        finally:
            session.close()

    try:
        result = await asyncio.to_thread(_sync_reject)
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail={"message": msg})
        raise HTTPException(status_code=400, detail={"message": msg})
    return result


@router.post("/{proposal_id}/promote-paper", summary="Start paper trading for approved proposal")
async def promote_paper(proposal_id: str) -> dict[str, Any]:
    """Move a PENDING_PAPER proposal into paper trading (PAPER_DONE)."""
    import asyncio
    from engine.agent.agent_loop import AgentLoopService

    def _sync_promote():
        svc = AgentLoopService()
        session = _session_factory()
        try:
            proposal = svc.promote_to_paper(proposal_id=proposal_id, session=session)
            session.commit()
            return _proposal_to_dict(proposal)
        except ValueError as exc:
            session.rollback()
            raise exc
        finally:
            session.close()

    try:
        result = await asyncio.to_thread(_sync_promote)
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail={"message": msg})
        raise HTTPException(status_code=400, detail={"message": msg})
    return result


@router.post("/{proposal_id}/promote-live", summary="Promote paper-done proposal to live")
async def promote_live(proposal_id: str, body: PromoteLiveRequest = PromoteLiveRequest()) -> dict[str, Any]:
    """Human gate 2: promote a PAPER_DONE proposal to live by patching the manifest."""
    import asyncio
    from engine.agent.agent_loop import AgentLoopService

    def _sync_live():
        svc = AgentLoopService()
        session = _session_factory()
        try:
            proposal = svc.promote_to_live(
                proposal_id=proposal_id,
                approved_by=body.approved_by,
                session=session,
            )
            session.commit()
            return _proposal_to_dict(proposal)
        except ValueError as exc:
            session.rollback()
            raise exc
        finally:
            session.close()

    try:
        result = await asyncio.to_thread(_sync_live)
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail={"message": msg})
        raise HTTPException(status_code=400, detail={"message": msg})

    log.info("agent_promote_live_ok", proposal_id=proposal_id, approved_by=body.approved_by)
    return result


# ── Proposal status summary ───────────────────────────────────────────────────

@router.get("/status-summary", summary="Count proposals by status")
async def status_summary(
    strategy_id: str | None = Query(None, description="Filter by strategy ID"),
) -> dict[str, Any]:
    """Return a count of proposals grouped by status (for dashboard badge counts)."""
    import asyncio

    def _sync_summary():
        from sqlalchemy import func, select
        from app.models.db.agent_proposal import AgentProposal
        session = _session_factory()
        try:
            q = select(AgentProposal.status, func.count().label("n")).group_by(AgentProposal.status)
            if strategy_id:
                q = q.where(AgentProposal.strategy_id == strategy_id)
            rows = session.execute(q).all()
            counts = {r.status: r.n for r in rows}
            for s in ProposalStatus:
                counts.setdefault(s.value, 0)
            return counts
        finally:
            session.close()

    counts = await asyncio.to_thread(_sync_summary)
    pending = counts.get("pending_backtest", 0) + counts.get("backtest_done", 0) + counts.get("pending_paper", 0) + counts.get("paper_done", 0)
    return {"by_status": counts, "pending_action": pending}
