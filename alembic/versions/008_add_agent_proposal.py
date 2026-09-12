"""Add agent_proposals table.

Revision ID: 008
Revises: 007
Create Date: 2026-09-12

Changes:
  1. Create `agent_proposals` table — tracks every StrategyIR mutation proposed
     by the agentic loop (Phase 4). Stores lifecycle status, backtest/paper
     metrics, lineage (agent_run_id), and human-approval fields.

Architecture notes:
  - `proposed_graph` contains ONLY StrategyIR nodes/edges — no capital/risk
    overrides. The CapitalAllocatorRule (Phase 2) remains human-set only.
  - Two human approval gates are encoded structurally in the status enum:
    backtest_done → (human) → pending_paper → paper_done → (human) → approved.
  - Every proposal links to a parent_version of strategy_manifests.version,
    enabling full mutation lineage (Part 3 §2 gap closure).

Downgrade: drops agent_proposals table.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_proposals",
        # ── Identity ────────────────────────────────────────────────────────
        sa.Column("proposal_id", sa.Text(), primary_key=True),

        # ── Foreign reference ────────────────────────────────────────────────
        sa.Column("strategy_id", sa.Text(), nullable=False),
        sa.Column(
            "parent_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),

        # ── Mutation payload ─────────────────────────────────────────────────
        sa.Column("proposed_graph", sa.JSON(), nullable=True),
        sa.Column("mutation_summary", sa.Text(), nullable=True),

        # ── Lineage ──────────────────────────────────────────────────────────
        sa.Column("agent_run_id", sa.Text(), nullable=True),

        # ── Lifecycle ────────────────────────────────────────────────────────
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'pending_backtest'"),
        ),

        # ── Results ──────────────────────────────────────────────────────────
        sa.Column("backtest_metrics", sa.JSON(), nullable=True),
        sa.Column("paper_metrics", sa.JSON(), nullable=True),

        # ── Human approval ───────────────────────────────────────────────────
        sa.Column("approved_by", sa.Text(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),

        # ── Timestamps ───────────────────────────────────────────────────────
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(datetime('now'))"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(datetime('now'))"),
            nullable=False,
        ),
    )

    # Index for common queries: by strategy and by status, and by agent_run_id
    op.create_index("idx_agent_proposals_strategy", "agent_proposals", ["strategy_id"])
    op.create_index("idx_agent_proposals_status", "agent_proposals", ["status"])
    op.create_index("idx_agent_proposals_run", "agent_proposals", ["agent_run_id"])


def downgrade() -> None:
    op.drop_index("idx_agent_proposals_run", "agent_proposals")
    op.drop_index("idx_agent_proposals_status", "agent_proposals")
    op.drop_index("idx_agent_proposals_strategy", "agent_proposals")
    op.drop_table("agent_proposals")
