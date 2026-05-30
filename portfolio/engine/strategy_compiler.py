from __future__ import annotations

import math
from dataclasses import replace
from typing import Any

import pandas as pd

from portfolio.engine.strategy_schema import AddRuleSpec, Rule, RuleGroup, StrategySpec, validate_strategy_spec


MAX_RISK_PER_TRADE_PCT = 2.0
MAX_POSITION_PCT = 15.0


class CompiledStrategy:
    def __init__(self, spec: StrategySpec):
        self.spec = spec

    def should_enter(self, row: pd.Series) -> bool:
        return all(_eval_rule(rule, row) for rule in self.spec.entry_all) and all(
            _eval_group(group, row) for group in self.spec.block_groups
        )

    def should_exit(self, row: pd.Series) -> bool:
        return any(_eval_rule(rule, row) for rule in self.spec.exit_any)

    def should_add(self, row: pd.Series, position_state: dict[str, Any] | None = None) -> bool:
        return any(_eval_add_rule(rule, row, position_state) for rule in self.spec.add_rules)

    def initial_stop(self, entry_price: float, row: pd.Series) -> float | None:
        stop = self.spec.risk.initial_stop
        if stop.type == "atr":
            price = _float(entry_price)
            atr = _float(row.get(stop.indicator))
            if price is None or atr is None or stop.multiple is None:
                return None
            return price - (atr * stop.multiple)
        return None


def compile_strategy(raw: dict[str, Any]) -> CompiledStrategy:
    spec = validate_strategy_spec(raw)
    risk = replace(
        spec.risk,
        risk_per_trade_pct=min(spec.risk.risk_per_trade_pct, MAX_RISK_PER_TRADE_PCT),
        max_position_pct=min(spec.risk.max_position_pct, MAX_POSITION_PCT),
    )
    return CompiledStrategy(replace(spec, risk=risk))


def _eval_rule(rule: Rule, row: pd.Series) -> bool:
    if rule.indicator not in row:
        return False
    left = row.get(rule.indicator)
    right = row.get(rule.value) if isinstance(rule.value, str) and rule.value in row else rule.value
    if rule.operator == "eq":
        return str(left).upper() == str(right).upper()
    if rule.operator == "in":
        return str(left).upper() in {str(item).upper() for item in (right or [])}
    if rule.operator == "above":
        left_value = _float(left)
        right_value = _float(right)
        return left_value is not None and right_value is not None and left_value > right_value
    if rule.operator == "below":
        left_value = _float(left)
        right_value = _float(right)
        return left_value is not None and right_value is not None and left_value < right_value
    if rule.operator == "gte":
        left_value = _float(left)
        right_value = _float(right)
        return left_value is not None and right_value is not None and left_value >= right_value
    if rule.operator == "lte":
        left_value = _float(left)
        right_value = _float(right)
        return left_value is not None and right_value is not None and left_value <= right_value
    if rule.operator == "between":
        if isinstance(right, str):
            return False
        try:
            low, high = list(right)
        except (TypeError, ValueError):
            return False
        value = _float(left)
        low_value = _float(low)
        high_value = _float(high)
        return (
            value is not None
            and low_value is not None
            and high_value is not None
            and low_value <= value <= high_value
        )
    return False


def _eval_group(group: RuleGroup, row: pd.Series) -> bool:
    all_pass = all(_eval_rule(rule, row) for rule in group.all_rules)
    any_pass = True if not group.any_rules else any(_eval_rule(rule, row) for rule in group.any_rules)
    return all_pass and any_pass


def _eval_add_rule(rule: AddRuleSpec, row: pd.Series, position_state: dict[str, Any] | None) -> bool:
    _ = position_state
    return _eval_rule(rule.rule, row)


def _float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed
