"""
engine/store/db_writer.py — Async SQLite writes: signals, trades, events, daily_pnl.

All write operations are async-safe via aiosqlite + SQLAlchemy 2.0.
One DB write per business event — never in the tick hot-path.
"""

from __future__ import annotations

import datetime
import json
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db.daily_pnl import DailyPnl
from app.models.db.order_event import OrderEvent
from app.models.db.signal import Signal
from app.models.db.signal_snapshot import SignalSnapshot
from app.models.db.trade import Trade, TradeStatus
from app.store.database import get_db

log = structlog.get_logger(__name__)


class DbWriter:
    """
    All database write operations for the engine.
    Uses get_db() context manager — each write is its own transaction.
    """

    # ── Signals ────────────────────────────────────────────────────────────

    async def write_signal(
        self,
        symbol: str,
        instrument_token: int,
        signal_time: datetime.datetime,
        impact_open: float,
        impact_high: float,
        impact_low: float,
        impact_close: float,
        impact_volume: int,
        impact_turnover: float,
        volume_sma_500: float,
        volume_spike_multiple: float,
        trade_mode: str | None = None,
    ) -> int:
        """Write a scan hit signal. Returns the new signal ID."""
        async with get_db() as session:
            sig = Signal(
                symbol=symbol,
                instrument_token=instrument_token,
                signal_time=signal_time,
                impact_candle_open=impact_open,
                impact_candle_high=impact_high,
                impact_candle_low=impact_low,
                impact_candle_close=impact_close,
                impact_candle_volume=impact_volume,
                impact_candle_turnover=impact_turnover,
                volume_sma_500=volume_sma_500,
                volume_spike_multiple=volume_spike_multiple,
                trade_mode=trade_mode,
            )
            session.add(sig)
            await session.flush()  # Get the ID before commit
            signal_id = sig.id
        log.debug("signal_written", symbol=symbol, signal_id=signal_id)
        return signal_id  # type: ignore[return-value]

    async def update_signal_progression(
        self,
        signal_id: int,
        progressed_to_monitor: bool | None = None,
        progressed_to_action: bool | None = None,
        resulted_in_trade: bool | None = None,
        abandonment_reason: str | None = None,
    ) -> None:
        async with get_db() as session:
            sig = await session.get(Signal, signal_id)
            if sig is None:
                log.warning("signal_not_found_for_update", signal_id=signal_id)
                return
            if progressed_to_monitor is not None:
                sig.progressed_to_monitor = int(progressed_to_monitor)
            if progressed_to_action is not None:
                sig.progressed_to_action = int(progressed_to_action)
            if resulted_in_trade is not None:
                sig.resulted_in_trade = int(resulted_in_trade)
            if abandonment_reason is not None:
                sig.abandonment_reason = abandonment_reason
            await session.flush()

    async def write_signal_snapshot(
        self,
        signal_id: int | None,
        symbol: str,
        event_type: str,
        context_data: dict[str, Any],
    ) -> None:
        """Write a point-in-time snapshot of the market context and setup state."""
        async with get_db() as session:
            snapshot = SignalSnapshot(
                signal_id=signal_id,
                symbol=symbol,
                snapshot_time=datetime.datetime.now(datetime.timezone.utc),
                event_type=event_type,
                context_data=context_data,
            )
            session.add(snapshot)
            await session.commit()

    # ── Trades ─────────────────────────────────────────────────────────────

    async def open_trade(
        self,
        signal_id: int | None,
        symbol: str,
        instrument_token: int,
        entry_order_id: str,
        entry_time: datetime.datetime,
        entry_price: float,
        quantity: int,
        initial_stop_loss: float,
        risk_per_share: float,
        risk_amount: float,
        target_1r2: float,
        target_1r3: float,
        target_1r4: float,
        sl_order_id: str | None = None,
        notes: str | None = None,
        trade_mode: str | None = None,
    ) -> int:
        """Record a new open trade. Returns trade ID."""
        async with get_db() as session:
            trade = Trade(
                signal_id=signal_id,
                symbol=symbol,
                instrument_token=instrument_token,
                entry_order_id=entry_order_id,
                entry_time=entry_time,
                entry_price=entry_price,
                quantity=quantity,
                initial_stop_loss=initial_stop_loss,
                current_stop_loss=initial_stop_loss,
                risk_per_share=risk_per_share,
                risk_amount=risk_amount,
                target_1r2=target_1r2,
                target_1r3=target_1r3,
                target_1r4=target_1r4,
                sl_order_id=sl_order_id,
                status=TradeStatus.OPEN.value,
                notes=notes,
                trade_mode=trade_mode,
            )
            session.add(trade)
            await session.flush()
            trade_id = trade.id
        log.info("trade_opened", symbol=symbol, trade_id=trade_id, entry_price=entry_price)
        return trade_id  # type: ignore[return-value]

    async def close_trade(
        self,
        trade_id: int,
        exit_price: float,
        exit_time: datetime.datetime,
        exit_order_id: str | None,
        gross_pnl: float,
        net_pnl: float,
        brokerage: float,
        stt: float,
        other_charges: float,
        status: TradeStatus,
        mfe: float | None = None,
        mae: float | None = None,
    ) -> None:
        async with get_db() as session:
            trade = await session.get(Trade, trade_id)
            if trade is None:
                log.error("trade_not_found_for_close", trade_id=trade_id)
                return
            trade.exit_price = exit_price
            trade.exit_time = exit_time
            trade.exit_order_id = exit_order_id
            trade.gross_pnl = gross_pnl
            trade.net_pnl = net_pnl
            trade.brokerage = brokerage
            trade.stt = stt
            trade.other_charges = other_charges
            trade.status = status.value
            trade.max_favorable_excursion = mfe
            trade.max_adverse_excursion = mae
            trade.updated_at = datetime.datetime.now(datetime.UTC)
        log.info(
            "trade_closed",
            trade_id=trade_id,
            status=status.value,
            net_pnl=net_pnl,
            exit_price=exit_price,
        )

    # ── Order Events ───────────────────────────────────────────────────────

    async def write_order_event(
        self,
        order_id: str,
        symbol: str,
        event_type: str,
        event_time: datetime.datetime,
        trade_id: int | None = None,
        status: str | None = None,
        price: float | None = None,
        trigger_price: float | None = None,
        quantity: int | None = None,
        filled_quantity: int | None = None,
        average_price: float | None = None,
        status_message: str | None = None,
        raw_payload: dict[str, Any] | None = None,
        trade_mode: str | None = None,
    ) -> None:
        async with get_db() as session:
            event = OrderEvent(
                order_id=order_id,
                trade_id=trade_id,
                symbol=symbol,
                event_type=event_type,
                status=status,
                price=price,
                trigger_price=trigger_price,
                quantity=quantity,
                filled_quantity=filled_quantity,
                average_price=average_price,
                status_message=status_message,
                raw_payload=json.dumps(raw_payload) if raw_payload else None,
                event_time=event_time,
                trade_mode=trade_mode,
            )
            session.add(event)
        log.debug("order_event_written", order_id=order_id, event_type=event_type)

    # ── Daily P&L ──────────────────────────────────────────────────────────

    async def write_daily_pnl(
        self,
        trade_date: datetime.date,
        total_capital: float,
        signals_fired: int,
        setups_abandoned: int,
        trades_taken: int,
        winning_trades: int,
        losing_trades: int,
        breakeven_trades: int,
        gross_pnl: float,
        total_charges: float,
        net_pnl: float,
        max_drawdown: float | None = None,
    ) -> None:
        async with get_db() as session:
            record = DailyPnl(
                trade_date=trade_date,
                total_capital=total_capital,
                signals_fired=signals_fired,
                setups_abandoned=setups_abandoned,
                trades_taken=trades_taken,
                winning_trades=winning_trades,
                losing_trades=losing_trades,
                breakeven_trades=breakeven_trades,
                gross_pnl=gross_pnl,
                total_charges=total_charges,
                net_pnl=net_pnl,
                max_drawdown=max_drawdown,
            )
            session.add(record)
        log.info(
            "daily_pnl_written",
            date=str(trade_date),
            net_pnl=net_pnl,
            trades=trades_taken,
        )


# Module-level singleton
db_writer = DbWriter()
