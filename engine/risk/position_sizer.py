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
