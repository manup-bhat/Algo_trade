"""
app/models/db/daily_pnl.py — daily_pnl table: end-of-day summary per trading session.
"""

from __future__ import annotations

import datetime

from sqlalchemy import Date, DateTime, Float, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db.base import Base


class DailyPnl(Base):
    __tablename__ = "daily_pnl"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, unique=True)
    total_capital: Mapped[float] = mapped_column(Float, nullable=False)

    # Session stats
    signals_fired: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    setups_abandoned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    trades_taken: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    winning_trades: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    losing_trades: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    breakeven_trades: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # P&L
    gross_pnl: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_charges: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    net_pnl: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    max_drawdown: Mapped[float | None] = mapped_column(Float, nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default="(datetime('now'))", nullable=False
    )
