# ADR 0001: Broker Adapter Interface

## Status
Accepted

## Context
Currently, the trading engine directly integrates with KiteConnect (Zerodha) across multiple files and layers (e.g., `MarketDataGateway`, `OrderService`, `InstrumentMaster`). As the platform grows, we need to support multiple brokers (for redundancy or alt-data), staging/paper environments without a real broker, and unit tests without mocking deep network calls. Directly coupling domain logic (strategies, risk, sizing) to Kite's specific SDK shapes prevents this extensibility.

## Decision
We will adopt the **Ports & Adapters (Hexagonal Architecture)** pattern by defining a strictly typed `BrokerAdapter` interface (the "Port").
- The domain logic will only interact with `BrokerAdapter`.
- We will implement `ZerodhaBrokerAdapter` (the "Adapter") to wrap `kiteconnect` internals.
- We will implement `PaperBrokerAdapter` for staging and unit testing.
- The boundary will act as an Anti-Corruption Layer, translating broker-specific shapes (like Kite's raw instrument models) into the platform's domain types (`engine.core.instrument`).

## Consequences
- **Positive:** Domain logic (Risk, Strategies) is completely decoupled from Zerodha. Adding a new broker later is a matter of writing a new adapter, not refactoring domain code.
- **Positive:** Unit tests can safely run against a dummy `PaperBrokerAdapter`.
- **Negative:** Requires a translation layer which adds a small overhead and initial boilerplate to translate every API call and WebSocket payload.
