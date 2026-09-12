"""
scripts/migrate_sqlite_to_postgres.py — Migrate trading data from SQLite to PostgreSQL.

Usage:
    python scripts/migrate_sqlite_to_postgres.py
    python scripts/migrate_sqlite_to_postgres.py --pg-url postgresql+asyncpg://postgres:postgres@localhost:5432/trading_bot
    python scripts/migrate_sqlite_to_postgres.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.db.base import Base
from app.models.db import (  # noqa: F401
    daily_pnl,
    order_event,
    signal,
    signal_snapshot,
    strategy,
    trade,
)

TABLE_ORDER = [
    "strategies",
    "signals",
    "signal_snapshots",
    "order_events",
    "trades",
    "daily_pnl",
]


def _read_sqlite_table(sqlite_path: str, table_name: str) -> list[dict[str, Any]]:
    """Read all rows from an SQLite table as dictionaries."""
    if not os.path.exists(sqlite_path):
        print(f"[!] SQLite file {sqlite_path} does not exist.")
        return []

    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        cursor.execute(f"SELECT * FROM {table_name}")
        rows = [dict(r) for r in cursor.fetchall()]
        return rows
    except sqlite3.OperationalError as e:
        print(f"[-] Table {table_name} not found in SQLite: {e}")
        return []
    finally:
        conn.close()


async def migrate(sqlite_path: str, pg_url: str, dry_run: bool = False) -> None:
    print("=" * 65)
    print(">> SQLite -> PostgreSQL Trading Bot Data Migration")
    print("=" * 65)
    print(f"Source SQLite  : {sqlite_path}")
    print(f"Target Postgres: {pg_url}")
    print(f"Mode           : {'DRY RUN (read only)' if dry_run else 'LIVE MIGRATION'}")
    print("-" * 65)

    # 1. Inspect SQLite counts
    sqlite_counts = {}
    sqlite_data = {}
    for tbl in TABLE_ORDER:
        rows = _read_sqlite_table(sqlite_path, tbl)
        sqlite_counts[tbl] = len(rows)
        sqlite_data[tbl] = rows
        print(f"  [SQLite] {tbl.ljust(18)} : {len(rows)} records found")

    if dry_run:
        print("\n[OK] Dry-run completed. No changes made to PostgreSQL.")
        return

    # 2. Connect to PostgreSQL
    print("\nConnecting to PostgreSQL...")
    engine = create_async_engine(
        pg_url,
        echo=False,
        pool_pre_ping=True,
    )

    try:
        # Create all tables in PostgreSQL
        print("Ensuring target schema exists in PostgreSQL...")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("[OK] PostgreSQL tables verified/created.")

        # 3. Migrate data table by table
        async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

        async with async_session() as session:
            for tbl in TABLE_ORDER:
                rows = sqlite_data[tbl]
                if not rows:
                    print(f"  [PG] {tbl.ljust(18)} : 0 records to insert (skipped)")
                    continue

                table_obj = Base.metadata.tables.get(tbl)
                if table_obj is None:
                    print(f"  [!] Metadata for {tbl} not found! Skipping.")
                    continue

                # Insert in chunks of 500
                chunk_size = 500
                inserted = 0
                for i in range(0, len(rows), chunk_size):
                    chunk = rows[i : i + chunk_size]
                    await session.execute(table_obj.insert(), chunk)
                    inserted += len(chunk)

                await session.commit()
                print(f"  [PG] {tbl.ljust(18)} : {inserted} records inserted successfully")

                # Reset sequence if id column exists
                if "id" in [c.name for c in table_obj.columns]:
                    try:
                        seq_sql = text(
                            f"SELECT setval(pg_get_serial_sequence('{tbl}', 'id'), "
                            f"COALESCE(MAX(id), 1)) FROM {tbl};"
                        )
                        await session.execute(seq_sql)
                        await session.commit()
                    except Exception:
                        pass

        # 4. Verify count parity
        print("\n" + "=" * 65)
        print("Data Parity Verification:")
        print("=" * 65)
        parity_ok = True
        async with engine.connect() as conn:
            for tbl in TABLE_ORDER:
                result = await conn.execute(text(f"SELECT count(*) FROM {tbl}"))
                pg_count = result.scalar() or 0
                sq_count = sqlite_counts[tbl]
                match = "[OK] MATCH" if pg_count == sq_count else "[!] MISMATCH"
                if pg_count != sq_count:
                    parity_ok = False
                print(f"  {tbl.ljust(18)} | SQLite: {str(sq_count).rjust(5)} | PG: {str(pg_count).rjust(5)} | {match}")

        print("-" * 65)
        if parity_ok:
            print("[SUCCESS] All tables verified with 100% parity.")
        else:
            print("[WARNING] Migration finished with mismatches.")

    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Migrate trading bot data from SQLite to PostgreSQL")
    parser.add_argument(
        "--sqlite-path",
        default="./trading.db",
        help="Path to SQLite trading.db file (default: ./trading.db)",
    )
    parser.add_argument(
        "--pg-url",
        default=os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/trading_bot"),
        help="PostgreSQL connection string (default: env DATABASE_URL or postgresql+asyncpg://postgres:postgres@localhost:5432/trading_bot)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only inspect SQLite database without modifying PostgreSQL",
    )
    args = parser.parse_args()

    # Ensure pg-url uses asyncpg driver if scheme is plain postgresql://
    pg_url = args.pg_url
    if pg_url.startswith("postgresql://"):
        pg_url = pg_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    asyncio.run(migrate(args.sqlite_path, pg_url, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
