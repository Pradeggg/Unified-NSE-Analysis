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
