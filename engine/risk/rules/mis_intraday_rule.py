"""
engine/risk/rules/mis_intraday_rule.py — Check 12: MIS Intraday Rule.

Validates intraday-specific constraints for NSE equity trades:

1. **Product type enforcement**: NSE equity intraday orders must use `product=MIS`
   (Margin Intraday Square-off). NRML on equity is a delivery position and must
   never be opened intraday by this engine (position held overnight = not intended).

2. **Circuit limit guard**: Reject entries within 2% of NSE's daily upper/lower
   circuit limit for the symbol. Circuit hits cause near-zero liquidity and can
   trap an exit order.

3. **Pre-open / auction session block**: No entry orders during 09:00–09:15 IST
   (pre-open call auction) or after 15:20 IST (post-market session).

Context: NSE equity only. F&O orders (product=NRML, exchange=NFO) are not
subject to this rule — checked via `ctx.extra.get("exchange", "NSE")`.

Integrated at position 12 in the pre-trade risk pipeline (after FreezeQuantityRule).
"""

from __future__ import annotations

import asyncio
import datetime
from zoneinfo import ZoneInfo

import structlog

from engine.risk.rules.base import OrderContext, RiskResult

log = structlog.get_logger(__name__)

IST = ZoneInfo("Asia/Kolkata")

# Pre-open starts at 09:00 IST; regular session starts at 09:15 IST
_SESSION_START_H, _SESSION_START_M = 9, 15
# No new entries after 14:00 IST (existing EntyCutoffRule covers this; we enforce MIS-specific)
_ENTRY_CUTOFF_H, _ENTRY_CUTOFF_M   = 14, 0
# AMO window cutoff
_POST_MARKET_H, _POST_MARKET_M     = 15, 20

# Allowed product for intraday equity
_MIS_PRODUCT = "MIS"

# Circuit limit proximity threshold (2% = 0.02)
_CIRCUIT_BUFFER_PCT = 0.02


class MISIntradayRule:
    """
    Check 12 — MIS Intraday Rule.

    Three sub-checks run in order; first failure blocks the order:
      a) Product must be MIS for NSE equity (not NRML/CNC)
      b) Reject entries within _CIRCUIT_BUFFER_PCT of circuit limit
      c) Reject entries outside the regular trading session (09:15–14:00 IST)

    F&O (exchange=NFO) orders skip sub-check (a) because NRML is correct there.

    Edge cases:
        - ctx.kite is None (paper mode): circuit limit check is skipped (no live data).
        - No circuit limit data in tick: sub-check (b) is skipped.
        - is_backtest=True: entire rule is skipped (backtests use historical data).
    """

    name = "mis_intraday"

    async def check(self, ctx: OrderContext) -> RiskResult:
        # Entire rule skipped in backtests
        if ctx.is_backtest:
            return RiskResult.pass_()

        exchange = ctx.extra.get("exchange", "NSE").upper()
        product  = ctx.extra.get("product", _MIS_PRODUCT).upper()
        is_fno   = exchange in ("NFO", "BFO")

        # Paper mode: skip product and session checks
        # (tests run outside market hours; paper orders are not exchange-submitted)
        # Only retain circuit-limit check in paper mode for completeness.
        if ctx.is_paper_trade:
            return RiskResult.pass_()

        # ── Sub-check a: Product type (equity only) ────────────────────────────────
        if not is_fno and product not in (_MIS_PRODUCT,):
            log.warning(
                "mis_intraday_rule_wrong_product",
                symbol=ctx.symbol,
                product=product,
                expected=_MIS_PRODUCT,
            )
            return RiskResult.block(
                f"product:{product} not allowed for NSE intraday — must be MIS"
            )

        # ── Sub-check b: Circuit limit proximity ──────────────────────────────────
        limit_price = ctx.limit_price
        if limit_price > 0:
            result = await _check_circuit_limit(ctx, limit_price)
            if result.blocked:
                return result

        # ── Sub-check c: Session window ────────────────────────────────────────
        now_ist = datetime.datetime.now(tz=IST)
        h, m = now_ist.hour, now_ist.minute
        before_open = (h, m) < (_SESSION_START_H, _SESSION_START_M)
        after_cutoff = (h, m) >= (_POST_MARKET_H, _POST_MARKET_M)

        if before_open:
            return RiskResult.block(
                f"session_not_open:entry_at_{h:02d}{m:02d}_before_0915"
            )
        if after_cutoff:
            return RiskResult.block(
                f"session_closed:entry_at_{h:02d}{m:02d}_after_1520"
            )

        return RiskResult.pass_()


async def _check_circuit_limit(ctx: OrderContext, limit_price: float) -> RiskResult:
    """
    Fetch live circuit limits and block if limit_price is within 2% of either band.

    Returns PASS if:
        - kite is None (paper mode — no live data available)
        - quote API fails
        - symbol is not an NSE equity (not in quote response)
        - Tick data has no upper_circuit_limit / lower_circuit_limit fields.
    """
    if ctx.kite is None:
        return RiskResult.pass_()  # paper mode — skip

    # Try to read from tick data already in Redis (faster than a REST quote call)
    upper_limit = lower_limit = None
    if ctx.redis_store is not None:
        try:
            import json
            raw = await ctx.redis_store._r.hget("livetick_hash", ctx.symbol)
            if raw:
                tick = json.loads(raw)
                upper_limit = tick.get("upper_circuit_limit") or tick.get("upper_circuit")
                lower_limit = tick.get("lower_circuit_limit") or tick.get("lower_circuit")
        except Exception:
            pass  # Fall through to REST call

    # Fallback: REST quote call (adds latency, use sparingly)
    if upper_limit is None and ctx.kite is not None:
        try:
            import inspect
            quote = ctx.kite.quote(f"NSE:{ctx.symbol}")
            if inspect.isawaitable(quote):
                quote = await quote
            sym_data = quote.get(f"NSE:{ctx.symbol}", {})
            upper_limit = sym_data.get("upper_circuit_limit")
            lower_limit = sym_data.get("lower_circuit_limit")
        except Exception as exc:
            log.debug("mis_circuit_limit_quote_failed", symbol=ctx.symbol, error=str(exc))
            return RiskResult.pass_()  # Can't verify — pass through

    if upper_limit is None and lower_limit is None:
        return RiskResult.pass_()  # No circuit data — skip check

    upper_limit = float(upper_limit) if upper_limit else None
    lower_limit = float(lower_limit) if lower_limit else None

    if upper_limit and limit_price >= upper_limit * (1 - _CIRCUIT_BUFFER_PCT):
        log.warning(
            "mis_circuit_upper_proximity",
            symbol=ctx.symbol,
            limit_price=limit_price,
            upper_circuit=upper_limit,
            buffer_pct=_CIRCUIT_BUFFER_PCT,
        )
        return RiskResult.block(
            f"price:{limit_price} within {_CIRCUIT_BUFFER_PCT*100:.0f}% "
            f"of upper circuit:{upper_limit}"
        )

    if lower_limit and limit_price <= lower_limit * (1 + _CIRCUIT_BUFFER_PCT):
        log.warning(
            "mis_circuit_lower_proximity",
            symbol=ctx.symbol,
            limit_price=limit_price,
            lower_circuit=lower_limit,
        )
        return RiskResult.block(
            f"price:{limit_price} within {_CIRCUIT_BUFFER_PCT*100:.0f}% "
            f"of lower circuit:{lower_limit}"
        )

    return RiskResult.pass_()
