"""
app/models/db/signal_snapshot.py — signal_snapshots table for event sourcing.
"""

from __future__ import annotations

import datetime

from sqlalchemy import DateTime, Integer, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import Index

from app.models.db.base import Base

class SignalSnapshot(Base):
    __tablename__ = "signal_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    signal_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_time: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    context_data: Mapped[dict] = mapped_column(JSON, nullable=False)

    from sqlalchemy.sql import func
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_signal_snapshots_symbol", "symbol"),
        Index("idx_signal_snapshots_time", "snapshot_time"),
        Index("idx_signal_snapshots_signal_id", "signal_id"),
    )
