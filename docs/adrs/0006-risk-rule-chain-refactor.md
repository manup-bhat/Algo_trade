# ADR 0006: Risk Rule Chain Refactor

## Status
Accepted

## Context
Currently, the pre-trade risk checks (e.g., market hours, concurrent positions, peak margin) are implemented as a rigid sequence of 9 if/else statements inside `pre_trade_checks.py`. This monolith is the most critical safety path in the system. As we add new rules (e.g., a new 10th check for Capital Allocation, sector exposure limits, or strategy-specific correlation limits), modifying this shared, monolithic file becomes incredibly risky.

## Decision
We will refactor the pre-trade checks using the **Chain of Responsibility** combined with the **Specification Pattern**.
- We define a `RiskRule` protocol requiring a `check(self, ctx: OrderContext) -> RiskResult` method.
- Each of the current 9 checks will be extracted into its own independently testable class (e.g., `MarketHoursRule`, `PeakMarginBufferRule`).
- A `risk_pipeline` list will chain these instances in the *exact same order* as the original if-chain.
- We will enforce strict exact-parity tests ensuring that the new pipeline produces identical pass/block outcomes as the legacy code before activating it.

## Consequences
- **Positive:** Adding a new risk rule is purely additive—write a new class and append it to the pipeline. Existing, proven safety checks are never modified.
- **Positive:** Each rule can be comprehensively unit-tested in isolation against mocked order contexts.
- **Negative:** Adds slight overhead due to object instantiation and iterative dispatch, though trivial compared to network I/O.
