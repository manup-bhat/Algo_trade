"""
engine/risk/rules/__init__.py — Risk rule chain package.

Exposes the public API for the risk pipeline:
  - OrderContext: all inputs a rule needs to evaluate a trade
  - RiskResult: PASS or BLOCK(reason) verdict
  - RiskRule: Protocol every rule implements
  - run_risk_pipeline: execute the ordered chain, return first failure or PASS
"""

from engine.risk.rules.base import OrderContext, RiskResult, RiskRule, run_risk_pipeline

__all__ = ["OrderContext", "RiskResult", "RiskRule", "run_risk_pipeline"]
