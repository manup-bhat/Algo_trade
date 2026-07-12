"""
tests/unit/test_option_chain.py — OptionChainResolver (Phase 4 F&O).
"""

from __future__ import annotations

import datetime

from engine.core.instrument import AssetClass, OptionType
from engine.market.option_chain import OptionChainResolver


def _dump() -> tuple[list[dict], str, str]:
    exp1 = (datetime.date.today() + datetime.timedelta(days=3)).isoformat()
    exp2 = (datetime.date.today() + datetime.timedelta(days=10)).isoformat()
    rows: list[dict] = []
    tok = 1
    for exp in (exp1, exp2):
        tag = exp.replace("-", "")
        for strike in (23900, 24000, 24100):
            for it in ("CE", "PE"):
                tok += 1
                rows.append({
                    "instrument_token": tok,
                    "tradingsymbol": f"NIFTY{tag}{strike}{it}",
                    "name": "NIFTY",
                    "last_price": 0.0,
                    "expiry": exp,
                    "strike": strike,
                    "tick_size": 0.05,
                    "lot_size": 75,
                    "instrument_type": it,
                    "segment": "NFO-OPT",
                    "exchange": "NFO",
                })
    rows.append({
        "instrument_token": 999,
        "tradingsymbol": "NIFTYFUT1",
        "name": "NIFTY",
        "last_price": 0.0,
        "expiry": exp1,
        "strike": 0,
        "tick_size": 0.05,
        "lot_size": 75,
        "instrument_type": "FUT",
        "segment": "NFO-FUT",
        "exchange": "NFO",
    })
    return rows, exp1, exp2


class TestOptionChainResolver:
    def test_load_and_expiries_sorted(self):
        r = OptionChainResolver()
        dump, exp1, exp2 = _dump()
        r.load(dump)
        exps = r.expiries("NIFTY")
        assert exps == [datetime.date.fromisoformat(exp1), datetime.date.fromisoformat(exp2)]

    def test_nearest_expiry(self):
        r = OptionChainResolver()
        dump, exp1, _ = _dump()
        r.load(dump)
        assert r.nearest_expiry("NIFTY") == datetime.date.fromisoformat(exp1)

    def test_atm_strike_uses_listed_strikes(self):
        r = OptionChainResolver()
        dump, exp1, _ = _dump()
        r.load(dump)
        e = datetime.date.fromisoformat(exp1)
        assert r.atm_strike("NIFTY", 24030, e, OptionType.CE) == 24000
        assert r.atm_strike("NIFTY", 24080, e, OptionType.CE) == 24100

    def test_atm_option_resolves_instrument(self):
        r = OptionChainResolver()
        dump, exp1, _ = _dump()
        r.load(dump)
        e = datetime.date.fromisoformat(exp1)
        opt = r.atm_option("NIFTY", 24030, OptionType.CE, e)
        assert opt is not None
        assert opt.strike == 24000
        assert opt.option_type == OptionType.CE
        assert opt.asset_class == AssetClass.OPTION
        assert opt.lot_size == 75
        assert opt.exchange.value == "NFO"

    def test_resolve_and_future(self):
        r = OptionChainResolver()
        dump, exp1, _ = _dump()
        r.load(dump)
        e = datetime.date.fromisoformat(exp1)
        assert r.resolve("NIFTY", e, OptionType.PE, 24100) is not None
        fut = r.future("NIFTY", e)
        assert fut is not None and fut.is_future

    def test_strikes_sorted(self):
        r = OptionChainResolver()
        dump, exp1, _ = _dump()
        r.load(dump)
        e = datetime.date.fromisoformat(exp1)
        assert r.strikes("NIFTY", e, OptionType.CE) == [23900.0, 24000.0, 24100.0]

    def test_empty_or_unknown_underlying(self):
        r = OptionChainResolver()
        r.load([])
        assert r.nearest_expiry("NIFTY") is None
        assert r.atm_option("NIFTY", 24000, OptionType.CE) is None
        assert r.expiries("NIFTY") == []
