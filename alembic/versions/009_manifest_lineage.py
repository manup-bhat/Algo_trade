"""Add graph and agent_lineage columns to strategy_manifests.

Revision ID: 009
Revises: 008
Create Date: 2026-09-12

Changes:
  1. Add `graph` column to `strategy_manifests` — holds the current active
     StrategyIR JSON (nodes + edges).  Populated by the Phase 3 Builder and
     updated by approved agent proposals (Phase 4).
  2. Add `agent_lineage` column to `strategy_manifests` — append-only JSON
     list of agent-produced version-change entries, each with:
       {proposal_id, agent_run_id, version, timestamp, summary}
     Enables full traceability of every agentic mutation (Part 3 §2 gap).

Both columns are nullable — existing rows (seeded by 007) are not affected
until the Builder or AgentLoopService writes to them.

Downgrade: drops both columns.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("strategy_manifests") as batch_op:
        batch_op.add_column(
            sa.Column(
                "graph",
                sa.JSON(),
                nullable=True,
                comment=(
                    "Current active StrategyIR: {nodes: [...], edges: [...]}. "
                    "Populated by Phase 3 Builder; mutated only via AgentLoopService."
                ),
            )
        )
        batch_op.add_column(
            sa.Column(
                "agent_lineage",
                sa.JSON(),
                nullable=True,
                comment=(
                    "Append-only list: [{proposal_id, agent_run_id, version, "
                    "timestamp, summary}] — one entry per agent-produced version."
                ),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("strategy_manifests") as batch_op:
        batch_op.drop_column("agent_lineage")
        batch_op.drop_column("graph")
