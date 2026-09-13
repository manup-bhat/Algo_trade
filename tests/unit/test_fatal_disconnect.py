from unittest.mock import AsyncMock, MagicMock

import pytest

from engine.core.strategy_router import StrategyRouter
from engine.strategies.ivbs.strategy import IVBSStrategy
from engine.strategy.state_machine import StrategyState


@pytest.mark.asyncio
async def test_ivbs_fatal_disconnect():
    # Setup Strategy with mocked DB/Redis
    mock_redis = MagicMock()
    mock_db = MagicMock()

    strategy = IVBSStrategy("test_ivbs", mock_redis, mock_db)

    # Create two mocked state machines: one MANAGING, one IDLE
    sm_managing = MagicMock()
    sm_managing.state = StrategyState.MANAGING
    sm_managing.force_squareoff = AsyncMock()

    sm_idle = MagicMock()
    sm_idle.state = StrategyState.IDLE
    sm_idle.force_squareoff = AsyncMock()

    strategy.active_state_machines = {
        "RELIANCE": sm_managing,
        "INFY": sm_idle
    }

    # Trigger fatal disconnect
    await strategy.on_fatal_disconnect()

    # Assert MANAGING was squared off
    sm_managing.force_squareoff.assert_called_once()

    # Assert IDLE was untouched (it shouldn't fire squareoff)
    sm_idle.force_squareoff.assert_not_called()

@pytest.mark.asyncio
async def test_router_broadcasts_fatal_disconnect():
    router = StrategyRouter()

    # Mock two strategies
    strat1 = AsyncMock()
    strat1.strategy_id = "strat1"

    strat2 = AsyncMock()
    strat2.strategy_id = "strat2"

    router.register(strat1)
    router.register(strat2)

    # Trigger
    await router.on_fatal_disconnect()

    # Both should receive the signal
    strat1.on_fatal_disconnect.assert_called_once()
    strat2.on_fatal_disconnect.assert_called_once()
