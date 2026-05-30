from __future__ import annotations

import math
from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Any


ALLOWED_INDICATORS = {
    "stage",
    "weekly_stage",
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
    "eps_growth_pct",
    "sales_growth_pct",
    "debt_to_equity",
    "roe_pct",
}
ALLOWED_OPERATORS = {"eq", "in", "above", "below", "gte", "lte", "between"}
ALLOWED_TIMEFRAMES = {
    "daily",
    "weekly",
    "monthly",
    "intraday_5m",
    "intraday_15m",
    "intraday_30m",
    "intraday_60m",
}
ENTRY_BLOCK_KEYS = (
    "stage_2",
    "trend_filters",
    "pullbacks",
    "breakouts",
    "moving_averages",
    "volume",
    "fundamentals",
    "multi_timeframe_confirmation",
)
ALLOWED_TOP_LEVEL_KEYS = {
    "strategy_id",
    "name",
    "universe",
    "entry",
    "exit",
    "risk",
    "add_rules",
} | set(ENTRY_BLOCK_KEYS)
ALLOWED_STOP_TYPES = {"atr"}
ALLOWED_ATR_STOP_INDICATORS = {"atr_14"}
ALLOWED_ATR_STOP_KEYS = {"type", "multiple", "indicator"}
ALLOWED_ADD_RULE_KINDS = {"pullback_add", "breakout_add", "trend_add"}


class StrategyValidationError(ValueError):
    """Raised when an LLM strategy proposal is outside the allowed grammar."""


@dataclass(frozen=True)
class Rule:
    indicator: str
    operator: str
    value: Any


@dataclass(frozen=True)
class RuleGroup:
    kind: str
    all_rules: tuple[Rule, ...]
    any_rules: tuple[Rule, ...]
    timeframe: str | None = None


@dataclass(frozen=True)
class InitialStopSpec:
    type: str
    multiple: float | None = None
    percent: float | None = None
    indicator: str = "atr_14"

    def __getitem__(self, key: str) -> Any:
        return {
            "type": self.type,
            "multiple": self.multiple,
            "percent": self.percent,
            "indicator": self.indicator,
        }[key]


@dataclass(frozen=True)
class RiskSpec:
    initial_stop: InitialStopSpec
    risk_per_trade_pct: float
    max_position_pct: float


@dataclass(frozen=True)
class AddRuleSpec:
    kind: str
    rule: Rule
    size_pct: float
    risk_per_trade_pct: float | None = None
    timeframe: str | None = None


@dataclass(frozen=True)
class StrategySpec:
    strategy_id: str
    name: str
    universe: dict[str, Any]
    entry_all: tuple[Rule, ...]
    exit_any: tuple[Rule, ...]
    risk: RiskSpec
    block_groups: tuple[RuleGroup, ...]
    add_rules: tuple[AddRuleSpec, ...]
    raw: dict[str, Any]


def validate_strategy_spec(raw: dict[str, Any]) -> StrategySpec:
    if not isinstance(raw, dict):
        raise StrategyValidationError("strategy spec must be a dict")
    _reject_unknown_top_level_blocks(raw)
    strategy_id = _required_str(raw, "strategy_id")
    name = _required_str(raw, "name")
    entry = _optional_dict(raw, "entry")
    exit_spec = _optional_dict(raw, "exit")
    risk = _optional_dict(raw, "risk")
    entry_rules = tuple(_parse_rule(rule) for rule in entry.get("all") or [])
    exit_rules = tuple(_parse_rule(rule) for rule in exit_spec.get("any") or [])
    if not entry_rules:
        raise StrategyValidationError("entry.all must include at least one rule")
    if not exit_rules:
        raise StrategyValidationError("exit.any must include at least one rule")
    if "initial_stop" not in risk:
        raise StrategyValidationError("risk.initial_stop is required")
    block_groups = tuple(_parse_rule_group(kind, _optional_dict(raw, kind)) for kind in ENTRY_BLOCK_KEYS if kind in raw)
    return StrategySpec(
        strategy_id=strategy_id,
        name=name,
        universe=deepcopy(_optional_dict(raw, "universe")),
        entry_all=entry_rules,
        exit_any=exit_rules,
        risk=RiskSpec(
            initial_stop=_parse_initial_stop(_required_dict(risk, "risk.initial_stop")),
            risk_per_trade_pct=_positive_float(risk.get("risk_per_trade_pct", 1.0), "risk_per_trade_pct"),
            max_position_pct=_positive_float(risk.get("max_position_pct", 10.0), "max_position_pct"),
        ),
        block_groups=block_groups,
        add_rules=tuple(_parse_add_rule(rule) for rule in raw.get("add_rules") or []),
        raw=deepcopy(raw),
    )


def _required_str(raw: dict[str, Any], key: str) -> str:
    value = str(raw.get(key) or "").strip()
    if not value:
        raise StrategyValidationError(f"{key} is required")
    return value


def _reject_unknown_top_level_blocks(raw: dict[str, Any]) -> None:
    unknown = set(raw) - ALLOWED_TOP_LEVEL_KEYS
    if unknown:
        raise StrategyValidationError(f"unknown top-level block: {sorted(unknown)[0]}")


def _parse_rule_group(kind: str, raw: dict[str, Any]) -> RuleGroup:
    unknown = set(raw) - {"all", "any", "timeframe"}
    if unknown:
        raise StrategyValidationError(f"{kind} includes unknown key: {sorted(unknown)[0]}")
    all_rules = tuple(_parse_rule(rule) for rule in raw.get("all") or [])
    any_rules = tuple(_parse_rule(rule) for rule in raw.get("any") or [])
    if not all_rules and not any_rules:
        raise StrategyValidationError(f"{kind} must include at least one rule")
    return RuleGroup(
        kind=kind,
        all_rules=all_rules,
        any_rules=any_rules,
        timeframe=_optional_timeframe(raw.get("timeframe"), f"{kind}.timeframe"),
    )


def _parse_rule(raw: dict[str, Any]) -> Rule:
    if not isinstance(raw, dict):
        raise StrategyValidationError("rule must be a dict")
    indicator = str(raw.get("indicator") or "").strip()
    operator = str(raw.get("operator") or "").strip()
    if indicator not in ALLOWED_INDICATORS:
        raise StrategyValidationError(f"unknown indicator: {indicator}")
    if operator not in ALLOWED_OPERATORS:
        raise StrategyValidationError(f"unknown operator: {operator}")
    if "value" not in raw:
        raise StrategyValidationError(f"rule value is required for {indicator}")
    return Rule(indicator=indicator, operator=operator, value=_validate_rule_value(operator, raw["value"]))


def _parse_initial_stop(raw: dict[str, Any]) -> InitialStopSpec:
    stop_type = str(raw.get("type") or "").strip()
    if stop_type not in ALLOWED_STOP_TYPES:
        raise StrategyValidationError(f"unsupported initial stop type: {stop_type}")
    if stop_type == "atr":
        unknown = set(raw) - ALLOWED_ATR_STOP_KEYS
        if unknown:
            raise StrategyValidationError(f"risk.initial_stop includes unsupported field: {sorted(unknown)[0]}")
        if "multiple" not in raw:
            raise StrategyValidationError("risk.initial_stop.multiple is required for atr stops")
        multiple = _positive_float(raw["multiple"], "risk.initial_stop.multiple")
        indicator = _optional_atr_indicator(raw)
        if indicator not in ALLOWED_ATR_STOP_INDICATORS:
            raise StrategyValidationError(f"unsupported ATR indicator: {indicator}")
        return InitialStopSpec(type=stop_type, multiple=multiple, indicator=indicator)
    raise StrategyValidationError(f"unsupported initial stop type: {stop_type}")


def _parse_add_rule(raw: dict[str, Any]) -> AddRuleSpec:
    if not isinstance(raw, dict):
        raise StrategyValidationError("add rule must be a dict")
    kind = str(raw.get("kind") or "").strip()
    if kind not in ALLOWED_ADD_RULE_KINDS:
        raise StrategyValidationError(f"unknown add rule kind: {kind}")
    operator = str(raw.get("operator") or "").strip()
    if operator not in ALLOWED_OPERATORS:
        raise StrategyValidationError(f"unknown add rule operator: {operator}")
    rule = _parse_rule(raw)
    return AddRuleSpec(
        kind=kind,
        rule=rule,
        size_pct=_positive_float(raw.get("size_pct", 1.0), "add rule size_pct"),
        risk_per_trade_pct=(
            _positive_float(raw["risk_per_trade_pct"], "add rule risk_per_trade_pct")
            if "risk_per_trade_pct" in raw
            else None
        ),
        timeframe=_optional_timeframe(raw.get("timeframe"), "add rule timeframe"),
    )


def _optional_dict(raw: dict[str, Any], key: str) -> dict[str, Any]:
    value = raw.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise StrategyValidationError(f"{key} must be a dict")
    return value


def _required_dict(raw: dict[str, Any], key: str) -> dict[str, Any]:
    value = raw.get(key.rsplit(".", 1)[-1])
    if not isinstance(value, dict):
        raise StrategyValidationError(f"{key} must be a dict")
    return value


def _positive_float(value: Any, field_name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise StrategyValidationError(f"{field_name} must be numeric") from exc
    if not math.isfinite(parsed) or parsed <= 0:
        raise StrategyValidationError(f"{field_name} must be positive and finite")
    return parsed


def _optional_timeframe(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    timeframe = str(value).strip()
    if timeframe not in ALLOWED_TIMEFRAMES:
        raise StrategyValidationError(f"unknown timeframe for {field_name}: {timeframe}")
    return timeframe


def _optional_atr_indicator(raw: dict[str, Any]) -> str:
    if "indicator" not in raw:
        return "atr_14"
    value = raw["indicator"]
    if not isinstance(value, str) or not value.strip():
        raise StrategyValidationError("unsupported ATR indicator")
    return value.strip()


def _validate_rule_value(operator: str, value: Any) -> Any:
    if operator == "between":
        if isinstance(value, str) or not isinstance(value, Sequence) or len(value) != 2:
            raise StrategyValidationError("between value must contain exactly two numeric values")
        return tuple(_numeric_rule_value(item, "between") for item in value)
    if operator == "in":
        if isinstance(value, str) or not isinstance(value, Sequence):
            raise StrategyValidationError("in value must be a non-string sequence")
        return tuple(_immutable_copy(item) for item in value)
    if operator in {"above", "below", "gte", "lte"}:
        if isinstance(value, str) and value in ALLOWED_INDICATORS:
            return value
        return _numeric_rule_value(value, operator)
    return _immutable_copy(value)


def _numeric_rule_value(value: Any, operator: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise StrategyValidationError(f"{operator} value must be numeric") from exc
    if not math.isfinite(parsed):
        raise StrategyValidationError(f"{operator} value must be finite")
    return parsed


def _immutable_copy(value: Any) -> Any:
    if isinstance(value, dict):
        return tuple((key, _immutable_copy(item)) for key, item in deepcopy(value).items())
    if isinstance(value, list):
        return tuple(_immutable_copy(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_immutable_copy(item) for item in value)
    return deepcopy(value)
