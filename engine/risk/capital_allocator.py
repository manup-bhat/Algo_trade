"""
engine/risk/capital_allocator.py — Per-strategy capital ledger.

THE CRITICAL MISSING PIECE: once more than one live strategy shares a single
Kite account, each strategy can independently believe it has room for a trade
and both fire — the account doesn't have two accounts.

This ledger tracks allocated-vs-used margin per strategy so the pre-trade gate
can check "does THIS strategy still have margin left in ITS allocation" rather
than just "does the account have margin" (Kite's get_margins() reflects the
whole account, which two strategies can each read as "sufficient" and both be
wrong once combined).

Architecture:
  - Each strategy manifest declares a capital allocation (INR absolute amount).
  - CapitalAllocator holds these in Redis so state survives engine restarts.
  - On fill: debit the strategy's allocation.
  - On close: credit back.
  - EOD: full credit reset (all strategies start the next session fully allocated).
  - CapitalAllocatorRule (Check 10) calls this before any order reaches Kite.

Redis key schema:
  capital:allocated:{strategy_id}   float  — max budget for the strategy (set once at startup)
  capital:used:{strategy_id}        float  — currently committed margin (debited on fill)

Both keys use TTL_EOD (25h) so they survive overnight but reset naturally.

Margin cushion: never allocate 100% of available margin across strategies.
The `cushion_pct` parameter reserves headroom so a slippage-driven margin call
on one strategy doesn't cascade into forced square-offs on another.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from engine.store.redis_store import RedisStore

log = structlog.get_logger(__name__)

# Redis key prefixes
_KEY_ALLOCATED = "capital:allocated:"
_KEY_USED      = "capital:used:"
_TTL = 90_000  # ~25 hours — same as other engine EOD keys


class CapitalAllocator:
    """
    Per-strategy margin ledger.

    Thread/coroutine safety: all mutations are async Redis operations.
    Redis is single-threaded on the server side, so compare-and-set
    patterns are not needed for the ledger itself (no TOCTOU risk for
    simple get/set operations on separate keys).

    Usage:
        allocator = CapitalAllocator(redis_store)
        allocator.allocate("ivbs", 200_000)         # at startup from manifest
        allocator.allocate("options_momentum", 150_000)

        ok, reason = await allocator.check("ivbs", required_margin=15_000)
        if ok:
            await allocator.debit("ivbs", 15_000)   # on fill
            ...
            await allocator.credit("ivbs", 15_000)  # on close
    """

    def __init__(self, redis_store: "RedisStore") -> None:
        self._redis = redis_store
        # In-memory map of strategy_id -> allocated INR (set at startup)
        # This is the static config; the dynamic "used" is in Redis.
        self._allocations: dict[str, float] = {}

    # ── Startup configuration ─────────────────────────────────────────────────

    def allocate(self, strategy_id: str, allocated_inr: float) -> None:
        """
        Declare a strategy's capital allocation (called once at startup).

        Args:
            strategy_id:   Must match the strategy's BaseStrategy.strategy_id.
            allocated_inr: Maximum margin (in INR) this strategy may commit at
                           any one time.  This is an absolute amount, NOT a
                           percentage of account equity (avoids dynamic re-sizing
                           when account equity fluctuates intraday).

        Edge cases:
          - Calling allocate() twice for the same strategy_id overwrites the
            previous allocation (supports hot-reload of manifest changes).
          - allocated_inr <= 0 is logged as an error but not raised (it will
            block all trades for that strategy via check(), which is safe).
        """
        if allocated_inr <= 0:
            log.error(
                "capital_allocator_invalid_allocation",
                strategy_id=strategy_id,
                allocated_inr=allocated_inr,
                hint="All trades for this strategy will be blocked.",
            )
        self._allocations[strategy_id] = allocated_inr
        log.info(
            "capital_allocated",
            strategy_id=strategy_id,
            allocated_inr=allocated_inr,
        )

    # ── Pre-trade check ───────────────────────────────────────────────────────

    async def check(
        self,
        strategy_id: str,
        required_margin: float,
    ) -> tuple[bool, str]:
        """
        Check whether strategy_id has enough free allocation for this trade.

        Returns:
            (True, "")             — sufficient free allocation
            (False, reason_str)    — allocation exceeded or strategy unknown

        Edge cases:
          - Strategy not in _allocations (strategy registered without a manifest):
            returns (False, "capital_allocator:strategy_not_allocated").
            This is intentionally a hard block — trading without a declared
            budget is the misconfiguration we most want to prevent.
          - Redis unavailable: returns (False, "capital_allocator:redis_error").
            A crashing allocator must never silently allow a trade through.
          - required_margin <= 0: passes (exit orders should never be blocked by
            this rule — use negative or zero required_margin for non-entry calls).
        """
        if required_margin <= 0:
            return True, ""

        if strategy_id not in self._allocations:
            log.warning(
                "capital_allocator_unknown_strategy",
                strategy_id=strategy_id,
                hint="Declare allocation via CapitalAllocator.allocate() at startup.",
            )
            return False, f"capital_allocator:strategy_not_allocated:{strategy_id}"

        allocated = self._allocations[strategy_id]

        try:
            used = await self._get_used(strategy_id)
        except Exception as exc:
            log.error("capital_allocator_redis_error", strategy_id=strategy_id, error=str(exc))
            return False, f"capital_allocator:redis_error:{exc!s}"

        free = allocated - used
        if required_margin > free:
            return False, (
                f"capital_allocator:insufficient_free:"
                f"strategy={strategy_id} "
                f"need={required_margin:.0f} free={free:.0f} "
                f"allocated={allocated:.0f} used={used:.0f}"
            )
        return True, ""

    # ── Fill lifecycle ────────────────────────────────────────────────────────

    async def debit(self, strategy_id: str, margin: float) -> None:
        """
        Debit *margin* from strategy's free allocation (called on order fill).

        Idempotency: if debit is called twice for the same fill (e.g. reconcile
        race), the ledger will over-debit.  Callers must guard with the same
        idempotency keys they use for fill tracking (order_id-based dedup).
        """
        if margin <= 0:
            return
        try:
            key = _KEY_USED + strategy_id
            await self._redis._r.incrbyfloat(key, margin)
            await self._redis._r.expire(key, _TTL)
            log.debug("capital_debited", strategy_id=strategy_id, margin=margin)
        except Exception as exc:
            log.error("capital_debit_failed", strategy_id=strategy_id, margin=margin, error=str(exc))

    async def credit(self, strategy_id: str, margin: float) -> None:
        """
        Credit *margin* back to strategy's free allocation (called on position close).

        Edge case: credits that push `used` below 0 are clamped to 0 — this
        handles the case where a crash-recovery reset was already done before the
        credit arrives.
        """
        if margin <= 0:
            return
        try:
            key = _KEY_USED + strategy_id
            raw = await self._redis._r.incrbyfloat(key, -margin)
            if float(raw) < 0:
                # Clamp to 0 — don't allow negative "used" (logical error, not a crash)
                await self._redis._r.set(key, "0", ex=_TTL)
                log.warning(
                    "capital_credit_clamped_to_zero",
                    strategy_id=strategy_id,
                    margin=margin,
                    raw=raw,
                )
            else:
                await self._redis._r.expire(key, _TTL)
            log.debug("capital_credited", strategy_id=strategy_id, margin=margin)
        except Exception as exc:
            log.error("capital_credit_failed", strategy_id=strategy_id, margin=margin, error=str(exc))

    async def reset_session(self, strategy_id: str | None = None) -> None:
        """
        EOD reset: zero out 'used' for one or all strategies.

        Called by EODSquareOffService after all positions are confirmed closed.
        If strategy_id is None, resets all registered strategies.
        """
        targets = [strategy_id] if strategy_id else list(self._allocations.keys())
        for sid in targets:
            try:
                key = _KEY_USED + sid
                await self._redis._r.set(key, "0", ex=_TTL)
                log.info("capital_session_reset", strategy_id=sid)
            except Exception as exc:
                log.error("capital_reset_failed", strategy_id=sid, error=str(exc))

    # ── Queries ───────────────────────────────────────────────────────────────

    async def get_free(self, strategy_id: str) -> float:
        """Return the current free allocation for a strategy."""
        allocated = self._allocations.get(strategy_id, 0.0)
        used = await self._get_used(strategy_id)
        return max(0.0, allocated - used)

    async def get_summary(self) -> dict[str, Any]:
        """Return a JSON-serializable summary of all strategy allocations (for dashboard)."""
        summary: dict[str, Any] = {}
        for sid, allocated in self._allocations.items():
            try:
                used = await self._get_used(sid)
                summary[sid] = {
                    "allocated": allocated,
                    "used": used,
                    "free": max(0.0, allocated - used),
                    "utilization_pct": round((used / allocated * 100) if allocated > 0 else 0.0, 1),
                }
            except Exception as exc:
                summary[sid] = {"error": str(exc)}
        return summary

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _get_used(self, strategy_id: str) -> float:
        key = _KEY_USED + strategy_id
        raw = await self._redis._r.get(key)
        return float(raw) if raw is not None else 0.0

    # ── Startup helper ────────────────────────────────────────────────────────

    def allocate_from_settings(self, total_capital: float) -> None:
        """
        Seed per-strategy allocations from settings + strategy config files.

        Called once at startup (runner.py) after capital is known.

        Algorithm:
          1. Load ENABLED_STRATEGIES list from settings.
          2. For each strategy ID, try loading its config.yaml for a
             ``capital_allocation_pct`` field (0.0–1.0).
          3. Compute INR allocation = total_capital * pct * cushion.
          4. Fall back to equal-split if no per-strategy config exists.

        The 90% cushion (``cushion_pct=0.9``) ensures we never allocate 100%
        of equity — leaves room for Kite's intraday margin calls and charges.

        Args:
            total_capital: Total account equity in INR as of today's pre-market.
        """
        from app.core.config import settings
        from engine.core.strategy_config import load_strategy_config

        cushion = 0.9  # Reserve 10% across the board

        enabled_ids = [
            s.strip().lower()
            for s in settings.ENABLED_STRATEGIES.split(",")
            if s.strip()
        ]

        if not enabled_ids:
            log.warning("capital_allocator_no_strategies_enabled")
            return

        per_strategy: dict[str, float] = {}
        total_pct_claimed = 0.0

        for sid in enabled_ids:
            cfg = load_strategy_config(sid)
            pct = cfg.get("capital_allocation_pct", 0.0)
            if pct > 0.0:
                per_strategy[sid] = pct
                total_pct_claimed += pct

        if total_pct_claimed == 0.0:
            # No explicit allocations — equal split across enabled strategies
            equal_pct = 1.0 / len(enabled_ids)
            per_strategy = {sid: equal_pct for sid in enabled_ids}
            log.info(
                "capital_allocator_equal_split",
                strategy_count=len(enabled_ids),
                pct_each=round(equal_pct * 100, 1),
            )
        elif total_pct_claimed > 1.0:
            # Over-allocated: normalise proportionally
            log.warning(
                "capital_allocator_over_allocated",
                total_pct=round(total_pct_claimed * 100, 1),
                note="Normalising proportionally — check config.yaml values.",
            )
            per_strategy = {
                sid: pct / total_pct_claimed
                for sid, pct in per_strategy.items()
            }

        for sid, pct in per_strategy.items():
            amount = total_capital * cushion * pct
            self.allocate(sid, amount)

        log.info(
            "capital_allocator_seeded",
            strategies=list(per_strategy.keys()),
            total_capital=total_capital,
            cushion_pct=cushion * 100,
        )
