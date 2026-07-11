"""Add target_1r3 column to trades table.

Revision ID: 003
Revises: 002
Create Date: 2026-05-27

Adds a nullable REAL column `target_1r3` to the trades table to persist the
1:3 risk-reward target used by the profit-lock trailing SL logic.
Previously this value was computed in-memory by the state machine but never
written to SQLite, causing the trail to be lost on engine restart.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("trades") as batch_op:
        batch_op.add_column(
            sa.Column("target_1r3", sa.Float, nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("trades") as batch_op:
        batch_op.drop_column("target_1r3")
