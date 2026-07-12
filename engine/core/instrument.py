"""
engine/core/instrument.py — Asset-class abstraction for multi-asset trading.

The current engine is hard-wired to NSE cash equity (exchange="NSE",
product="MIS"). To support futures & options this module introduces a normalized
`Instrument` value object plus the enums an order needs to route correctly to
Zerodha Kite across segments (NSE / NFO / ...).

This is a pure value layer: no I/O, stdlib only. Phase 4 populates it from the
Kite NFO instrument dump and the option-chain resolver.

Kite constants reference:
  exchange : NSE, BSE, NFO, CDS, BCD, MCX
  product  : CNC (equity delivery), NRML (F&O carry), MIS (intraday), MTF
  segment  : "NSE", "NFO-FUT", "NFO-OPT", ...
  instrument_type (dump) : "EQ", "FUT", "CE", "PE"
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from enum import Enum


class AssetClass(str, Enum):
    EQUITY = "EQUITY"
    FUTURE = "FUTURE"
    OPTION = "OPTION"


class Exchange(str, Enum):
    NSE = "NSE"
    BSE = "BSE"
    NFO = "NFO"   # NSE F&O
    CDS = "CDS"
    BCD = "BCD"
    MCX = "MCX"


class Product(str, Enum):
    CNC = "CNC"    # equity delivery
    NRML = "NRML"  # F&O overnight / carry
    MIS = "MIS"    # margin intraday square-off
    MTF = "MTF"    # margin trading facility


class OptionType(str, Enum):
    CE = "CE"  # call
    PE = "PE"  # put


# NSE cash series that indicate surveillance / restricted trading.
_RESTRICTED_SERIES = frozenset({"T", "BE", "BZ", "IL"})


def _parse_expiry(value: object) -> datetime.date | None:
    """Normalize a Kite expiry (date, datetime, or 'YYYY-MM-DD' string) to date."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, str):
        try:
            return datetime.date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


@dataclass(frozen=True, slots=True)
class Instrument:
    """Normalized, broker-agnostic instrument descriptor."""

    instrument_token: int
    tradingsymbol: str
    exchange: Exchange
    asset_class: AssetClass
    tick_size: float
    lot_size: int
    last_price: float = 0.0

    # Cash-equity only
    series: str | None = None

    # Derivatives only (None for equity)
    underlying: str | None = None
    expiry: datetime.date | None = None
    strike: float | None = None
    option_type: OptionType | None = None
    segment: str | None = None

    # ── Classification helpers ───────────────────────────────────────────────

    @property
    def is_equity(self) -> bool:
        return self.asset_class is AssetClass.EQUITY

    @property
    def is_future(self) -> bool:
        return self.asset_class is AssetClass.FUTURE

    @property
    def is_option(self) -> bool:
        return self.asset_class is AssetClass.OPTION

    @property
    def is_derivative(self) -> bool:
        return self.asset_class in (AssetClass.FUTURE, AssetClass.OPTION)

    @property
    def is_restricted(self) -> bool:
        """True for surveillance / T2T cash series (never for derivatives)."""
        return self.series in _RESTRICTED_SERIES if self.series else False

    @property
    def default_intraday_product(self) -> Product:
        """Intraday product for this asset class (this engine is intraday-only)."""
        return Product.MIS

    @property
    def default_carry_product(self) -> Product:
        """Overnight/carry product (delivery for equity, NRML for derivatives)."""
        return Product.CNC if self.is_equity else Product.NRML

    def rounded_to_tick(self, price: float) -> float:
        """Round a raw price to the instrument's tick size (2 dp fallback)."""
        if self.tick_size and self.tick_size > 0:
            steps = round(price / self.tick_size)
            return round(steps * self.tick_size, 2)
        return round(price, 2)

    # ── Construction from a Kite instrument-dump row ─────────────────────────

    @classmethod
    def from_kite_dict(cls, row: dict) -> "Instrument":
        """Build an Instrument from one row of kite.instruments(<exchange>)."""
        itype = str(row.get("instrument_type", "")).upper()
        if itype == "FUT":
            asset = AssetClass.FUTURE
            option_type: OptionType | None = None
        elif itype in ("CE", "PE"):
            asset = AssetClass.OPTION
            option_type = OptionType(itype)
        else:  # "EQ" or anything else defaults to equity
            asset = AssetClass.EQUITY
            option_type = None

        exch_raw = str(row.get("exchange", "NSE")).upper()
        try:
            exchange = Exchange(exch_raw)
        except ValueError:
            exchange = Exchange.NSE

        tick_size = float(row.get("tick_size", 0.05) or 0.05)
        lot_size = int(row.get("lot_size", 1) or 1)
        strike_raw = float(row.get("strike", 0.0) or 0.0)

        return cls(
            instrument_token=int(row.get("instrument_token", 0) or 0),
            tradingsymbol=str(row.get("tradingsymbol", "")),
            exchange=exchange,
            asset_class=asset,
            tick_size=tick_size if tick_size > 0 else 0.05,
            lot_size=lot_size if lot_size > 0 else 1,
            last_price=float(row.get("last_price", 0.0) or 0.0),
            series=(str(row["series"]) if row.get("series") else None),
            underlying=(str(row["name"]) if row.get("name") else None),
            expiry=_parse_expiry(row.get("expiry")),
            strike=strike_raw if strike_raw > 0 else None,
            option_type=option_type,
            segment=(str(row["segment"]) if row.get("segment") else None),
        )
