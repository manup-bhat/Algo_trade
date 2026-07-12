"""Add strategy_id to event tables + strategies metadata table.

Revision ID: 004
Revises: 03f052fed285
Create Date: 2026-07-11

Multi-strategy support: every event row (signal / trade / order_event / daily_pnl)
is tagged with the owning strategy_id (defaults to "ivbs" for all existing rows).
A new `strategies` table holds per-strategy metadata for the dashboard.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "03f052fed285"
branch_labels = None
depends_on = None

_STRATEGY_COL = lambda: sa.Column(  # noqa: E731
    "strategy_id", sa.Text(), nullable=False, server_default=sa.text("'ivbs'")
)


def upgrade() -> None:
    # ── strategy_id column on each event table (server_default backfills rows) ──
    with op.batch_alter_table("signals") as batch_op:
        batch_op.add_column(_STRATEGY_COL())
        batch_op.create_index("idx_signals_strategy", ["strategy_id"])

    with op.batch_alter_table("trades") as batch_op:
        batch_op.add_column(_STRATEGY_COL())
        batch_op.create_index("idx_trades_strategy", ["strategy_id"])

    with op.batch_alter_table("order_events") as batch_op:
        batch_op.add_column(_STRATEGY_COL())
        batch_op.create_index("idx_order_events_strategy", ["strategy_id"])

    with op.batch_alter_table("daily_pnl") as batch_op:
        batch_op.add_column(_STRATEGY_COL())

    # ── strategies metadata table ──────────────────────────────────────────
    op.create_table(
        "strategies",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("asset_class", sa.Text(), nullable=False, server_default=sa.text("'EQUITY'")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(datetime('now'))"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(datetime('now'))"), nullable=False),
    )

    # Seed the IVBS strategy row so existing tagged rows have a parent.
    op.execute(
        "INSERT INTO strategies (id, name, description, asset_class, enabled) "
        "VALUES ('ivbs', 'Institutional Volume Breakout Strategy', "
        "'First-wave volume spike + dry-up re-ignition (NSE equity intraday)', 'EQUITY', 1)"
    )


def downgrade() -> None:
    op.drop_table("strategies")
    with op.batch_alter_table("daily_pnl") as batch_op:
        batch_op.drop_column("strategy_id")
    with op.batch_alter_table("order_events") as batch_op:
        batch_op.drop_index("idx_order_events_strategy")
        batch_op.drop_column("strategy_id")
    with op.batch_alter_table("trades") as batch_op:
        batch_op.drop_index("idx_trades_strategy")
        batch_op.drop_column("strategy_id")
    with op.batch_alter_table("signals") as batch_op:
        batch_op.drop_index("idx_signals_strategy")
        batch_op.drop_column("strategy_id")
