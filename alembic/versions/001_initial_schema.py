"""Initial schema — all 4 tables.

Revision ID: 001
Revises: 
Create Date: 2026-04-12
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── signals ──────────────────────────────────────────────────────
    op.create_table(
        "signals",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.Text, nullable=False),
        sa.Column("instrument_token", sa.Integer, nullable=False),
        sa.Column("signal_time", sa.DateTime, nullable=False),
        sa.Column("impact_candle_open", sa.Float, nullable=False),
        sa.Column("impact_candle_high", sa.Float, nullable=False),
        sa.Column("impact_candle_low", sa.Float, nullable=False),
        sa.Column("impact_candle_close", sa.Float, nullable=False),
        sa.Column("impact_candle_volume", sa.Integer, nullable=False),
        sa.Column("impact_candle_turnover", sa.Float, nullable=False),
        sa.Column("volume_sma_500", sa.Float, nullable=False),
        sa.Column("volume_spike_multiple", sa.Float, nullable=False),
        sa.Column("progressed_to_monitor", sa.Integer, server_default="0"),
        sa.Column("progressed_to_action", sa.Integer, server_default="0"),
        sa.Column("resulted_in_trade", sa.Integer, server_default="0"),
        sa.Column("abandonment_reason", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("(datetime('now'))")),
    )
    op.create_index("idx_signals_symbol", "signals", ["symbol"])
    op.create_index("idx_signals_time", "signals", ["signal_time"])

    # ── trades ───────────────────────────────────────────────────────
    op.create_table(
        "trades",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("signal_id", sa.Integer, nullable=True),
        sa.Column("symbol", sa.Text, nullable=False),
        sa.Column("instrument_token", sa.Integer, nullable=False),
        sa.Column("entry_order_id", sa.Text, nullable=False, unique=True),
        sa.Column("entry_time", sa.DateTime, nullable=False),
        sa.Column("entry_price", sa.Float, nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("initial_stop_loss", sa.Float, nullable=False),
        sa.Column("current_stop_loss", sa.Float, nullable=False),
        sa.Column("risk_per_share", sa.Float, nullable=False),
        sa.Column("risk_amount", sa.Float, nullable=False),
        sa.Column("target_1r2", sa.Float, nullable=False),
        sa.Column("target_1r4", sa.Float, nullable=False),
        sa.Column("sl_order_id", sa.Text, nullable=True),
        sa.Column("exit_order_id", sa.Text, nullable=True),
        sa.Column("exit_time", sa.DateTime, nullable=True),
        sa.Column("exit_price", sa.Float, nullable=True),
        sa.Column("gross_pnl", sa.Float, nullable=True),
        sa.Column("brokerage", sa.Float, nullable=True),
        sa.Column("stt", sa.Float, nullable=True),
        sa.Column("other_charges", sa.Float, nullable=True),
        sa.Column("net_pnl", sa.Float, nullable=True),
        sa.Column("status", sa.Text, nullable=False, server_default="OPEN"),
        sa.Column("cost_trailed", sa.Integer, server_default="0"),
        sa.Column("profit_locked", sa.Integer, server_default="0"),
        sa.Column("max_adverse_excursion", sa.Float, nullable=True),
        sa.Column("max_favorable_excursion", sa.Float, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("(datetime('now'))")),
        sa.Column("updated_at", sa.DateTime, server_default=sa.text("(datetime('now'))")),
    )
    op.create_index("idx_trades_symbol", "trades", ["symbol"])
    op.create_index("idx_trades_status", "trades", ["status"])
    op.create_index("idx_trades_entry_time", "trades", ["entry_time"])

    # ── order_events ─────────────────────────────────────────────────
    op.create_table(
        "order_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.Text, nullable=False),
        sa.Column("trade_id", sa.Integer, nullable=True),
        sa.Column("symbol", sa.Text, nullable=False),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=True),
        sa.Column("price", sa.Float, nullable=True),
        sa.Column("trigger_price", sa.Float, nullable=True),
        sa.Column("quantity", sa.Integer, nullable=True),
        sa.Column("filled_quantity", sa.Integer, nullable=True),
        sa.Column("average_price", sa.Float, nullable=True),
        sa.Column("status_message", sa.Text, nullable=True),
        sa.Column("raw_payload", sa.Text, nullable=True),
        sa.Column("event_time", sa.DateTime, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("(datetime('now'))")),
    )
    op.create_index("idx_order_events_order_id", "order_events", ["order_id"])

    # ── daily_pnl ────────────────────────────────────────────────────
    op.create_table(
        "daily_pnl",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("trade_date", sa.Date, nullable=False, unique=True),
        sa.Column("total_capital", sa.Float, nullable=False),
        sa.Column("signals_fired", sa.Integer, server_default="0", nullable=False),
        sa.Column("setups_abandoned", sa.Integer, server_default="0", nullable=False),
        sa.Column("trades_taken", sa.Integer, server_default="0", nullable=False),
        sa.Column("winning_trades", sa.Integer, server_default="0", nullable=False),
        sa.Column("losing_trades", sa.Integer, server_default="0", nullable=False),
        sa.Column("breakeven_trades", sa.Integer, server_default="0", nullable=False),
        sa.Column("gross_pnl", sa.Float, server_default="0", nullable=False),
        sa.Column("total_charges", sa.Float, server_default="0", nullable=False),
        sa.Column("net_pnl", sa.Float, server_default="0", nullable=False),
        sa.Column("max_drawdown", sa.Float, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("(datetime('now'))")),
    )


def downgrade() -> None:
    op.drop_table("daily_pnl")
    op.drop_index("idx_order_events_order_id", "order_events")
    op.drop_table("order_events")
    op.drop_index("idx_trades_entry_time", "trades")
    op.drop_index("idx_trades_status", "trades")
    op.drop_index("idx_trades_symbol", "trades")
    op.drop_table("trades")
    op.drop_index("idx_signals_time", "signals")
    op.drop_index("idx_signals_symbol", "signals")
    op.drop_table("signals")
