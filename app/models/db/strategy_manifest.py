"""
app/models/db/strategy_manifest.py — StrategyManifest table.

Stores the structured requirements/capital/risk/ui declaration for each
strategy — the "data contract" between a strategy and the common engine.

Extends (not replaces) the existing `strategies` table:
  - `strategies.id` is the primary key / foreign reference point.
  - `strategy_manifest.strategy_id` references `strategies.id` as a soft FK.
  - YAML config remains as `strategies.config` (source of truth for tunables).
  - Manifest fields take PRECEDENCE over YAML for engine subscription/capital
    allocation decisions (DB row wins; YAML is the static seed/fallback).

Schema mirrors Part 2 §5 manifest shape with a `version` field for the
schema/version policy gap identified in Part 3 §2.

Phase 4 additions (agentic loop lineage — Part 3 §4):
  - `graph`         : current active StrategyIR JSON (the IR the builder saves
                      and the agent mutates).
  - `agent_lineage` : append-only list of {proposal_id, agent_run_id, version,
                      timestamp} entries — every version is traceable to either
                      a human Builder save or a specific agent run.

Alembic migrations:
  007_add_strategy_manifest.py  — initial table creation.
  009_manifest_lineage.py       — adds graph + agent_lineage columns.
"""

from __future__ import annotations

import datetime

from sqlalchemy import DateTime, Integer, JSON, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db.base import Base


class StrategyManifest(Base):
    """
    One row per strategy containing the engine data-contract fields.

    Requirements block (requirements JSON column) schema:
    {
        "instruments": {
            "mode": "watchlist" | "option_chain",
            "symbols": ["RELIANCE", "TCS", ...],   # mode=watchlist
            "underlying": "NIFTY",                  # mode=option_chain
            "expiry": "nearest_weekly",
            "strike_range_pct": 5
        },
        "candle_intervals": ["1min"],
        "tick_mode": "ltp" | "quote" | "full",
        "capabilities": ["volume_sma", "option_chain", "greeks"]
    }

    Capital block:
    { "allocated": 200000.0, "currency": "INR" }

    Risk block:
    { "max_concurrent": 3, "circuit_breaker_pct": 2.0 }

    UI block:
    { "panels": [{"type": "scanner_table", "endpoint": "/api/strategies/ivbs/scan"}] }
    """

    __tablename__ = "strategy_manifests"

    # Primary key mirrors strategy_id (no hard FK so the manifest can exist
    # independently of whether the strategies table row is populated).
    strategy_id: Mapped[str] = mapped_column(Text, primary_key=True)

    # ── Core manifest blocks ───────────────────────────────────────────────────
    requirements: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Data requirements: instruments, candle_intervals, tick_mode, capabilities",
    )
    capital: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment='Capital allocation: {"allocated": 200000.0, "currency": "INR"}',
    )
    risk: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment='Risk parameters: {"max_concurrent": 3, "circuit_breaker_pct": 2.0}',
    )
    ui: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment='UI panel declarations: {"panels": [{"type": "scanner_table", "endpoint": "..."}]}',
    )

    # ── Schema versioning (Part 3 §2 gap closure) ─────────────────────────────
    # version=1 is the initial shape defined in Part 2 §5.
    # When the IR schema evolves, bump this and write a migration rule.
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Manifest schema version — increment when the JSON shapes above change",
    )

    # ── Audit ──────────────────────────────────────────────────────────────────
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # ── Phase 4: StrategyIR graph & agent lineage ──────────────────────────────────────
    # `graph` holds the current StrategyIR JSON that the Phase 3 Builder
    # saves and that the agent proposes mutations against.  It is the
    # machine-readable definition of the strategy’s logic.
    graph: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment=(
            "Current active StrategyIR: {nodes: [...], edges: [...]}. "
            "Populated by the Builder (Phase 3) and updated by approved agent proposals (Phase 4). "
            "NEVER touched directly by the agent — only via AgentLoopService."
        ),
    )

    # `agent_lineage` is an append-only list of entries, one per version change
    # that came from the agentic loop.  Human Builder saves do NOT add an entry
    # here (they update `version` and leave lineage unchanged).
    # Entry shape: {proposal_id, agent_run_id, version, timestamp, summary}
    agent_lineage: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
        comment=(
            "Append-only list of agent-produced version changes. "
            "Each entry: {proposal_id, agent_run_id, version, timestamp, summary}. "
            "Enables full traceability of every agentic mutation (Part 3 §2 gap closure)."
        ),
    )

    # ── Helpers ──────────────────────────────────────────────────────────────────────────

    @property
    def allocated_capital(self) -> float:
        """Return the allocated INR from the capital block (0.0 if not set)."""
        if self.capital is None:
            return 0.0
        return float(self.capital.get("allocated", 0.0))

    @property
    def tick_mode(self) -> str:
        """Return the requested tick mode (defaults to 'quote')."""
        if self.requirements is None:
            return "quote"
        return str(self.requirements.get("tick_mode", "quote"))

    @property
    def required_capabilities(self) -> list[str]:
        """Return the list of required capability keys."""
        if self.requirements is None:
            return []
        return list(self.requirements.get("capabilities", []))

    def __repr__(self) -> str:
        return (
            f"StrategyManifest(id={self.strategy_id!r}, "
            f"version={self.version}, "
            f"capital={self.allocated_capital:.0f})"
        )
