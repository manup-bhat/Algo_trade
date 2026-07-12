"""
app/models/db/strategy.py — strategies table: one row per registered strategy plugin.

Holds strategy metadata for the multi-strategy platform (used by the dashboard to
list strategies, toggle them, and show per-strategy config). Event tables
(signals/trades/order_events/daily_pnl) carry a `strategy_id` foreign-ish key that
references Strategy.id (kept as a plain Text column — no hard FK — so a strategy
row is optional and can be seeded lazily).
"""

from __future__ import annotations

import datetime

from sqlalchemy import Boolean, DateTime, JSON, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db.base import Base


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # e.g. "ivbs", "opt_momentum"
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # EQUITY | FUTURE | OPTION | MIXED
    asset_class: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'EQUITY'"), default="EQUITY"
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("1"), default=True
    )
    # Snapshot of the strategy's config (mirrors engine/strategies/<id>/config.yaml).
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default="(datetime('now'))", nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default="(datetime('now'))", nullable=False
    )
