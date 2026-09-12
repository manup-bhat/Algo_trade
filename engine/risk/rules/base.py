"""
engine/risk/rules/base.py — Core types for the risk rule chain.

Pattern: Chain of Responsibility + Specification.

Every risk rule receives an OrderContext (all inputs it could need) and returns
a RiskResult (PASS or BLOCK with a reason string).  Rules are completely
independent of each other — no rule imports another, and adding a new rule
never requires editing existing ones.

The RiskRule Protocol is structural (not ABC-based) so rules are independently
unit-testable without needing the full engine wired up.

Usage:
    ctx = OrderContext(symbol="RELIANCE", ...)
    result = await some_rule.check(ctx)
    if result.blocked:
        print(result.reason)  # "max_concurrent_positions:3>=3"
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, Sequence

import structlog

if TYPE_CHECKING:
    from engine.kite.client import AsyncKiteClient
    from engine.market.candle_builder import CandleBuilder
    from engine.store.redis_store import RedisStore

log = structlog.get_logger(__name__)


# ── Data types ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RiskResult:
    """
    Verdict returned by every RiskRule.

    A PASS result has blocked=False and an empty reason.
    A BLOCK result has blocked=True and a non-empty reason string.
    """

    blocked: bool
    reason: str = ""

    # ── Constructors ──────────────────────────────────────────────────────────

    @classmethod
    def pass_(cls) -> "RiskResult":
        """Canonical PASS result."""
        return cls(blocked=False, reason="")

    @classmethod
    def block(cls, reason: str) -> "RiskResult":
        """
        Canonical BLOCK result.

        Args:
            reason: Machine-readable reason string (no spaces, uses colons as
                    delimiters, e.g. "max_concurrent_positions:3>=3").
                    This value is logged and shown in the dashboard — keep it
                    concise but informative.
        """
        if not reason:
            raise ValueError("A blocked RiskResult must have a non-empty reason string.")
        return cls(blocked=True, reason=reason)

    def __bool__(self) -> bool:
        """True means PASS (trade is allowed).  Mirrors the old (ok, reason) tuple."""
        return not self.blocked


@dataclass
class OrderContext:
    """
    All inputs a risk rule might need to evaluate a single order.

    This is the single object passed to every rule in the chain.  Centralising
    all inputs here means:
      - Rules are pure functions of OrderContext → RiskResult.
      - Tests can build any scenario by constructing one dataclass.
      - New inputs for a new rule are added here without touching old rules.

    Nullable fields are None when not relevant to a given call site (e.g.
    kite=None in paper mode, candle_builder=None for F&O market orders).
    """

    # ── Order parameters ──────────────────────────────────────────────────────
    symbol: str
    strategy_id: str
    limit_price: float
    stop_loss: float

    # ── Execution dependencies (may be None in paper / test mode) ─────────────
    redis_store: "RedisStore | None" = None
    kite: "AsyncKiteClient | None" = None
    candle_builder: "CandleBuilder | None" = None

    # ── Pre-computed values (populated lazily by rules that need them) ─────────
    # Filled in by QuantityRule so subsequent rules reuse it without recomputing.
    computed_quantity: int = 0

    # ── Flags ─────────────────────────────────────────────────────────────────
    is_paper_trade: bool = True
    is_backtest: bool = False

    # ── Extra context (for strategy-specific or future rules) ─────────────────
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def risk_per_share(self) -> float:
        return self.limit_price - self.stop_loss


# ── Protocol ──────────────────────────────────────────────────────────────────


class RiskRule(Protocol):
    """
    Structural protocol every risk rule must satisfy.

    Rules are async because some (margin availability, capital allocator) need
    async Redis / Kite API calls.  Rules that don't need I/O can still be
    async with trivial `return RiskResult.pass_()` or `return RiskResult.block(...)`.
    """

    name: str  # e.g. "circuit_breaker", "concurrent_positions"

    async def check(self, ctx: OrderContext) -> RiskResult:
        """
        Evaluate the rule against *ctx*.

        Must:
          - Be idempotent (called multiple times with same ctx → same result).
          - Never raise — exceptions must be caught internally and returned as
            a BLOCK result (a crashing risk rule blocks trading safely).
          - Be independently testable without other rules present.
        """
        ...


# ── Pipeline runner ───────────────────────────────────────────────────────────


async def run_risk_pipeline(
    ctx: OrderContext,
    rules: Sequence[RiskRule],
) -> tuple[bool, str]:
    """
    Execute *rules* in order; return on first failure.

    Returns:
        (True, "")            — all rules passed
        (False, reason_str)   — first blocking rule's reason

    This function preserves the historical (ok, reason) tuple interface so
    call sites in strategy code need no change.

    Edge cases:
      - Empty rules list → (True, "") — vacuously passes.
      - Rule raises an exception → treated as BLOCK("rule_error:{name}:{exc}")
        and the chain stops.  A crashing risk rule must never silently allow a
        trade through.
    """
    for rule in rules:
        try:
            result = await rule.check(ctx)
        except Exception as exc:
            reason = f"rule_error:{rule.name}:{exc!s}"
            log.error(
                "risk_rule_raised_exception",
                rule=rule.name,
                symbol=ctx.symbol,
                error=str(exc),
            )
            return False, reason

        if result.blocked:
            log.debug(
                "pre_trade_check_blocked",
                rule=rule.name,
                symbol=ctx.symbol,
                reason=result.reason,
            )
            return False, result.reason

    log.debug("pre_trade_checks_all_passed", symbol=ctx.symbol, rule_count=len(rules))
    return True, ""
