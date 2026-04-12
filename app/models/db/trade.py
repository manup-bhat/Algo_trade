"""
app/models/db/trade.py — trades table + TradeStatus enum.
"""

from __future__ import annotations

import datetime
import enum

from sqlalchemy import DateTime, Float, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db.base import Base


class TradeStatus(str, enum.Enum):
    OPEN = "OPEN"
    CLOSED_TARGET = "CLOSED_TARGET"       # Hit 1:4 target
    CLOSED_STOPLOSS = "CLOSED_STOPLOSS"   # SL triggered, no trailing
    CLOSED_TRAILSTOP = "CLOSED_TRAILSTOP" # SL triggered after trailing
    CLOSED_TIME = "CLOSED_TIME"           # 3:20 PM squareoff
    CLOSED_MANUAL = "CLOSED_MANUAL"       # Operator emergency stop
    CLOSED_BROKER = "CLOSED_BROKER"       # Broker auto-squareoff
    CLOSED_ERROR = "CLOSED_ERROR"         # SL placement failed, emergency exit
    # Paper mode statuses carry the same names with PAPER_ prefix in notes field


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    signal_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    instrument_token: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_order_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    entry_time: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    # Stop loss levels
    initial_stop_loss: Mapped[float] = mapped_column(Float, nullable=False)
    current_stop_loss: Mapped[float] = mapped_column(Float, nullable=False)
    risk_per_share: Mapped[float] = mapped_column(Float, nullable=False)
    risk_amount: Mapped[float] = mapped_column(Float, nullable=False)

    # Targets
    target_1r2: Mapped[float] = mapped_column(Float, nullable=False)
    target_1r4: Mapped[float] = mapped_column(Float, nullable=False)

    # Order tracking
    sl_order_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    exit_order_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Exit data
    exit_time: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    gross_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    brokerage: Mapped[float | None] = mapped_column(Float, nullable=True)
    stt: Mapped[float | None] = mapped_column(Float, nullable=True)
    other_charges: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Status
    status: Mapped[str] = mapped_column(Text, nullable=False, default=TradeStatus.OPEN.value)

    # Trailing flags
    cost_trailed: Mapped[int] = mapped_column(Integer, default=0)
    profit_locked: Mapped[int] = mapped_column(Integer, default=0)

    # Analytics
    max_adverse_excursion: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_favorable_excursion: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default="(datetime('now'))", nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default="(datetime('now'))", nullable=False
    )

    __table_args__ = (
        Index("idx_trades_symbol", "symbol"),
        Index("idx_trades_status", "status"),
        Index("idx_trades_entry_time", "entry_time"),
    )
