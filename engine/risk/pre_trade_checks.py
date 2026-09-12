"""
engine/risk/pre_trade_checks.py — Twelve sequential pre-trade safety checks.

All 12 checks must pass; fail on first failure (spec §13.1).
Paper mode bypasses checks 7 and 8 (margin API calls).

Check order:
  1. Circuit breaker not tripped
  2. Concurrent positions < MAX_CONCURRENT_POSITIONS
  3. Market is open
  4. Before entry cutoff (14:00 IST)
  5. risk_per_share >= MIN_RISK_PER_SHARE_INR
  6. Quantity >= 1
  7. Margin available for this trade
  8. Peak margin safety buffer maintained
  9. SMA warmup complete for this symbol
 10. Per-strategy capital allocation (CapitalAllocator ledger)
 11. Freeze quantity guard (NSE single-order size cap)
 12. MIS intraday rule (product type, circuit proximity, session window)

Refactored to delegate each check to an independently testable RiskRule object.
The public API (PreTradeChecks.run signature and return type) is UNCHANGED —
all existing call sites in strategy code continue to work without modification.

"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from app.core.config import settings
from engine.risk.rules.base import OrderContext, run_risk_pipeline
from engine.risk.rules.circuit_breaker_rule import CircuitBreakerRule
from engine.risk.rules.concurrent_positions_rule import ConcurrentPositionsRule
from engine.risk.rules.entry_cutoff_rule import EntryCutoffRule
from engine.risk.rules.market_hours_rule import MarketHoursRule
from engine.risk.rules.margin_availability_rule import MarginAvailabilityRule
from engine.risk.rules.quantity_rule import QuantityRule
from engine.risk.rules.risk_per_share_rule import RiskPerShareRule
from engine.risk.rules.sma_warmup_rule import SmaWarmupRule
from engine.risk.rules.capital_allocator_rule import CapitalAllocatorRule
from engine.risk.rules.freeze_quantity_rule import FreezeQuantityRule
from engine.risk.rules.mis_intraday_rule import MISIntradayRule

if TYPE_CHECKING:
    from engine.kite.client import AsyncKiteClient
    from engine.market.candle_builder import CandleBuilder
    from engine.risk.capital_allocator import CapitalAllocator
    from engine.store.redis_store import RedisStore

log = structlog.get_logger(__name__)


# ── Default pipeline (10 rules, same order as the original 9) ─────────────────
# Instantiated once at module level — rules are stateless, safe to share.
_DEFAULT_RULES = [
    CircuitBreakerRule(),          # 1
    ConcurrentPositionsRule(),     # 2
    MarketHoursRule(),             # 3
    EntryCutoffRule(),             # 4
    RiskPerShareRule(),            # 5
    QuantityRule(),                # 6  — also populates ctx.computed_quantity
    MarginAvailabilityRule(),      # 7 + 8 combined
    SmaWarmupRule(),               # 9
    CapitalAllocatorRule(),        # 10 (needs capital_allocator in ctx.extra)
    FreezeQuantityRule(),          # 11 (NSE freeze qty — F&O safety)
    MISIntradayRule(),             # 12 (product=MIS, circuit guard, session window)
]


class PreTradeChecks:
    """
    Runs all 10 pre-trade checks in sequence via the RiskRule chain.

    Public API is IDENTICAL to the original implementation:
        ok, reason = await pre_trade_checks.run(
            symbol, limit_price, stop_loss,
            candle_builder, redis_store, kite
        )

    The new optional parameters (strategy_id, capital_allocator) enable the
    10th check without breaking any existing call sites that don't pass them.
    """

    def __init__(self, capital_allocator: "CapitalAllocator | None" = None) -> None:
        self._capital_allocator = capital_allocator

    def set_capital_allocator(self, allocator: "CapitalAllocator") -> None:
        """Wire in the capital allocator (called after it's initialized in runner.py)."""
        self._capital_allocator = allocator

    async def run(
        self,
        symbol: str,
        limit_price: float,
        stop_loss: float,
        candle_builder: "CandleBuilder | None",
        redis_store: "RedisStore | None",
        kite: "AsyncKiteClient | None" = None,
        *,
        strategy_id: str = "",
        extra: dict[str, Any] | None = None,
    ) -> tuple[bool, str]:
        """
        Run all 10 pre-trade checks.
        Returns (True, "") if all pass; (False, reason) on first failure.

        Args:
            symbol:         NSE/NFO trading symbol.
            limit_price:    Proposed entry limit price.
            stop_loss:      Initial stop-loss price.
            candle_builder: CandleBuilder for this symbol (for SMA warmup check).
            redis_store:    Active Redis store (for circuit breaker, positions, capital).
            kite:           Kite client (for live margin API calls; None in paper mode).
            strategy_id:    ID of the requesting strategy (for CapitalAllocatorRule).
            extra:          Additional context for specialized rules (exchange, product, etc.)
        """
        _extra: dict[str, Any] = extra or {}

        # Inject capital allocator into extra if wired
        if self._capital_allocator is not None:
            _extra.setdefault("capital_allocator", self._capital_allocator)

        ctx = OrderContext(
            symbol=symbol,
            strategy_id=strategy_id,
            limit_price=limit_price,
            stop_loss=stop_loss,
            redis_store=redis_store,
            kite=kite,
            candle_builder=candle_builder,
            is_paper_trade=settings.is_paper_trade,
            is_backtest=settings.BACKTEST_MODE,
            extra=_extra,
        )

        ok, reason = await run_risk_pipeline(ctx, _DEFAULT_RULES)

        if ok:
            log.debug(
                "pre_trade_checks_passed",
                symbol=symbol,
                strategy_id=strategy_id,
                limit=limit_price,
                sl=stop_loss,
                rps=ctx.risk_per_share,
                qty=ctx.computed_quantity,
            )

        return ok, reason


# Module-level singleton — wire capital_allocator via pre_trade_checks.set_capital_allocator()
# after it's created in runner.py
pre_trade_checks = PreTradeChecks()
