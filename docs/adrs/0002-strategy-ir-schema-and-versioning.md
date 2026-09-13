# ADR 0002: Strategy IR Schema and Versioning Policy

## Status
Accepted

## Context
The platform introduces a `StrategyIR` (Intermediate Representation) which represents a strategy as a serializable JSON/DAG. This IR will be consumed by the backend execution engine (Part 1 Phase 1), a React Flow frontend builder (Part 1 Phase 2), and an LLM-driven Agentic Loop (Part 1 Phase 3). As the platform evolves, the schema of this IR will inevitably change. Without a strict versioning and migration policy, a v1 manifest loaded by v2 code (or an agent mutating a legacy manifest) will cause silent undefined behaviors, risking structural failures in a live trading system.

## Decision
We will enforce a strict Schema and Versioning Policy for `StrategyIR` and `StrategyManifest`:
- The schema will contain a mandatory integer `"version"` field (starting at `1`).
- Breaking changes to the IR shape require a version bump (e.g., v1 -> v2).
- The platform will maintain explicit, testable up-migration functions (e.g., `migrate_v1_to_v2()`).
- The Agentic Loop (Phase 4) and the React Flow builder will *always* read and emit the latest version of the IR. If they encounter a legacy version, the system will apply the up-migration function before processing.
- The `StrategyManifest` DB row will store the full lineage and version history, tracking exactly which agent run or human action produced which version.

## Consequences
- **Positive:** Guarantees backward compatibility and structural safety when dealing with old strategies.
- **Positive:** Provides the strict lineage tracking required for the Agentic Loop to safely propose and rollback mutations.
- **Negative:** Adds maintenance burden to write and unit-test migration paths every time the IR schema adds a breaking change.
