"""Fix daily_pnl: composite unique (trade_date, strategy_id) instead of trade_date alone.

Revision ID: 005
Revises: 004
Create Date: 2026-07-18

Problem: daily_pnl.trade_date had unique=True which means only ONE strategy can write
a P&L record per day. With multiple strategies running concurrently, the second
write_daily_pnl() call on the same calendar date raises:
    UNIQUE constraint failed: daily_pnl.trade_date

Fix: drop the old single-column unique constraint and replace with a composite
unique constraint on (trade_date, strategy_id) so each strategy gets one row per day.

SQLite does not support ALTER CONSTRAINT, so we use batch_alter_table (which rebuilds
the table) to drop and recreate with the new constraint.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite batch mode rebuilds the table — this drops unique=True on trade_date
    # and replaces it with a composite unique on (trade_date, strategy_id).
    with op.batch_alter_table("daily_pnl", recreate="always") as batch_op:
        # Drop the old single-column unique index (SQLite may name it ix_daily_pnl_trade_date
        # or sqlite_autoindex_daily_pnl_1 depending on how the column was created).
        # batch_alter_table with recreate="always" rebuilds the table from scratch
        # using the current ORM model, so we just need to declare the new constraint.
        batch_op.create_unique_constraint(
            "uq_daily_pnl_date_strategy", ["trade_date", "strategy_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("daily_pnl", recreate="always") as batch_op:
        batch_op.drop_constraint("uq_daily_pnl_date_strategy", type_="unique")
        # Restore original single-column unique
        batch_op.create_unique_constraint(None, ["trade_date"])
