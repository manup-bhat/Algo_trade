# ADR 0008: Agentic-Loop Approval Gates

## Status
Accepted

## Context
Phase 4 introduces an Agentic Strategy Loop, an LLM-driven process that can independently analyze market data and propose mutations to a strategy's logic via the `StrategyIR`. Allowing an autonomous agent to push logic directly to live capital introduces unacceptable structural and financial risk. We need a hardened state-machine to isolate agent exploration from live execution, guaranteeing that humans always hold the final key to capital deployment.

## Decision
We will implement strict, unidirectional state-machine approval gates for the Agentic Loop:
1. **Constraint 1 (Scope):** The agent is strictly limited to proposing `StrategyIR` mutations. It is structurally isolated from executing raw broker calls, modifying core engine files, or mutating the `capital.allocated` field in the manifest.
2. **Constraint 2 (Evaluation):** Every proposed `StrategyIR` must pass through the exact same backtest engine and analytical grading pipeline as human-coded strategies.
3. **Constraint 3 (Approval Gates):**
   - **Backtest → Paper:** The agent may autonomously run backtests. However, pushing a strategy to forward-test (Paper mode) requires an explicit human-in-the-loop approval.
   - **Paper → Live:** Pushing a strategy from Paper to Live capital requires a *second*, separate explicit human approval gate.
4. **State Machine Enforcement:** `AgentLoopService` will enforce these transitions. Rejecting a terminal proposal or attempting to jump states (e.g. Backtest → Live) will raise fatal domain errors.

## Consequences
- **Positive:** Hard physical boundary preventing AI-driven capital destruction.
- **Positive:** Leverages existing backtest and paper-trading infrastructure for validation without building parallel agent-specific sandboxes.
- **Negative:** Slows down the iteration speed of the agent, as human async approval is required at multiple stages of the lifecycle.
