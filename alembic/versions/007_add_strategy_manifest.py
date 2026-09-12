"""Add strategy_manifest table and order_group_id to order_events.

Revision ID: 007
Revises: 005
Create Date: 2026-09-09

Changes:
  1. Create `strategy_manifests` table — stores the engine data-contract
     (requirements, capital, risk, ui) per strategy as a DB row.
  2. Add `order_group_id` column to `order_events` — enables multi-leg order
     tracking in the blotter (Phase 1: OrderGroup).

Seeded with initial manifests for ivbs and options_momentum derived from
their existing config.yaml tunables.

Downgrade: drops strategy_manifests, removes order_group_id from order_events.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. strategy_manifests table ───────────────────────────────────────────
    op.create_table(
        "strategy_manifests",
        sa.Column("strategy_id", sa.Text(), primary_key=True),
        sa.Column("requirements", sa.JSON(), nullable=True),
        sa.Column("capital", sa.JSON(), nullable=True),
        sa.Column("risk", sa.JSON(), nullable=True),
        sa.Column("ui", sa.JSON(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
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

    # ── Seed initial manifests from known strategies ──────────────────────────
    # These values match the current config.yaml tunables for both strategies.
    # Operators can update them via the DB or the dashboard without touching code.
    op.execute("""
        INSERT INTO strategy_manifests (strategy_id, requirements, capital, risk, ui, version)
        VALUES (
            'ivbs',
            '{"instruments": {"mode": "watchlist", "tick_mode": "quote"}, "candle_intervals": ["1min"], "tick_mode": "quote", "capabilities": ["volume_sma"]}',
            '{"allocated": 200000, "currency": "INR"}',
            '{"max_concurrent": 3, "circuit_breaker_pct": 2.0}',
            '{"panels": [{"type": "scanner_table", "endpoint": "/api/strategies/ivbs/scan"}]}',
            1
        )
    """)

    op.execute("""
        INSERT INTO strategy_manifests (strategy_id, requirements, capital, risk, ui, version)
        VALUES (
            'options_momentum',
            '{"instruments": {"mode": "option_chain", "underlying": "NIFTY", "expiry": "nearest_weekly", "strike_range_pct": 5}, "candle_intervals": ["1min"], "tick_mode": "full", "capabilities": ["option_chain", "greeks"]}',
            '{"allocated": 150000, "currency": "INR"}',
            '{"max_concurrent": 2, "circuit_breaker_pct": 3.0}',
            '{"panels": [{"type": "option_chain", "endpoint": "/api/strategies/options_momentum/chain"}]}',
            1
        )
    """)

    # ── 2. order_group_id on order_events ─────────────────────────────────────
    # Nullable — existing single-leg orders have no group; only multi-leg orders
    # (OrderGroup) populate this field.
    with op.batch_alter_table("order_events") as batch_op:
        batch_op.add_column(
            sa.Column("order_group_id", sa.Text(), nullable=True)
        )
        batch_op.create_index("idx_order_events_group", ["order_group_id"])


def downgrade() -> None:
    with op.batch_alter_table("order_events") as batch_op:
        batch_op.drop_index("idx_order_events_group")
        batch_op.drop_column("order_group_id")

    op.drop_table("strategy_manifests")
