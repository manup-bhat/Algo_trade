"""
engine/core — base engine infrastructure for the multi-strategy platform.

This package holds strategy-agnostic building blocks:
  - base_strategy.py   : the BaseStrategy ABC every plugin implements
  - strategy_router.py : fan-out dispatcher with per-strategy failure isolation
  - instrument.py      : asset-class abstraction (equity / futures / options)
  - order_gateway.py   : broker-agnostic order interface

Nothing here imports a concrete strategy. Strategies depend on this package,
never the other way around (Dependency Inversion).
"""
