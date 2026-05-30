from __future__ import annotations

import pytest

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
