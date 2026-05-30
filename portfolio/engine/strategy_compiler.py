from __future__ import annotations

from dataclasses import replace
from typing import Any

import pandas as pd

from portfolio.engine.strategy_schema import RiskSpec, Rule, StrategySpec, validate_strategy_spec


MAX_RISK_PER_TRADE_PCT = 2.0
MAX_POSITION_PCT = 15.0


class CompiledStrategy:
    def __init__(self, spec: StrategySpec):
        self.spec = spec

    def should_enter(self, row: pd.Series) -> bool:
        return all(_eval_rule(rule, row) for rule in self.spec.entry_all)

    def should_exit(self, row: pd.Series) -> bool:
        return any(_eval_rule(rule, row) for rule in self.spec.exit_any)


def compile_strategy(raw: dict[str, Any]) -> CompiledStrategy:
    spec = validate_strategy_spec(raw)
    risk = replace(
        spec.risk,
        risk_per_trade_pct=min(spec.risk.risk_per_trade_pct, MAX_RISK_PER_TRADE_PCT),
        max_position_pct=min(spec.risk.max_position_pct, MAX_POSITION_PCT),
    )
    return CompiledStrategy(replace(spec, risk=risk))


def _eval_rule(rule: Rule, row: pd.Series) -> bool:
    left = row.get(rule.indicator)
    right = row.get(rule.value) if isinstance(rule.value, str) and rule.value in row else rule.value
    if rule.operator == "eq":
        return str(left).upper() == str(right).upper()
    if rule.operator == "in":
        return str(left).upper() in {str(item).upper() for item in (right or [])}
    if rule.operator == "above":
        return _float(left) > _float(right)
    if rule.operator == "below":
        return _float(left) < _float(right)
    if rule.operator == "gte":
        return _float(left) >= _float(right)
    if rule.operator == "lte":
        return _float(left) <= _float(right)
    if rule.operator == "between":
        low, high = list(right)
        value = _float(left)
        return _float(low) <= value <= _float(high)
    return False


def _float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0
