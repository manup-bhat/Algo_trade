"""
app/store/database.py — Async SQLAlchemy engine + session factory.

All DB access goes through get_db() context manager.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
    # aiosqlite: single connection fine for low-write trading bot
    connect_args={"check_same_thread": False},
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


@asynccontextmanager
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager that yields a DB session and handles commit/rollback."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Initialize SQLite tables based on SQLAlchemy models."""
    from app.models.db.base import Base
    # Import all models to ensure they are registered with Base.metadata
    from app.models.db import (  # noqa: F401
        daily_pnl,
        order_event,
        signal,
        signal_snapshot,
        strategy,
        trade,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
