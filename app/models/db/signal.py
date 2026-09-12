"""
app/models/db/signal.py — signals table: one row per Phase 1 scan hit.
"""

from __future__ import annotations

import datetime

from sqlalchemy import DateTime, Float, Index, Integer, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db.base import Base


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_id: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'ivbs'"), default="ivbs"
    )
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    instrument_token: Mapped[int] = mapped_column(Integer, nullable=False)
    signal_time: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)

    # Impact candle OHLCV
    impact_candle_open: Mapped[float] = mapped_column(Float, nullable=False)
    impact_candle_high: Mapped[float] = mapped_column(Float, nullable=False)
    impact_candle_low: Mapped[float] = mapped_column(Float, nullable=False)
    impact_candle_close: Mapped[float] = mapped_column(Float, nullable=False)
    impact_candle_volume: Mapped[int] = mapped_column(Integer, nullable=False)
    impact_candle_turnover: Mapped[float] = mapped_column(Float, nullable=False)

    # SMA context
    volume_sma_500: Mapped[float] = mapped_column(Float, nullable=False)
    volume_spike_multiple: Mapped[float] = mapped_column(Float, nullable=False)

    # Progression tracking
    progressed_to_monitor: Mapped[int] = mapped_column(Integer, default=0)
    progressed_to_action: Mapped[int] = mapped_column(Integer, default=0)
    resulted_in_trade: Mapped[int] = mapped_column(Integer, default=0)
    abandonment_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Trade mode: PAPER or LIVE — set when signal triggers an entry in any mode.
    # A signal that produces both paper and live trades gets BOTH modes recorded.
    trade_mode: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_signals_symbol", "symbol"),
        Index("idx_signals_time", "signal_time"),
        Index("idx_signals_strategy", "strategy_id"),
    )
