from __future__ import annotations

import pytest
import pandas as pd

from portfolio.engine.strategy_compiler import compile_strategy
from portfolio.engine.strategy_schema import StrategyValidationError, validate_strategy_spec
from tests.portfolio.fixtures import valid_strategy_spec


def test_valid_strategy_spec_is_accepted():
    spec = validate_strategy_spec(valid_strategy_spec())

    assert spec.strategy_id == "stage2_fixture_v1"
    assert spec.risk.risk_per_trade_pct == 1.0
    assert spec.risk.max_position_pct == 10.0
    assert spec.risk.initial_stop["type"] == "atr"


def test_unknown_indicator_is_rejected():
    raw = valid_strategy_spec()
    raw["entry"]["all"][0]["indicator"] = "future_alpha"

    with pytest.raises(StrategyValidationError, match="unknown indicator"):
        validate_strategy_spec(raw)


def test_missing_stop_rule_is_rejected():
    raw = valid_strategy_spec()
    raw["risk"].pop("initial_stop")

    with pytest.raises(StrategyValidationError, match="initial_stop"):
        validate_strategy_spec(raw)


def test_compiler_clamps_risk_to_hard_rails():
    raw = valid_strategy_spec()
    raw["risk"]["risk_per_trade_pct"] = 9.0
    raw["risk"]["max_position_pct"] = 80.0

    compiled = compile_strategy(raw)

    assert compiled.spec.risk.risk_per_trade_pct == 2.0
    assert compiled.spec.risk.max_position_pct == 15.0


def test_missing_numeric_indicator_fails_closed():
    raw = valid_strategy_spec()
    raw["entry"]["all"] = [{"indicator": "close", "operator": "above", "value": -1}]
    compiled = compile_strategy(raw)

    assert compiled.should_enter(pd.Series({})) is False


def test_non_dict_rule_is_rejected():
    raw = valid_strategy_spec()
    raw["entry"]["all"][0] = "not a rule"

    with pytest.raises(StrategyValidationError, match="rule"):
        validate_strategy_spec(raw)


@pytest.mark.parametrize("section", ["entry", "exit", "risk"])
def test_non_dict_sections_are_rejected(section: str):
    raw = valid_strategy_spec()
    raw[section] = []

    with pytest.raises(StrategyValidationError, match=f"{section} must be a dict"):
        validate_strategy_spec(raw)


def test_bad_risk_number_is_rejected():
    raw = valid_strategy_spec()
    raw["risk"]["risk_per_trade_pct"] = "not numeric"

    with pytest.raises(StrategyValidationError, match="risk_per_trade_pct"):
        validate_strategy_spec(raw)


def test_negative_risk_is_rejected():
    raw = valid_strategy_spec()
    raw["risk"]["max_position_pct"] = -1

    with pytest.raises(StrategyValidationError, match="max_position_pct"):
        validate_strategy_spec(raw)


def test_malformed_between_value_is_rejected():
    raw = valid_strategy_spec()
    raw["entry"]["all"][2]["value"] = [45]

    with pytest.raises(StrategyValidationError, match="between"):
        validate_strategy_spec(raw)


def test_mutating_raw_after_validation_does_not_mutate_validated_spec():
    raw = valid_strategy_spec()
    spec = validate_strategy_spec(raw)

    raw["risk"]["initial_stop"]["multiple"] = 99.0
    raw["entry"]["all"][2]["value"][0] = 1
    raw["universe"]["stage"] = "STAGE_4"

    assert spec.risk.initial_stop["multiple"] == 2.0
    assert spec.entry_all[2].value == (45, 70)
    assert spec.universe["stage"] == "STAGE_2"
    assert spec.raw["risk"]["initial_stop"]["multiple"] == 2.0


def test_unknown_top_level_block_is_rejected():
    raw = valid_strategy_spec()
    raw["moonshot_filters"] = {"all": []}

    with pytest.raises(StrategyValidationError, match="unknown top-level block"):
        validate_strategy_spec(raw)


def test_unknown_timeframe_is_rejected():
    raw = _representative_block_spec()
    raw["trend_filters"]["timeframe"] = "hourly"

    with pytest.raises(StrategyValidationError, match="timeframe"):
        validate_strategy_spec(raw)


def test_unsupported_atr_stop_is_rejected():
    raw = valid_strategy_spec()
    raw["risk"]["initial_stop"]["type"] = "fixed_rupees"

    with pytest.raises(StrategyValidationError, match="stop type"):
        validate_strategy_spec(raw)


def test_malformed_atr_stop_value_is_rejected():
    raw = valid_strategy_spec()
    raw["risk"]["initial_stop"]["multiple"] = "wide"

    with pytest.raises(StrategyValidationError, match="initial_stop.multiple"):
        validate_strategy_spec(raw)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("kind", "martingale_add", "add rule kind"),
        ("operator", "crosses", "add rule operator"),
        ("timeframe", "hourly", "timeframe"),
    ],
)
def test_unknown_add_rule_kind_operator_or_timeframe_is_rejected(field: str, value: str, message: str):
    raw = _representative_block_spec()
    raw["add_rules"][0][field] = value

    with pytest.raises(StrategyValidationError, match=message):
        validate_strategy_spec(raw)


def test_representative_building_block_spec_validates_and_evaluates_deterministically():
    compiled = compile_strategy(_representative_block_spec())

    matching_row = pd.Series(
        {
            "stage": "STAGE_2",
            "close": 125.0,
            "sma_20": 120.0,
            "sma_50": 110.0,
            "sma_200": 90.0,
            "rsi_14": 55.0,
            "volume_ratio_20d": 1.6,
            "relative_strength": 82.0,
            "weekly_stage": "STAGE_2",
            "eps_growth_pct": 22.0,
            "atr_14": 5.0,
        }
    )
    failing_row = matching_row.copy()
    failing_row["weekly_stage"] = "STAGE_3"

    assert compiled.should_enter(matching_row) is True
    assert compiled.should_enter(failing_row) is False
    assert compiled.should_exit(matching_row) is False


def test_should_add_and_initial_stop_are_deterministic():
    compiled = compile_strategy(_representative_block_spec())
    row = pd.Series({"close": 125.0, "sma_20": 120.0, "atr_14": 5.0})

    assert compiled.should_add(row, position_state={"adds": 0}) is True
    assert compiled.initial_stop(entry_price=125.0, row=row) == 115.0


def _representative_block_spec() -> dict:
    raw = valid_strategy_spec()
    raw["entry"]["all"] = [{"indicator": "stage", "operator": "eq", "value": "STAGE_2"}]
    raw["stage_2"] = {
        "timeframe": "daily",
        "all": [{"indicator": "stage", "operator": "eq", "value": "STAGE_2"}],
    }
    raw["trend_filters"] = {
        "timeframe": "daily",
        "all": [
            {"indicator": "close", "operator": "above", "value": "sma_50"},
            {"indicator": "sma_50", "operator": "above", "value": "sma_200"},
        ],
    }
    raw["pullbacks"] = {
        "timeframe": "daily",
        "all": [{"indicator": "rsi_14", "operator": "between", "value": [45, 65]}],
    }
    raw["breakouts"] = {
        "timeframe": "daily",
        "all": [{"indicator": "close", "operator": "above", "value": 100}],
    }
    raw["moving_averages"] = {
        "timeframe": "daily",
        "all": [{"indicator": "close", "operator": "above", "value": "sma_20"}],
    }
    raw["volume"] = {
        "timeframe": "daily",
        "all": [{"indicator": "volume_ratio_20d", "operator": "gte", "value": 1.5}],
    }
    raw["fundamentals"] = {
        "all": [{"indicator": "eps_growth_pct", "operator": "gte", "value": 15}],
    }
    raw["multi_timeframe_confirmation"] = {
        "timeframe": "weekly",
        "all": [{"indicator": "weekly_stage", "operator": "eq", "value": "STAGE_2"}],
    }
    raw["add_rules"] = [
        {
            "kind": "pullback_add",
            "indicator": "close",
            "operator": "above",
            "value": "sma_20",
            "size_pct": 5.0,
            "risk_per_trade_pct": 0.5,
            "timeframe": "daily",
        }
    ]
    return raw
