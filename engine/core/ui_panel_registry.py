"""
engine/core/ui_panel_registry.py — Pluggable UI panel type registry.

Every type of panel that can appear in the IVBS dashboard is registered here.
A StrategyManifest's ``ui["panels"]`` block names panel types by key; the UI
shell resolves the full descriptor (title, schema, default config) from this
registry without any hard-coded panel list.

Built-in panel types:
    scanner_table   — real-time scan hits with candlestick metrics
    option_chain    — strike ladder, ATM highlight, Greeks (IV/Δ/Θ/Vega)
    metric_card     — KPI summary tile (win rate, P&L, Sharpe, Drawdown)
    order_blotter   — order execution timeline with multi-leg group visibility
    position_table  — active positions with trailing SL / 1R2 / 1R4 / unrealised P&L
    graph_canvas    — interactive node-graph editor (node-builder UI)
    heatmap         — symbol-vs-metric colour matrix

Usage:
    from engine.core.ui_panel_registry import ui_panel_registry

    # Lookup a single panel descriptor
    desc = ui_panel_registry.get("metric_card")

    # Register a custom panel type (e.g. from a third-party plugin)
    ui_panel_registry.register("custom.my_panel", my_descriptor)

    # Enumerate all panel types (used by GET /api/v1/ui/panels)
    all_panels = {k: ui_panel_registry.get(k) for k in ui_panel_registry.list_keys()}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import structlog

from engine.core.registry import Registry

log = structlog.get_logger(__name__)


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PanelTypeDescriptor:
    """
    Immutable description of a UI panel type.

    Attributes:
        panel_type:     Registry key (e.g. "scanner_table").
        title:          Human-readable name shown in the UI header.
        description:    Single-sentence description for tool-tips / docs.
        schema:         JSON-Schema object that validates the panel's
                        ``config`` block in StrategyManifest.ui["panels"].
        default_config: Sensible defaults merged with the manifest config
                        before the panel is rendered.
        icon:           Optional icon class / emoji used in the shell UI.
        refresh_ms:     Suggested data-refresh cadence in milliseconds.
                        0 = event-driven (WebSocket only).
    """
    panel_type: str
    title: str
    description: str
    schema: dict[str, Any]
    default_config: dict[str, Any]
    icon: str = "📊"
    refresh_ms: int = 1000

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation for API responses."""
        return {
            "panel_type": self.panel_type,
            "title": self.title,
            "description": self.description,
            "schema": self.schema,
            "default_config": self.default_config,
            "icon": self.icon,
            "refresh_ms": self.refresh_ms,
        }


@runtime_checkable
class PanelRenderer(Protocol):
    """
    Protocol for custom server-side panel renderers.

    A renderer is optional — the built-in descriptors work without one.
    Use a renderer when a panel needs server-side data aggregation that is
    specific to that panel type (e.g. the option_chain fetching strike data).

    The renderer is called by the dashboard backend before the panel data
    is sent to the frontend via WebSocket or REST.
    """

    async def render(
        self,
        panel_config: dict[str, Any],
        strategy_id: str | None,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Return the data payload for one panel instance.

        Args:
            panel_config:  The merged (manifest + default) config for this
                           panel instance.
            strategy_id:   Strategy being viewed, or None for the global view.
            context:       Live context dict (redis_store, db_session, etc.)

        Returns:
            A JSON-serialisable dict that the frontend panel component consumes.
        """
        ...


# ── Registry singleton ────────────────────────────────────────────────────────

ui_panel_registry: Registry[PanelTypeDescriptor] = Registry("ui_panel")


# ── Default panel descriptors ─────────────────────────────────────────────────

def _build_default_panels() -> list[PanelTypeDescriptor]:
    """Build the seven built-in panel type descriptors."""
    return [
        PanelTypeDescriptor(
            panel_type="scanner_table",
            title="Scanner Table",
            description=(
                "Real-time scan hits table with candlestick metrics, "
                "signal strength, and state badges."
            ),
            icon="🔍",
            refresh_ms=0,  # event-driven via WebSocket scan_hit events
            schema={
                "type": "object",
                "properties": {
                    "max_rows": {"type": "integer", "minimum": 1, "maximum": 200},
                    "columns": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "show_state_badge": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
            default_config={
                "max_rows": 50,
                "columns": [
                    "symbol", "signal_time", "signal_strength",
                    "volume_spike", "close_price", "state",
                ],
                "show_state_badge": True,
            },
        ),
        PanelTypeDescriptor(
            panel_type="option_chain",
            title="Option Chain",
            description=(
                "Live NSE F&O strike ladder with ATM highlight and "
                "per-strike Greeks (IV, Δ, Θ, Vega)."
            ),
            icon="⛓️",
            refresh_ms=500,
            schema={
                "type": "object",
                "properties": {
                    "underlying": {"type": "string"},
                    "expiry": {
                        "type": "string",
                        "enum": ["nearest_weekly", "nearest_monthly", "next_monthly"],
                    },
                    "strike_range_pct": {
                        "type": "number",
                        "minimum": 1.0,
                        "maximum": 20.0,
                    },
                    "show_greeks": {"type": "boolean"},
                    "highlight_atm": {"type": "boolean"},
                },
                "required": ["underlying"],
                "additionalProperties": False,
            },
            default_config={
                "underlying": "NIFTY",
                "expiry": "nearest_weekly",
                "strike_range_pct": 5.0,
                "show_greeks": True,
                "highlight_atm": True,
            },
        ),
        PanelTypeDescriptor(
            panel_type="metric_card",
            title="Metric Card",
            description=(
                "KPI summary tile displaying strategy performance metrics: "
                "win rate, net P&L, Sharpe ratio, and maximum drawdown."
            ),
            icon="📈",
            refresh_ms=5000,
            schema={
                "type": "object",
                "properties": {
                    "metrics": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "win_rate", "net_pnl", "gross_pnl",
                                "sharpe", "max_drawdown", "total_trades",
                                "avg_trade_duration_min",
                            ],
                        },
                    },
                    "period": {
                        "type": "string",
                        "enum": ["today", "week", "month", "all_time"],
                    },
                    "layout": {
                        "type": "string",
                        "enum": ["row", "grid"],
                    },
                },
                "additionalProperties": False,
            },
            default_config={
                "metrics": ["win_rate", "net_pnl", "sharpe", "max_drawdown"],
                "period": "today",
                "layout": "row",
            },
        ),
        PanelTypeDescriptor(
            panel_type="order_blotter",
            title="Order Blotter",
            description=(
                "Chronological order execution timeline with multi-leg group "
                "collapsing, fill prices, slippage, and status badges."
            ),
            icon="📋",
            refresh_ms=0,  # event-driven via order_event WebSocket channel
            schema={
                "type": "object",
                "properties": {
                    "max_rows": {"type": "integer", "minimum": 1, "maximum": 500},
                    "show_legs": {"type": "boolean"},
                    "show_slippage": {"type": "boolean"},
                    "filter_status": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["COMPLETE", "REJECTED", "CANCELLED", "OPEN"],
                        },
                    },
                },
                "additionalProperties": False,
            },
            default_config={
                "max_rows": 100,
                "show_legs": True,
                "show_slippage": True,
                "filter_status": ["COMPLETE", "REJECTED"],
            },
        ),
        PanelTypeDescriptor(
            panel_type="position_table",
            title="Position Table",
            description=(
                "Active positions grid with entry price, trailing stop-loss, "
                "1R2/1R4 targets, unrealised P&L, and lot count."
            ),
            icon="💼",
            refresh_ms=1000,
            schema={
                "type": "object",
                "properties": {
                    "show_trailing_sl": {"type": "boolean"},
                    "show_targets": {"type": "boolean"},
                    "show_unrealised_pnl": {"type": "boolean"},
                    "highlight_breach": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
            default_config={
                "show_trailing_sl": True,
                "show_targets": True,
                "show_unrealised_pnl": True,
                "highlight_breach": True,
            },
        ),
        PanelTypeDescriptor(
            panel_type="graph_canvas",
            title="Strategy Graph Builder",
            description=(
                "Interactive drag-and-drop node-graph editor for building "
                "strategy IR graphs — palette driven from node_type_registry."
            ),
            icon="🔧",
            refresh_ms=0,  # user-driven, no polling needed
            schema={
                "type": "object",
                "properties": {
                    "read_only": {"type": "boolean"},
                    "show_palette": {"type": "boolean"},
                    "show_minimap": {"type": "boolean"},
                    "grid_snap": {"type": "boolean"},
                    "canvas_width": {"type": "integer", "minimum": 400},
                    "canvas_height": {"type": "integer", "minimum": 300},
                },
                "additionalProperties": False,
            },
            default_config={
                "read_only": False,
                "show_palette": True,
                "show_minimap": True,
                "grid_snap": True,
                "canvas_width": 1200,
                "canvas_height": 800,
            },
        ),
        PanelTypeDescriptor(
            panel_type="heatmap",
            title="Heatmap",
            description=(
                "Symbol-vs-metric colour matrix for visualising relative "
                "strength / volume / momentum across the watchlist."
            ),
            icon="🌡️",
            refresh_ms=2000,
            schema={
                "type": "object",
                "properties": {
                    "metric": {
                        "type": "string",
                        "enum": [
                            "volume_spike", "price_change_pct",
                            "rsi", "atr_pct", "open_interest_change",
                        ],
                    },
                    "color_scale": {
                        "type": "string",
                        "enum": ["RdYlGn", "RdBu", "Blues", "Reds"],
                    },
                    "cell_label": {"type": "string"},
                },
                "additionalProperties": False,
            },
            default_config={
                "metric": "volume_spike",
                "color_scale": "RdYlGn",
                "cell_label": "symbol",
            },
        ),
    ]


def register_default_panels() -> None:
    """
    Register all built-in panel types.

    Safe to call multiple times — skips already-registered keys so tests
    that import the module multiple times don't blow up with duplicate errors.
    Called automatically at module import (bottom of this file).
    """
    for descriptor in _build_default_panels():
        if not ui_panel_registry.has(descriptor.panel_type):
            ui_panel_registry.register(descriptor.panel_type, descriptor)
            log.debug(
                "ui_panel_registered",
                panel_type=descriptor.panel_type,
                title=descriptor.title,
            )


# Auto-register defaults at import time so callers need no bootstrap step.
register_default_panels()

log.debug(
    "ui_panel_registry_ready",
    registered_panel_types=ui_panel_registry.list_keys(),
)
