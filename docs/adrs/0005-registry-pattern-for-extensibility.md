# ADR 0005: Registry Pattern for Extensibility

## Status
Accepted

## Context
As the platform expands to support multiple strategies, UI panels, analytical capabilities, and notification channels, relying on hard-coded lists or sequential `if/elif` statements in core files (like `StrategyRouter` or `dashboard_router`) leads to severe coupling. Adding a new feature currently requires modifying core execution logic, violating the Open-Closed Principle and increasing the risk of regressions in critical path systems.

## Decision
We will adopt the **Plugin/Registry Pattern** as the single, consistent future-proof extensibility layer.
- A generic `Registry[T]` class will be introduced in `engine/core/registry.py`.
- Dedicated registries will be created for:
  - `capability_registry`: Data providers (e.g., option_chains, sentiment, greeks).
  - `node_type_registry`: Strategy IR node factories (e.g., indicators, conditions, actions).
  - `ui_panel_registry`: Dashboard UI renderers.
  - `broker_registry`: Trading adapters.
  - `notification_registry`: Alert channels (e.g., telegram, sms).
- **Guardrail:** While the registry mechanisms will be established in Phase 0, we will *not* pre-populate them with speculative future implementations. They will only be populated with existing, real capabilities (e.g. `volume_sma`, `zerodha`).

## Consequences
- **Positive:** Adding a new capability, UI panel, or node type is entirely additive—simply register a new class. Core routers and runners are never touched.
- **Positive:** Allows graceful degradation (e.g., if a UI panel is requested but unregistered, the frontend can render a fallback table).
- **Negative:** Slightly obscures tracing the execution path via simple code traversal, as behavior is resolved dynamically via string keys.
