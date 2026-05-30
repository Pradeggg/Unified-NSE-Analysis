from __future__ import annotations

from dataclasses import dataclass
from typing import Any


ALLOWED_INDICATORS = {
    "stage",
    "close",
    "open",
    "high",
    "low",
    "rsi_14",
    "sma_20",
    "sma_50",
    "sma_100",
    "sma_200",
    "ema_20",
    "ema_50",
    "atr_14",
    "volume_ratio_20d",
    "relative_strength",
    "trailing_stop",
}
ALLOWED_OPERATORS = {"eq", "in", "above", "below", "gte", "lte", "between"}


class StrategyValidationError(ValueError):
    """Raised when an LLM strategy proposal is outside the allowed grammar."""


@dataclass(frozen=True)
class Rule:
    indicator: str
    operator: str
    value: Any


@dataclass(frozen=True)
class RiskSpec:
    initial_stop: dict[str, Any]
    risk_per_trade_pct: float
    max_position_pct: float


@dataclass(frozen=True)
class StrategySpec:
    strategy_id: str
    name: str
    universe: dict[str, Any]
    entry_all: tuple[Rule, ...]
    exit_any: tuple[Rule, ...]
    risk: RiskSpec
    add_rules: tuple[dict[str, Any], ...]
    raw: dict[str, Any]


def validate_strategy_spec(raw: dict[str, Any]) -> StrategySpec:
    if not isinstance(raw, dict):
        raise StrategyValidationError("strategy spec must be a dict")
    strategy_id = _required_str(raw, "strategy_id")
    name = _required_str(raw, "name")
    entry = raw.get("entry") or {}
    exit_spec = raw.get("exit") or {}
    risk = raw.get("risk") or {}
    entry_rules = tuple(_parse_rule(rule) for rule in entry.get("all") or [])
    exit_rules = tuple(_parse_rule(rule) for rule in exit_spec.get("any") or [])
    if not entry_rules:
        raise StrategyValidationError("entry.all must include at least one rule")
    if not exit_rules:
        raise StrategyValidationError("exit.any must include at least one rule")
    if "initial_stop" not in risk:
        raise StrategyValidationError("risk.initial_stop is required")
    return StrategySpec(
        strategy_id=strategy_id,
        name=name,
        universe=dict(raw.get("universe") or {}),
        entry_all=entry_rules,
        exit_any=exit_rules,
        risk=RiskSpec(
            initial_stop=dict(risk["initial_stop"]),
            risk_per_trade_pct=float(risk.get("risk_per_trade_pct", 1.0)),
            max_position_pct=float(risk.get("max_position_pct", 10.0)),
        ),
        add_rules=tuple(dict(rule) for rule in raw.get("add_rules") or []),
        raw=dict(raw),
    )


def _required_str(raw: dict[str, Any], key: str) -> str:
    value = str(raw.get(key) or "").strip()
    if not value:
        raise StrategyValidationError(f"{key} is required")
    return value


def _parse_rule(raw: dict[str, Any]) -> Rule:
    indicator = str(raw.get("indicator") or "").strip()
    operator = str(raw.get("operator") or "").strip()
    if indicator not in ALLOWED_INDICATORS:
        raise StrategyValidationError(f"unknown indicator: {indicator}")
    if operator not in ALLOWED_OPERATORS:
        raise StrategyValidationError(f"unknown operator: {operator}")
    if "value" not in raw:
        raise StrategyValidationError(f"rule value is required for {indicator}")
    return Rule(indicator=indicator, operator=operator, value=raw["value"])
