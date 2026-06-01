"""Deterministic Coder / Quant agent for strategy-build requests."""

from __future__ import annotations

import json
from typing import Any, Callable

import pandas as pd
from backtesting.engine import compute_stage2_features
from backtesting.strategy_council.dsl import compile_strategy_proposal
from backtesting.strategy_council.runner import run_strategy_spec_on_split
from backtesting.strategy_council.splits import build_time_splits
from backtesting.strategy_council.types import BacktestSliceResult, StrategySpec

from terminal.research_council.schemas import StrategyBuildRequest, StrategyBuildResult


WHITELISTED_FAMILIES = {
    "stage2_breakout",
    "supertrend_continuation",
    "rsi_pullback_stage2",
    "fifty_two_week_high",
    "vcp_breakout",
    "earnings_momentum",
}
ASSUMPTIONS = [
    "time-ordered train/validation/test split",
    "test split locked until strategy commit",
    "minimum 25 bps round-trip transaction cost",
]
METRIC_KEYS = ("trade_count", "win_rate", "return_pct", "sharpe", "max_drawdown_pct", "profit_factor")
STRATEGY_ID_BY_FAMILY = {
    "stage2_breakout": "stage2",
    "supertrend_continuation": "supertrend_continuation",
    "rsi_pullback_stage2": "rsi_pullback_stage2",
    "fifty_two_week_high": "52w_high",
    "vcp_breakout": "vcp",
    "earnings_momentum": "rule_composed",
}
RULES_BY_FAMILY = {
    "stage2_breakout": {
        "entry_rules": ["stage is Stage 2", "close breaks above recent resistance", "volume above 20 day average"],
        "exit_rules": ["close below 50 day moving average", "time stop at selected horizon"],
        "risk_rules": ["risk no more than 1 percent of capital", "research only next session fills"],
    },
    "supertrend_continuation": {
        "entry_rules": ["supertrend is bullish", "close above 20 day moving average"],
        "exit_rules": ["supertrend flips bearish", "time stop at selected horizon"],
        "risk_rules": ["risk no more than 1 percent of capital", "research only next session fills"],
    },
    "rsi_pullback_stage2": {
        "entry_rules": ["stage is Stage 2", "RSI pulls back then reclaims 50"],
        "exit_rules": ["RSI fails below 45", "time stop at selected horizon"],
        "risk_rules": ["risk no more than 1 percent of capital", "research only next session fills"],
    },
    "fifty_two_week_high": {
        "entry_rules": ["close within 2 percent of 52 week high", "relative strength is positive"],
        "exit_rules": ["close loses breakout level", "time stop at selected horizon"],
        "risk_rules": ["risk no more than 1 percent of capital", "research only next session fills"],
    },
    "vcp_breakout": {
        "entry_rules": ["volatility contraction pattern resolves upward", "volume confirms breakout"],
        "exit_rules": ["close below pivot support", "time stop at selected horizon"],
        "risk_rules": ["risk no more than 1 percent of capital", "research only next session fills"],
    },
    "earnings_momentum": {
        "entry_rules": ["latest earnings growth is positive", "price confirms post result momentum"],
        "exit_rules": ["momentum confirmation fails", "time stop at selected horizon"],
        "risk_rules": ["risk no more than 1 percent of capital", "research only next session fills"],
    },
}
AI_STRATEGY_SCHEMA = {
    "type": "object",
    "required": ["strategy_family", "horizon_days", "entry_rules", "exit_rules", "risk_rules"],
    "properties": {
        "strategy_family": {"type": "string", "enum": sorted(WHITELISTED_FAMILIES)},
        "horizon_days": {"type": "integer", "enum": [5, 10, 20]},
        "entry_rules": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "exit_rules": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "risk_rules": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "required_features": {"type": "array", "items": {"type": "string"}},
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "limitations": {"type": "array", "items": {"type": "string"}},
        "thesis": {"type": "string"},
        "use_test_split": {"type": "boolean"},
    },
    "additionalProperties": True,
}


class CoderQuantAgent:
    """Creates safe strategy-build requests and first-pass validation results."""

    name = "coder_quant"

    def __init__(
        self,
        *,
        llm_call: Callable[..., dict[str, Any]] | None = None,
        model: str | None = None,
        require_ai: bool = False,
    ) -> None:
        self.llm_call = llm_call
        self.model = model
        self.require_ai = require_ai

    def build_request(
        self,
        *,
        source_branch: str,
        hypothesis: str,
        strategy_family: str,
        required_features: list[str] | None = None,
        allowed_horizons: list[int] | None = None,
    ) -> StrategyBuildRequest:
        return StrategyBuildRequest(
            source_branch=source_branch,
            strategy_family=_normalized_family(strategy_family),
            hypothesis=hypothesis,
            required_features=list(required_features or []),
            allowed_horizons=list(allowed_horizons or [5, 10, 20]),
        )

    def evaluate_request(
        self,
        request: StrategyBuildRequest,
        *,
        backtest_summary: dict[str, Any] | None = None,
    ) -> StrategyBuildResult:
        family = _normalized_family(request.strategy_family)
        if family not in WHITELISTED_FAMILIES:
            return StrategyBuildResult(
                request=request,
                verdict="UNTESTABLE",
                metrics={
                    "trade_count": 0,
                    "splits": {},
                    "assumptions": ASSUMPTIONS,
                },
                limitations=[f"strategy family {request.strategy_family!r} is not whitelisted"],
            )
        metrics = _metrics_from_summary(backtest_summary or {})
        limitations = _limitations(metrics)
        verdict = _verdict(metrics=metrics, limitations=limitations)
        return StrategyBuildResult(
            request=request,
            verdict=verdict,
            metrics=metrics,
            limitations=limitations,
        )

    def to_strategy_spec(self, request: StrategyBuildRequest) -> StrategySpec:
        family = _normalized_family(request.strategy_family)
        if family not in WHITELISTED_FAMILIES:
            raise ValueError(f"strategy family {request.strategy_family!r} is not whitelisted")
        horizon = int((request.allowed_horizons or [5])[0])
        strategy_id = STRATEGY_ID_BY_FAMILY[family]
        rules = RULES_BY_FAMILY[family]
        proposal = {
            "strategy_id": strategy_id,
            "horizon_days": horizon,
            "entry_rules": rules["entry_rules"],
            "exit_rules": rules["exit_rules"],
            "risk_rules": rules["risk_rules"],
            "thesis": request.hypothesis,
            "params": {
                "source_branch": request.source_branch,
                "strategy_family": family,
                "required_features": list(request.required_features),
                "split_policy": request.split_policy,
                "test_split_locked": True,
            },
            "origin": "research_council",
        }
        return compile_strategy_proposal(
            proposal,
            allowed_strategies=("stage2", "supertrend_continuation", "rsi_pullback_stage2", "52w_high", "vcp", "rule_composed"),
            allowed_horizons=tuple(request.allowed_horizons or [5, 10, 20]),
        )

    def propose_strategy_spec(
        self,
        request: StrategyBuildRequest,
        *,
        evidence: dict[str, Any] | None = None,
    ) -> StrategySpec:
        response = self._call_ai_strategy_designer(request, evidence=evidence or {})
        _guard_ai_proposal(response)
        family = _normalized_family(response.get("strategy_family") or request.strategy_family)
        if family not in WHITELISTED_FAMILIES:
            raise ValueError(f"strategy family {family!r} is not whitelisted")
        horizon = int(response.get("horizon_days") or (request.allowed_horizons or [5])[0])
        proposal = {
            "strategy_id": STRATEGY_ID_BY_FAMILY[family],
            "horizon_days": horizon,
            "entry_rules": response.get("entry_rules"),
            "exit_rules": response.get("exit_rules"),
            "risk_rules": response.get("risk_rules"),
            "thesis": str(response.get("thesis") or request.hypothesis),
            "params": {
                "ai_driven": True,
                "source_branch": request.source_branch,
                "strategy_family": family,
                "required_features": list(response.get("required_features") or request.required_features),
                "assumptions": list(response.get("assumptions") or []),
                "limitations": list(response.get("limitations") or []),
                "split_policy": request.split_policy,
                "test_split_locked": True,
            },
            "origin": "ai_coder_quant",
        }
        return compile_strategy_proposal(
            proposal,
            allowed_strategies=("stage2", "supertrend_continuation", "rsi_pullback_stage2", "52w_high", "vcp", "rule_composed"),
            allowed_horizons=tuple(request.allowed_horizons or [5, 10, 20]),
        )

    def try_propose_strategy_spec(
        self,
        request: StrategyBuildRequest,
        *,
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            return {"ok": True, "spec": self.propose_strategy_spec(request, evidence=evidence)}
        except RuntimeError as exc:
            return {"ok": False, "error": "llm_unavailable", "message": str(exc)}
        except PermissionError as exc:
            return {"ok": False, "error": "test_split_locked", "message": str(exc)}
        except Exception as exc:
            return {"ok": False, "error": "invalid_ai_strategy_proposal", "message": str(exc)}

    def run_train_validation(
        self,
        request: StrategyBuildRequest,
        eod_data: pd.DataFrame,
        *,
        initial_capital: float = 100000.0,
        validation_from: str | None = None,
        test_from: str | None = None,
        include_test: bool = False,
    ) -> dict[str, Any]:
        if include_test:
            return {
                "ok": False,
                "error": "test_split_locked",
                "message": "test split is locked until strategy commit",
            }
        if self.require_ai or self.llm_call is not None:
            proposed = self.try_propose_strategy_spec(request)
            if not proposed.get("ok"):
                return proposed
            spec = proposed["spec"]
        else:
            spec = self.to_strategy_spec(request)
        split_source = _prepare_backtest_frame(eod_data, spec)
        splits = build_time_splits(split_source, validation_from=validation_from, test_from=test_from)
        backtest_results = {
            split: run_strategy_spec_on_split(
                frame,
                spec,
                split_name=split,
                initial_capital=initial_capital,
            )
            for split, frame in splits.items()
            if split in {"train", "validation"}
        }
        unsupported_strategy = _unsupported_strategy(backtest_results)
        if unsupported_strategy:
            return {
                "ok": False,
                "error": "unsupported_strategy",
                "message": f"strategy {unsupported_strategy} is not supported by the backtest runner",
            }
        summary = {split: _summary_from_backtest(result) for split, result in backtest_results.items()}
        result = self.evaluate_request(request, backtest_summary=summary)
        return {
            "ok": True,
            "request": request,
            "spec": spec,
            "result": result,
            "backtest_results": backtest_results,
        }

    def sweep_train_validation(
        self,
        *,
        source_branch: str,
        hypothesis: str,
        eod_data: pd.DataFrame,
        strategy_families: list[str] | None = None,
        horizons: list[int] | None = None,
        option_grid: list[tuple[str, int]] | None = None,
        initial_capital: float = 100000.0,
    ) -> dict[str, Any]:
        families = [_normalized_family(item) for item in (strategy_families or sorted(WHITELISTED_FAMILIES))]
        allowed_horizons = [int(item) for item in (horizons or [5, 10, 20])]
        grid = option_grid or [(family, horizon) for family in families for horizon in allowed_horizons]
        ranked_options: list[dict[str, Any]] = []
        untestable: list[dict[str, Any]] = []
        ai_unavailable_message: str | None = None

        for raw_family, horizon in grid:
            family = _normalized_family(raw_family)
            request = self.build_request(
                source_branch=source_branch,
                hypothesis=hypothesis,
                strategy_family=family,
                allowed_horizons=[int(horizon)],
            )
            if family not in WHITELISTED_FAMILIES:
                untestable.append(
                    {
                        "request": request,
                        "result": self.evaluate_request(request),
                        "limitations": [f"strategy family {family!r} is not whitelisted"],
                    }
                )
                continue
            if ai_unavailable_message and (self.require_ai or self.llm_call is not None):
                untestable.append(
                    {
                        "request": request,
                        "error": "llm_unavailable_skipped",
                        "message": ai_unavailable_message,
                    }
                )
                continue
            output = self.run_train_validation(
                request,
                eod_data,
                initial_capital=initial_capital,
                include_test=False,
            )
            if not output.get("ok"):
                if output.get("error") == "llm_unavailable":
                    ai_unavailable_message = str(output.get("message") or "LLM unavailable")
                untestable.append({"request": request, "error": output.get("error"), "message": output.get("message")})
                continue
            ranked_options.append(
                {
                    "request": request,
                    "spec": output["spec"],
                    "result": output["result"],
                    "backtest_results": output["backtest_results"],
                    "symbol_attribution": _symbol_attribution(output["backtest_results"]),
                    "rank_score": _rank_score(output["result"]),
                }
            )

        ranked_options.sort(key=lambda item: item["rank_score"], reverse=True)
        return {
            "ok": True,
            "best": ranked_options[0] if ranked_options else None,
            "ranked_options": ranked_options,
            "untestable": untestable,
            "routes_tested": len(ranked_options),
            "routes_untestable": len(untestable),
        }

    def format_evidence_for_llm(self, evidence: dict, mode_profile: object | None = None) -> str:
        return json.dumps({"strategy_build": evidence.get("strategy_build")}, default=str)

    def _call_ai_strategy_designer(self, request: StrategyBuildRequest, *, evidence: dict[str, Any]) -> dict[str, Any]:
        call = self.llm_call or _default_llm_call()
        return call(
            system=_ai_system_prompt(),
            user=json.dumps(_ai_user_payload(request, evidence), default=str),
            schema=AI_STRATEGY_SCHEMA,
            model=self.model,
        )


def _metrics_from_summary(summary: dict[str, Any]) -> dict[str, Any]:
    train = _clean_split(summary.get("train") or {})
    validation = _clean_split(summary.get("validation") or {})
    trade_count = int(train.get("trade_count") or 0) + int(validation.get("trade_count") or 0)
    return {
        "trade_count": trade_count,
        "splits": {
            "train": train,
            "validation": validation,
        },
        "validation_pass": _validation_pass(validation),
        "assumptions": ASSUMPTIONS,
    }


def _prepare_backtest_frame(eod_data: pd.DataFrame, spec: StrategySpec) -> pd.DataFrame:
    if spec.strategy_id != "stage2":
        return eod_data
    required = {"stage", "relative_strength", "sma_50", "sma_150", "sma_200"}
    if required.issubset(set(eod_data.columns)):
        return eod_data
    return compute_stage2_features(eod_data)


def _unsupported_strategy(backtest_results: dict[str, BacktestSliceResult]) -> str | None:
    for result in backtest_results.values():
        unsupported = (result.metrics or {}).get("unsupported_strategy")
        if unsupported:
            return str(unsupported)
    return None


def _default_llm_call() -> Callable[..., dict[str, Any]]:
    from terminal.research_council.llm_client import call_llm_json

    return call_llm_json


def _ai_system_prompt() -> str:
    return (
        "You are Coder Quant, an AI strategy design agent for Indian equity research. "
        "Return JSON only matching the supplied schema. Design bounded, auditable rules; "
        "do not write Python, SQL, shell commands, or executable code. Use only train and "
        "validation evidence. The held-out test split is locked until strategy commit; "
        "do not request, inspect, infer, or reference test split results."
    )


def _ai_user_payload(request: StrategyBuildRequest, evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "task": "propose_strategy_spec",
        "request": request.to_dict(),
        "allowed_strategy_families": sorted(WHITELISTED_FAMILIES),
        "allowed_horizons": list(request.allowed_horizons or [5, 10, 20]),
        "evidence": evidence,
        "requirements": [
            "rules must be plain declarative text",
            "do not ask for test split data",
            "do not calculate backtest metrics",
            "include assumptions and limitations",
        ],
    }


def _guard_ai_proposal(proposal: dict[str, Any]) -> None:
    if proposal.get("use_test_split") is True:
        raise PermissionError("test split is locked until strategy commit")
    split_text = json.dumps(
        {
            "splits": proposal.get("splits"),
            "data_splits": proposal.get("data_splits"),
            "requested_data": proposal.get("requested_data"),
        },
        default=str,
    ).lower()
    if "test" in split_text:
        raise PermissionError("test split is locked until strategy commit")


def _normalized_family(strategy_family: str) -> str:
    return str(strategy_family or "").strip().lower().replace("-", "_")


def _summary_from_backtest(result: BacktestSliceResult) -> dict[str, Any]:
    metrics = dict(result.metrics or {})
    return {
        "trade_count": int(result.trade_count or metrics.get("trade_count") or 0),
        "return_pct": metrics.get("return_pct", metrics.get("total_return_pct")),
        "sharpe": metrics.get("sharpe"),
        "win_rate": metrics.get("win_rate"),
        "max_drawdown_pct": metrics.get("max_drawdown_pct"),
        "profit_factor": metrics.get("profit_factor"),
    }


def _symbol_attribution(backtest_results: dict[str, BacktestSliceResult]) -> dict[str, dict[str, Any]]:
    by_symbol: dict[str, dict[str, Any]] = {}
    for split in ("train", "validation"):
        result = backtest_results.get(split)
        if not result:
            continue
        split_attribution = (result.metrics or {}).get("symbol_attribution") or {}
        for raw_symbol, metrics in split_attribution.items():
            symbol = str(raw_symbol).upper()
            row = by_symbol.setdefault(symbol, {"symbol": symbol, "total_trade_count": 0})
            trade_count = int(metrics.get("trade_count") or 0)
            row[f"{split}_trade_count"] = trade_count
            row[f"{split}_return_pct"] = metrics.get("return_pct")
            row[f"{split}_sharpe"] = metrics.get("sharpe")
            row["total_trade_count"] = int(row.get("total_trade_count") or 0) + trade_count
    return by_symbol


def _rank_score(result: StrategyBuildResult) -> float:
    metrics = result.metrics or {}
    splits = metrics.get("splits") or {}
    validation = splits.get("validation") or {}
    verdict_bonus = {
        "SUPPORTED": 1000.0,
        "AMBIGUOUS": 100.0,
        "REFUTED": 0.0,
        "UNTESTABLE": -1000.0,
    }.get(result.verdict, 0.0)
    validation_return = _float_metric(validation.get("return_pct"))
    validation_sharpe = _float_metric(validation.get("sharpe"))
    validation_trades = _float_metric(validation.get("trade_count"))
    total_trades = _float_metric(metrics.get("trade_count"))
    return verdict_bonus + validation_return * 10.0 + validation_sharpe * 25.0 + validation_trades + total_trades * 0.1


def _float_metric(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _clean_split(split: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key in METRIC_KEYS:
        value = split.get(key)
        if value is not None:
            cleaned[key] = value
    cleaned.setdefault("trade_count", 0)
    return cleaned


def _validation_pass(validation: dict[str, Any]) -> bool:
    if int(validation.get("trade_count") or 0) <= 0:
        return False
    if float(validation.get("return_pct") or 0) <= 0:
        return False
    if float(validation.get("sharpe") or 0) < 0.5:
        return False
    return True


def _limitations(metrics: dict[str, Any]) -> list[str]:
    limitations: list[str] = []
    if int(metrics.get("trade_count") or 0) < 30:
        limitations.append("below 30 trades")
    if not metrics.get("validation_pass"):
        limitations.append("validation did not pass minimum return/sharpe gates")
    return limitations


def _verdict(*, metrics: dict[str, Any], limitations: list[str]) -> str:
    if int(metrics.get("trade_count") or 0) < 30:
        return "AMBIGUOUS"
    if not metrics.get("validation_pass"):
        return "REFUTED"
    if limitations:
        return "AMBIGUOUS"
    return "SUPPORTED"
