"""
engine/risk/position_sizer.py — 1% risk rule → quantity calculation.

Formula (spec §7.11):
  risk_amount = total_capital × (RISK_PER_TRADE_PCT / 100)
  risk_per_share = limit_price - stop_loss
  quantity = floor(risk_amount / risk_per_share)
  quantity = max(1, quantity)

Guards:
  - risk_per_share < MIN_RISK_PER_SHARE_INR → return 0
  - risk_per_share <= 0 → return 0 (zero division guard)
  - capital <= 0 → return 0
"""

from __future__ import annotations

import math

import structlog

from app.core.config import settings

log = structlog.get_logger(__name__)


def compute(
    capital: float,
    limit_price: float,
    stop_loss: float,
) -> int:
    """
    Compute the number of shares to buy based on the 1% risk rule.

    Args:
        capital:     Total account equity in ₹ (fetched from kite.margins at 9AM).
        limit_price: Proposed entry limit price.
        stop_loss:   Initial stop-loss price.

    Returns:
        Number of shares (int). Returns 0 if setup is invalid.
    """
    if capital <= 0:
        log.warning("position_sizer_zero_capital")
        return 0

    risk_per_share = limit_price - stop_loss

    if risk_per_share <= 0:
        log.warning(
            "position_sizer_invalid_rps",
            limit_price=limit_price,
            stop_loss=stop_loss,
            risk_per_share=risk_per_share,
        )
        return 0

    if risk_per_share < settings.MIN_RISK_PER_SHARE_INR:
        log.info(
            "position_sizer_rps_below_minimum",
            risk_per_share=risk_per_share,
            minimum=settings.MIN_RISK_PER_SHARE_INR,
        )
        return 0

    risk_amount = capital * (settings.RISK_PER_TRADE_PCT / 100)
    quantity = max(1, math.floor(risk_amount / risk_per_share))

    log.debug(
        "position_sized",
        capital=capital,
        risk_pct=settings.RISK_PER_TRADE_PCT,
        risk_amount=risk_amount,
        limit=limit_price,
        sl=stop_loss,
        rps=risk_per_share,
        quantity=quantity,
    )
    return quantity


def compute_lots(
    capital: float,
    entry_price: float,
    stop_loss: float,
    lot_size: int,
    risk_pct: float | None = None,
    max_lots: int | None = None,
    max_premium_exposure_pct: float | None = None,
) -> int:
    """Lot-based position sizing for F&O (futures / option buying).

    Sizes whole lots so that (entry - stop) * qty <= capital * risk_pct%, then
    optionally caps by max_lots and by premium exposure
    (entry * qty <= capital * max_premium_exposure_pct%). Returns quantity as
    lots * lot_size, or 0 if the setup cannot fund a single lot within limits.

    Args:
        capital:                  Account equity in ₹.
        entry_price:              Entry price per unit (option premium / future price).
        stop_loss:                Stop price per unit (< entry for a long).
        lot_size:                 Exchange lot size (e.g. 75 for NIFTY options).
        risk_pct:                 Risk per trade %; defaults to settings.RISK_PER_TRADE_PCT.
        max_lots:                 Optional hard cap on number of lots.
        max_premium_exposure_pct: Optional cap on premium outlay as % of capital.
    """
    if capital <= 0 or lot_size <= 0:
        return 0
    risk_per_unit = entry_price - stop_loss
    if risk_per_unit <= 0:
        return 0

    rp = settings.RISK_PER_TRADE_PCT if risk_pct is None else risk_pct
    risk_amount = capital * (rp / 100.0)
    lots = int((risk_amount / risk_per_unit) // lot_size)
    if lots < 1:
        return 0

    if max_lots is not None:
        lots = min(lots, max_lots)

    if max_premium_exposure_pct is not None and entry_price > 0:
        max_cost = capital * (max_premium_exposure_pct / 100.0)
        denom = entry_price * lot_size
        lots_by_cost = int(max_cost // denom) if denom > 0 else 0
        lots = min(lots, lots_by_cost)

    if lots < 1:
        return 0

    quantity = lots * lot_size
    log.debug(
        "position_sized_lots",
        capital=capital,
        entry=entry_price,
        sl=stop_loss,
        lot_size=lot_size,
        lots=lots,
        quantity=quantity,
    )
    return quantity
