"""
tests/unit/test_freeze_quantity_rule.py — Unit tests for FreezeQuantityRule (Check 11).

Covers:
    - Qty <= freeze_qty → PASS
    - Qty > freeze_qty → BLOCK with informative reason
    - Backtest mode always passes
    - Qty = 0 passes (Quantity rule handles it upstream)
    - NSE equity (freeze=999999) effectively never blocked
    - NIFTY index options (freeze=1800) blocked at 1801+
    - _split_for_freeze: single chunk, exact multiple, remainder, qty=0
"""

from __future__ import annotations

import pytest

from engine.orders.order_service import OrderService
from engine.risk.rules.base import OrderContext
from engine.risk.rules.freeze_quantity_rule import FreezeQuantityRule


def _make_ctx(**kw) -> OrderContext:
    defaults = dict(
        symbol="RELIANCE",
        strategy_id="test",
        limit_price=500.0,
        stop_loss=460.0,
        is_paper_trade=True,
        is_backtest=False,
        computed_quantity=1,
    )
    defaults.update(kw)
    return OrderContext(**defaults)


# ── FreezeQuantityRule ────────────────────────────────────────────────────────

class TestFreezeQuantityRule:
    @pytest.fixture
    def rule(self):
        return FreezeQuantityRule()

    @pytest.fixture(autouse=True)
    def mock_instrument_master(self, monkeypatch):
        """Return freeze_qty=1800 for NIFTY*, 2500 for equity F&O, 999999 for equity."""
        def fake_freeze(symbol):
            sym = symbol.upper()
            if sym.startswith(("NIFTY", "BANKNIFTY")):
                return 1_800
            import re
            if re.search(r"\d+(CE|PE)$", sym) or sym.endswith("FUT"):
                return 2_500
            return 999_999

        class FakeMaster:
            def get_freeze_quantity(self, symbol):
                return fake_freeze(symbol)

        fake = FakeMaster()
        # Override the lazy getter so module-level cache is bypassed
        monkeypatch.setattr(
            "engine.risk.rules.freeze_quantity_rule._get_master",
            lambda: fake,
        )

    @pytest.mark.asyncio
    async def test_backtest_always_passes(self, rule):
        ctx = _make_ctx(symbol="NIFTY23SEP21000CE", computed_quantity=9999, is_backtest=True)
        result = await rule.check(ctx)
        assert not result.blocked

    @pytest.mark.asyncio
    async def test_zero_qty_passes(self, rule):
        ctx = _make_ctx(symbol="NIFTY23SEP21000CE", computed_quantity=0)
        result = await rule.check(ctx)
        assert not result.blocked

    @pytest.mark.asyncio
    async def test_nifty_within_freeze_passes(self, rule):
        ctx = _make_ctx(symbol="NIFTY23SEP21000CE", computed_quantity=1800)
        result = await rule.check(ctx)
        assert not result.blocked

    @pytest.mark.asyncio
    async def test_nifty_exceeds_freeze_blocks(self, rule):
        ctx = _make_ctx(symbol="NIFTY23SEP21000CE", computed_quantity=1801)
        result = await rule.check(ctx)
        assert result.blocked
        assert "1801" in result.reason
        assert "1800" in result.reason

    @pytest.mark.asyncio
    async def test_equity_never_blocked(self, rule):
        # Equity freeze is 999999
        ctx = _make_ctx(symbol="RELIANCE", computed_quantity=5000)
        result = await rule.check(ctx)
        assert not result.blocked

    @pytest.mark.asyncio
    async def test_equity_fno_within_freeze(self, rule):
        ctx = _make_ctx(symbol="RELIANCEFUT", computed_quantity=2500)
        result = await rule.check(ctx)
        assert not result.blocked

    @pytest.mark.asyncio
    async def test_equity_fno_exceeds_freeze(self, rule):
        ctx = _make_ctx(symbol="RELIANCEFUT", computed_quantity=2501)
        result = await rule.check(ctx)
        assert result.blocked


# ── OrderService._split_for_freeze ────────────────────────────────────────────

class TestSplitForFreeze:
    @pytest.fixture
    def svc(self, monkeypatch):
        svc = OrderService()
        # patch instrument_master inside order_service
        class FakeMaster:
            def get_freeze_quantity(self, symbol):
                if "NIFTY" in symbol.upper():
                    return 1800
                return 999_999
        monkeypatch.setattr(
            "engine.market.instrument_master.instrument_master",
            FakeMaster(),
        )
        return svc

    def test_no_split_needed(self, svc):
        splits = svc._split_for_freeze("NIFTY23SEP21000CE", 1800)
        assert splits == [1800]

    def test_exact_two_chunks(self, svc):
        splits = svc._split_for_freeze("NIFTY23SEP21000CE", 3600)
        assert splits == [1800, 1800]
        assert sum(splits) == 3600

    def test_two_chunks_with_remainder(self, svc):
        splits = svc._split_for_freeze("NIFTY23SEP21000CE", 4200)
        assert splits == [1800, 1800, 600]
        assert sum(splits) == 4200

    def test_below_freeze(self, svc):
        splits = svc._split_for_freeze("NIFTY23SEP21000CE", 500)
        assert splits == [500]

    def test_zero_qty(self, svc):
        splits = svc._split_for_freeze("NIFTY23SEP21000CE", 0)
        assert splits == [0]

    def test_equity_single_chunk(self, svc):
        # Equity freeze = 999999 → never splits for sane quantities
        splits = svc._split_for_freeze("RELIANCE", 10_000)
        assert splits == [10_000]

    def test_exactly_one_freeze_unit(self, svc):
        splits = svc._split_for_freeze("NIFTY23SEP21000CE", 1)
        assert splits == [1]
