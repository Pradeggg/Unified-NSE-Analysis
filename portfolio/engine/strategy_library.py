from __future__ import annotations

from copy import deepcopy
from typing import Any


def built_in_strategy_specs() -> list[dict[str, Any]]:
    """Return validated-by-schema strategy templates for common paper strategies."""

    return deepcopy(_BUILT_IN_STRATEGY_SPECS)


def get_strategy_spec(strategy_id: str) -> dict[str, Any]:
    """Return a deep copy of a built-in strategy template by id."""

    for spec in _BUILT_IN_STRATEGY_SPECS:
        if spec["strategy_id"] == strategy_id:
            return deepcopy(spec)
    raise KeyError(f"unknown built-in strategy_id: {strategy_id}")


def _rule(indicator: str, operator: str, value: Any) -> dict[str, Any]:
    return {"indicator": indicator, "operator": operator, "value": value}


def _atr_risk(multiple: float, risk_per_trade_pct: float, max_position_pct: float) -> dict[str, Any]:
    return {
        "initial_stop": {"type": "atr", "indicator": "atr_14", "multiple": multiple},
        "risk_per_trade_pct": risk_per_trade_pct,
        "max_position_pct": max_position_pct,
    }


_BUILT_IN_STRATEGY_SPECS: list[dict[str, Any]] = [
    {
        "strategy_id": "stage2_continuation_v1",
        "name": "Stage 2 Continuation",
        "universe": {"stage": "STAGE_2", "min_price": 50},
        "entry": {
            "all": [
                _rule("stage", "eq", "STAGE_2"),
                _rule("close", "above", "sma_50"),
                _rule("sma_50", "above", "sma_200"),
                _rule("rsi_14", "between", [45, 70]),
            ]
        },
        "trend_filters": {
            "timeframe": "daily",
            "all": [_rule("close", "above", "sma_50"), _rule("sma_50", "above", "sma_200")],
        },
        "volume": {"timeframe": "daily", "all": [_rule("volume_ratio_20d", "gte", 1.1)]},
        "risk": _atr_risk(multiple=2.0, risk_per_trade_pct=1.0, max_position_pct=10.0),
        "add_rules": [
            {
                "kind": "pullback_add",
                "indicator": "close",
                "operator": "above",
                "value": "sma_20",
                "size_pct": 5.0,
                "risk_per_trade_pct": 0.5,
                "timeframe": "daily",
            }
        ],
        "exit": {
            "any": [
                _rule("stage", "in", ["STAGE_3", "STAGE_4"]),
                _rule("close", "below", "sma_50"),
                _rule("trailing_stop", "gte", 1),
            ]
        },
    },
    {
        "strategy_id": "donchian_turtle_breakout_v1",
        "name": "Donchian Turtle Breakout",
        "universe": {"min_price": 50},
        "entry": {
            "all": [
                _rule("close", "above", "sma_100"),
                _rule("sma_50", "above", "sma_200"),
                _rule("relative_strength", "gte", 65),
                _rule("volume_ratio_20d", "gte", 1.3),
            ]
        },
        "breakouts": {"timeframe": "daily", "all": [_rule("close", "above", "sma_100")]},
        "trend_filters": {"timeframe": "daily", "all": [_rule("sma_50", "above", "sma_200")]},
        "risk": _atr_risk(multiple=2.0, risk_per_trade_pct=1.0, max_position_pct=12.0),
        "add_rules": [
            {
                "kind": "breakout_add",
                "indicator": "close",
                "operator": "above",
                "value": "sma_20",
                "size_pct": 4.0,
                "risk_per_trade_pct": 0.5,
                "timeframe": "daily",
            }
        ],
        "exit": {"any": [_rule("close", "below", "sma_50"), _rule("trailing_stop", "gte", 1)]},
    },
    {
        "strategy_id": "moving_average_trend_v1",
        "name": "Moving Average Trend",
        "universe": {"min_price": 50},
        "entry": {
            "all": [
                _rule("close", "above", "sma_20"),
                _rule("sma_20", "above", "sma_50"),
                _rule("sma_50", "above", "sma_200"),
            ]
        },
        "moving_averages": {
            "timeframe": "daily",
            "all": [
                _rule("close", "above", "sma_20"),
                _rule("sma_20", "above", "sma_50"),
                _rule("sma_50", "above", "sma_200"),
            ],
        },
        "risk": _atr_risk(multiple=2.2, risk_per_trade_pct=0.8, max_position_pct=10.0),
        "add_rules": [],
        "exit": {"any": [_rule("close", "below", "sma_50"), _rule("sma_20", "below", "sma_50")]},
    },
    {
        "strategy_id": "momentum_rotation_v1",
        "name": "Momentum Rotation",
        "universe": {"min_price": 50},
        "entry": {
            "all": [
                _rule("relative_strength", "gte", 80),
                _rule("rsi_14", "between", [50, 75]),
                _rule("close", "above", "sma_50"),
                _rule("volume_ratio_20d", "gte", 1.1),
            ]
        },
        "trend_filters": {"timeframe": "daily", "all": [_rule("close", "above", "sma_50")]},
        "risk": _atr_risk(multiple=2.0, risk_per_trade_pct=0.75, max_position_pct=8.0),
        "add_rules": [],
        "exit": {"any": [_rule("relative_strength", "below", 60), _rule("close", "below", "sma_50")]},
    },
    {
        "strategy_id": "vcp_breakout_v1",
        "name": "VCP Breakout",
        "universe": {"stage": "STAGE_2", "min_price": 50},
        "entry": {
            "all": [
                _rule("stage", "eq", "STAGE_2"),
                _rule("close", "above", "sma_20"),
                _rule("sma_20", "above", "sma_50"),
                _rule("volume_ratio_20d", "gte", 1.5),
                _rule("rsi_14", "between", [50, 75]),
            ]
        },
        "pullbacks": {"timeframe": "daily", "all": [_rule("rsi_14", "between", [45, 65])]},
        "breakouts": {"timeframe": "daily", "all": [_rule("volume_ratio_20d", "gte", 1.5)]},
        "risk": _atr_risk(multiple=1.8, risk_per_trade_pct=0.75, max_position_pct=8.0),
        "add_rules": [
            {
                "kind": "breakout_add",
                "indicator": "volume_ratio_20d",
                "operator": "gte",
                "value": 1.8,
                "size_pct": 3.0,
                "risk_per_trade_pct": 0.4,
                "timeframe": "daily",
            }
        ],
        "exit": {"any": [_rule("close", "below", "sma_20"), _rule("rsi_14", "below", 45)]},
    },
    {
        "strategy_id": "darvas_box_breakout_v1",
        "name": "Darvas Box Breakout",
        "universe": {"min_price": 50, "stage": "STAGE_2"},
        "entry": {
            "all": [
                _rule("stage", "eq", "STAGE_2"),
                _rule("close", "above", "sma_50"),
                _rule("relative_strength", "gte", 70),
                _rule("volume_ratio_20d", "gte", 1.4),
            ]
        },
        "breakouts": {"timeframe": "daily", "all": [_rule("close", "above", "sma_50")]},
        "volume": {"timeframe": "daily", "all": [_rule("volume_ratio_20d", "gte", 1.4)]},
        "risk": _atr_risk(multiple=2.0, risk_per_trade_pct=0.75, max_position_pct=8.0),
        "add_rules": [],
        "exit": {
            "any": [
                _rule("close", "below", "sma_50"),
                _rule("relative_strength", "below", 55),
                _rule("trailing_stop", "gte", 1),
            ]
        },
    },
    {
        "strategy_id": "mean_reversion_uptrend_v1",
        "name": "Mean Reversion In Uptrend",
        "universe": {"min_price": 50},
        "entry": {
            "all": [
                _rule("close", "above", "sma_200"),
                _rule("sma_50", "above", "sma_200"),
                _rule("close", "below", "sma_20"),
                _rule("rsi_14", "between", [30, 45]),
            ]
        },
        "trend_filters": {
            "timeframe": "daily",
            "all": [_rule("close", "above", "sma_200"), _rule("sma_50", "above", "sma_200")],
        },
        "pullbacks": {
            "timeframe": "daily",
            "all": [_rule("close", "below", "sma_20"), _rule("rsi_14", "between", [30, 45])],
        },
        "risk": _atr_risk(multiple=1.5, risk_per_trade_pct=0.5, max_position_pct=6.0),
        "add_rules": [],
        "exit": {"any": [_rule("close", "above", "sma_20"), _rule("close", "below", "sma_50")]},
    },
    {
        "strategy_id": "minervini_trend_template_v1",
        "name": "Minervini Trend Template",
        "universe": {"stage": "STAGE_2", "min_price": 50},
        "entry": {
            "all": [
                _rule("stage", "eq", "STAGE_2"),
                _rule("close", "above", "sma_50"),
                _rule("sma_50", "above", "sma_100"),
            ]
        },
        "stage_2": {"timeframe": "daily", "all": [_rule("stage", "eq", "STAGE_2")]},
        "trend_filters": {
            "timeframe": "daily",
            "all": [
                _rule("close", "above", "sma_50"),
                _rule("sma_50", "above", "sma_200"),
                _rule("relative_strength", "gte", 80),
            ],
        },
        "fundamentals": {
            "all": [
                _rule("eps_growth_pct", "gte", 20),
                _rule("sales_growth_pct", "gte", 15),
                _rule("roe_pct", "gte", 15),
            ]
        },
        "volume": {"timeframe": "daily", "all": [_rule("volume_ratio_20d", "gte", 1.2)]},
        "risk": _atr_risk(multiple=2.0, risk_per_trade_pct=1.0, max_position_pct=10.0),
        "add_rules": [
            {
                "kind": "trend_add",
                "indicator": "close",
                "operator": "above",
                "value": "sma_20",
                "size_pct": 4.0,
                "risk_per_trade_pct": 0.5,
                "timeframe": "daily",
            }
        ],
        "exit": {
            "any": [
                _rule("close", "below", "sma_50"),
                _rule("relative_strength", "below", 65),
                _rule("stage", "in", ["STAGE_3", "STAGE_4"]),
            ]
        },
    },
]
