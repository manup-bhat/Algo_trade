"""
alembic/env.py — Alembic migration environment.

Uses synchronous connection for migrations (Alembic doesn't support asyncio natively).
We create a sync engine from the async DATABASE_URL by swapping the driver.
"""

from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Import all models so Alembic can detect them
from app.models.db.base import Base
from app.models.db.signal import Signal  # noqa: F401
from app.models.db.trade import Trade  # noqa: F401
from app.models.db.order_event import OrderEvent  # noqa: F401
from app.models.db.daily_pnl import DailyPnl  # noqa: F401
from app.models.db.signal_snapshot import SignalSnapshot  # noqa: F401
from app.models.db.strategy import Strategy  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_sync_url() -> str:
    """Convert async aiosqlite URL to sync sqlite URL for Alembic."""
    url = config.get_main_option("sqlalchemy.url", "sqlite:///./trading.db")
    return url.replace("sqlite+aiosqlite", "sqlite")


def run_migrations_offline() -> None:
    url = get_sync_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    sync_url = get_sync_url()
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = sync_url

    connectable = engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
