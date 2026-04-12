"""
app/models/db/order_event.py — order_events table: full audit trail of every order event.
"""

from __future__ import annotations

import datetime

from sqlalchemy import DateTime, Float, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db.base import Base


class OrderEvent(Base):
    __tablename__ = "order_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(Text, nullable=False)
    trade_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)

    # Event metadata
    event_type: Mapped[str] = mapped_column(Text, nullable=False)  # PLACED|FILLED|REJECTED|CANCELLED|MODIFIED
    status: Mapped[str | None] = mapped_column(Text, nullable=True)  # Raw Kite order status

    # Price/qty snapshot
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    trigger_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    filled_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    average_price: Mapped[float | None] = mapped_column(Float, nullable=True)

    status_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[str | None] = mapped_column(Text, nullable=True)  # Full JSON

    event_time: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default="(datetime('now'))", nullable=False
    )

    __table_args__ = (Index("idx_order_events_order_id", "order_id"),)
