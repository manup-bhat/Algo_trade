"""
engine/orders/cost_calculator.py — Transaction cost computation for all IVBS trades.

All rates from IVBS_Final_Spec.md §19.1 (verified against SEBI/NSE/Zerodha).
Uses settings object for all configurable rates — no magic numbers.

Verification example (₹5L capital, 125 shares, ₹500 entry=exit):
  Turnover: ₹62,500 buy + ₹62,500 sell = ₹1,25,000
  Brokerage:   ₹40.00 (₹20 × 2)
  STT:          ₹15.63 (sell-side: 62,500 × 0.00025)
  NSE fee:       ₹4.06 (1,25,000 × 3.25/100000)
  SEBI fee:      ₹0.13 (1,25,000 × 10/1e7)
  GST:           ₹7.20 (brokerage × 18%)
  Stamp duty:    ₹1.88 (buy-side: 62,500 × 0.00003)
  Total:        ≈₹69
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings


@dataclass(frozen=True, slots=True)
class TradeCharges:
    """All transaction costs for a single round-trip trade."""
    brokerage: float      # Flat ₹20 each side
    stt: float            # Sell-side STT (intraday equity: on sell only)
    nse_fee: float        # NSE transaction fee on total turnover
    sebi_fee: float       # SEBI regulatory fee on total turnover
    gst: float            # 18% GST on brokerage
    stamp_duty: float     # Buy-side stamp duty

    @property
    def total(self) -> float:
        return round(
            self.brokerage + self.stt + self.nse_fee
            + self.sebi_fee + self.gst + self.stamp_duty,
            2,
        )

    def __str__(self) -> str:
        return (
            f"Charges(total={self.total:.2f} | "
            f"brk={self.brokerage:.2f} stt={self.stt:.2f} "
            f"nse={self.nse_fee:.2f} sebi={self.sebi_fee:.2f} "
            f"gst={self.gst:.2f} stamp={self.stamp_duty:.2f})"
        )


def calculate(
    entry_price: float,
    exit_price: float,
    quantity: int,
) -> TradeCharges:
    """
    Compute all transaction charges for a round-trip intraday MIS trade.

    Args:
        entry_price: Actual fill price on entry.
        exit_price:  Actual fill price on exit (SL hit, target, or squareoff).
        quantity:    Number of shares.

    Returns:
        TradeCharges with all individual cost components.

    Cost basis (current rates per spec §4.1 Group B):
      STT_INTRADAY_SELL_PCT = 0.00025  (sell-side only for intraday)
      NSE_TXFEE_PER_LAKH_INR = 3.25   (₹/lakh of total turnover)
      SEBI_TXFEE_PER_CRORE_INR = 10.0 (₹/crore of total turnover)
      GST_ON_BROKERAGE_PCT = 18.0
      STAMP_DUTY_BUY_PCT = 0.00003    (buy-side only)
      BROKERAGE_PER_ORDER_INR = 20.0  (flat per order — Zerodha)
    """
    buy_turnover = entry_price * quantity
    sell_turnover = exit_price * quantity
    total_turnover = buy_turnover + sell_turnover

    # Brokerage: ₹20 flat per order, buy + sell
    brokerage = settings.BROKERAGE_PER_ORDER_INR * 2

    # STT: applies to sell-side turnover only (intraday equity MIS)
    stt = round(sell_turnover * settings.STT_INTRADAY_SELL_PCT, 2)

    # NSE transaction fee: per ₹1 lakh of total turnover
    nse_fee = round(total_turnover * settings.NSE_TXFEE_PER_LAKH_INR / 100_000, 2)

    # SEBI regulatory fee: per ₹1 crore of total turnover
    sebi_fee = round(total_turnover * settings.SEBI_TXFEE_PER_CRORE_INR / 1_00_00_000, 2)

    # GST: 18% on brokerage only
    gst = round(brokerage * settings.GST_ON_BROKERAGE_PCT / 100, 2)

    # Stamp duty: buy-side only
    stamp_duty = round(buy_turnover * settings.STAMP_DUTY_BUY_PCT, 2)

    return TradeCharges(
        brokerage=brokerage,
        stt=stt,
        nse_fee=nse_fee,
        sebi_fee=sebi_fee,
        gst=gst,
        stamp_duty=stamp_duty,
    )
