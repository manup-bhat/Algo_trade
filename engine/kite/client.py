"""
engine/kite/client.py — Thin async wrapper around KiteConnect REST API.

All KiteConnect REST calls are synchronous. We wrap them with run_in_executor
to avoid blocking the asyncio event loop. The default ThreadPoolExecutor is
sufficient for our use case (at most 10 concurrent REST calls).
"""

from __future__ import annotations

import asyncio
import datetime
from typing import Any

import structlog

log = structlog.get_logger(__name__)


class AsyncKiteClient:
    """
    Async wrapper around the synchronous KiteConnect object.

    All methods that call the Kite REST API use run_in_executor to
    avoid blocking the event loop. Pattern:
        await loop.run_in_executor(None, lambda: self._kite.method(...))
    """

    def __init__(self, kite: Any) -> None:
        """
        Args:
            kite: A configured KiteConnect instance with access_token set.
        """
        self._kite = kite

    def _loop(self) -> asyncio.AbstractEventLoop:
        return asyncio.get_event_loop()

    async def profile(self) -> dict:
        return await self._loop().run_in_executor(None, self._kite.profile)

    async def margins(self, segment: str = "equity") -> dict:
        return await self._loop().run_in_executor(
            None, lambda: self._kite.margins(segment)
        )

    async def positions(self) -> dict:
        return await self._loop().run_in_executor(None, self._kite.positions)

    async def orders(self) -> list[dict]:
        return await self._loop().run_in_executor(None, self._kite.orders)

    async def trades(self) -> list[dict]:
        return await self._loop().run_in_executor(None, self._kite.trades)

    async def instruments(self, exchange: str = "NSE") -> list[dict]:
        return await self._loop().run_in_executor(
            None, lambda: self._kite.instruments(exchange)
        )

    async def historical_data(
        self,
        instrument_token: int,
        from_date: datetime.datetime | str,
        to_date: datetime.datetime | str,
        interval: str = "minute",
        continuous: bool = False,
        oi: bool = False,
    ) -> list[dict]:
        """
        Retrieve historical candles through Kite's real historical API.

        The pykiteconnect client normalizes the REST array response into dicts
        with date/open/high/low/close/volume keys.
        """
        return await self._loop().run_in_executor(
            None,
            lambda: self._kite.historical_data(
                instrument_token,
                from_date,
                to_date,
                interval,
                continuous=continuous,
                oi=oi,
            ),
        )

    async def place_order(self, **params: Any) -> str:
        """Returns order_id string."""
        return await self._loop().run_in_executor(
            None,
            lambda: self._kite.place_order(variety="regular", **params),
        )

    async def modify_order(self, order_id: str, **params: Any) -> str:
        return await self._loop().run_in_executor(
            None,
            lambda: self._kite.modify_order(
                variety="regular", order_id=order_id, **params
            ),
        )

    async def cancel_order(self, order_id: str) -> str:
        return await self._loop().run_in_executor(
            None,
            lambda: self._kite.cancel_order(variety="regular", order_id=order_id),
        )

    async def order_margins(self, orders: list[dict]) -> list[dict]:
        """
        Calculate margin requirements for proposed orders.
        Use "initial" margin value for pre-trade checks.
        """
        return await self._loop().run_in_executor(
            None,
            lambda: self._kite.order_margins(orders),
        )

    def set_access_token(self, token: str) -> None:
        """Synchronous — safe to call before event loop starts."""
        self._kite.set_access_token(token)

    async def get_available_balance(self) -> float:
        """
        Return live available cash balance for the equity segment.
        Used by pre_trade_checks (checks 7 + 8) and margin_tracker.
        """
        m = await self.margins("equity")
        return float(m.get("available", {}).get("live_balance", 0.0))

    async def get_net_equity(self) -> float:
        """
        Return net equity value (total capital) for position sizing.
        Fetched at 9:00 AM and stored in Redis engine:capital.
        """
        m = await self.margins("equity")
        return float(m.get("net", 0.0))
