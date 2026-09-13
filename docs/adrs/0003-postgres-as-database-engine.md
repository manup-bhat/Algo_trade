# ADR 0003: Database Engine Migration to PostgreSQL

## Status
Accepted

## Context
The platform currently uses SQLite for data persistence. While perfectly adequate for a single-strategy, single-process, local-only setup, SQLite presents severe limitations as the platform scales. Running multiple strategies concurrently, adding a background EOD squaring-off service, adding an agentic loop, and surfacing analytics in a React Flow UI introduces high concurrent read/write pressure. SQLite's file-level locking will inevitably lead to `database is locked` errors and silent contention failures in a highly concurrent, multi-threaded environment handling tick-level data and high-frequency order events.

## Decision
We will migrate the database engine from SQLite to **PostgreSQL**.
- We will encapsulate database access behind a `Repository` layer (e.g., `TradeRepository`, `SignalRepository`) so that the core domain logic remains oblivious to the underlying engine.
- This migration will occur in Phase 0 (Stabilize + Extensibility Seams) prior to the addition of concurrent multi-strategies and the agentic loop.
- We will continue to use SQLAlchemy as the ORM to manage models and migrations, ensuring a smooth transition.

## Consequences
- **Positive:** Full support for high-concurrency read/writes without locking errors, making multi-strategy scaling safe.
- **Positive:** Enables robust outbox patterns and advanced analytical materialized views.
- **Negative:** Introduces a heavier infrastructure dependency (requires a running PostgreSQL instance/container).
