"""engine/backtest — historical replay engine for validating strategies.

Replays candles/ticks through the SAME StrategyRouter + BaseStrategy plugins used
in live/paper trading (environment parity), with a deterministic simulated broker
and a portfolio that computes performance metrics.
"""
