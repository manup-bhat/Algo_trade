# ADR 0004: Capital Allocator Ledger & Margin Cushion Policy

## Status
Accepted

## Context
The platform currently operates two live-capable strategies (`IVBS` and `OptionsMomentum`) sharing a single Kite account. Because they evaluate against undivided margin without isolated capital buckets, an aggressive scale-in by one strategy could starve the other or trigger broker rejections due to insufficient margin. Furthermore, unexpected margin spikes (e.g. holding options overnight into an expiry day) could cause cascading failures. The original plan relegated the `CapitalAllocator` to a later phase (Phase 2+), but given the latent risk of running multiple strategies against an undivided pool today, this needs immediate attention.

## Decision
We will implement a central `CapitalAllocator` ledger and a strict Margin-Cushion Policy, bringing this work completely forward into **Phase 0**.
- The `CapitalAllocator` will maintain isolated logical ledgers (`allocated`, `utilized`, `reserved`) per strategy.
- A new `CapitalAllocatorRule` will be added as the 10th pre-trade check in the risk pipeline to enforce that an order never exceeds a strategy's isolated allocated margin.
- A global margin cushion buffer (e.g. 5-10% unallocated) will be mandated to absorb broker margin-requirement spikes.
- The `StrategyManifest` will dictate `capital.allocated` which acts as the unbreachable ceiling; the agentic loop (Phase 4) is strictly forbidden from mutating this value.

## Consequences
- **Positive:** Safely supports multiple live concurrent strategies without cross-contamination or margin starvation.
- **Positive:** Hardens the structural boundary against agent-driven over-leveraging.
- **Negative:** Adds complexity to order placement, as capital must be reserved upon order generation and reconciled upon fill/cancellation.
