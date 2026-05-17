"""Strategy Council strategist and critic interfaces.

Production LLM implementations can satisfy these Protocols. The rule-based
fallbacks keep the council deterministic and fully testable.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Protocol

from backtesting.strategy_council.dsl import compile_strategy_proposal
from backtesting.strategy_council.types import (
    BacktestSliceResult,
    CouncilConfig,
    Critique,
    EvidencePack,
    StrategySpec,
)


class Strategist(Protocol):
    def propose(
        self,
        *,
        evidence: EvidencePack,
        config: CouncilConfig,
        prior_feedback: tuple[Critique, ...],
    ) -> tuple[StrategySpec, ...]:
        ...


class Critic(Protocol):
    def critique(
        self,
        *,
        candidates: tuple[StrategySpec, ...],
        train_results: tuple[BacktestSliceResult, ...],
        validation_results: tuple[BacktestSliceResult, ...],
    ) -> Critique:
        ...


class RuleBasedStrategist:
    def propose(
        self,
        *,
        evidence: EvidencePack,
        config: CouncilConfig,
        prior_feedback: tuple[Critique, ...],
    ) -> tuple[StrategySpec, ...]:
        proposals: list[StrategySpec] = []
        feedback_text = "; ".join(issue for critique in prior_feedback for issue in critique.issues)
        for strategy_id in config.allowed_strategies:
            for horizon in config.horizons:
                proposals.append(
                    StrategySpec(
                        strategy_id=strategy_id,
                        horizon_days=horizon,
                        entry_rules=(f"{strategy_id} entry confirmation",),
                        exit_rules=(f"{strategy_id} exit or horizon {horizon} days",),
                        risk_rules=("max_position_pct=10", "next_open_execution", "research_only"),
                        thesis=(
                            f"{strategy_id} candidate for {config.symbol} over {horizon} trading days."
                            + (f" Prior critic feedback: {feedback_text}" if feedback_text else "")
                        ),
                        origin="deterministic_fallback",
                    )
                )
                if len(proposals) >= config.max_candidates:
                    return tuple(proposals)
        return tuple(proposals)


class JSONLLMStrategist:
    """Structured LLM strategist adapter.

    The injected `llm_call` keeps the production API boundary narrow and lets
    tests use deterministic fakes. It must return a dict with a `strategies`
    list that can be compiled into constrained StrategySpec objects.
    """

    def __init__(self, llm_call: Callable[[str, str], dict[str, Any]]):
        self.llm_call = llm_call

    def propose(
        self,
        *,
        evidence: EvidencePack,
        config: CouncilConfig,
        prior_feedback: tuple[Critique, ...],
    ) -> tuple[StrategySpec, ...]:
        system = (
            "You are a senior Indian equity strategist. Return JSON only. "
            "Propose bounded EOD research strategies; do not write Python code."
        )
        prompt = json.dumps(
            {
                "symbol": config.symbol,
                "horizons": config.horizons,
                "allowed_strategies": config.allowed_strategies,
                "max_candidates": config.max_candidates,
                "evidence": {
                    "as_of": evidence.as_of,
                    "technical": evidence.technical,
                    "fundamental": evidence.fundamental,
                    "market": evidence.market,
                    "missing": evidence.missing,
                    "freshness": evidence.freshness,
                },
                "prior_feedback": [
                    {
                        "critic": item.critic,
                        "verdict": item.verdict,
                        "issues": list(item.issues),
                        "required_changes": list(item.required_changes),
                    }
                    for item in prior_feedback
                ],
                "schema": {
                    "strategies": [
                        {
                            "strategy_id": "stage2",
                            "horizon_days": 10,
                            "entry_rules": ["string"],
                            "exit_rules": ["string"],
                            "risk_rules": ["string"],
                            "thesis": "string",
                            "params": {},
                        }
                    ]
                },
            },
            default=str,
        )
        response = self.llm_call(system, prompt)
        raw = response.get("strategies") or []
        specs: list[StrategySpec] = []
        for proposal in raw[: config.max_candidates]:
            try:
                specs.append(
                    compile_strategy_proposal(
                        dict(proposal),
                        allowed_strategies=config.allowed_strategies,
                        allowed_horizons=config.horizons,
                    )
                )
            except Exception:
                continue
        if specs:
            return tuple(specs)
        return RuleBasedStrategist().propose(evidence=evidence, config=config, prior_feedback=prior_feedback)


class JSONLLMCritic:
    """Structured LLM critic adapter for data/leakage or market/risk review."""

    def __init__(self, critic_name: str, llm_call: Callable[[str, str], dict[str, Any]]):
        self.critic_name = critic_name
        self.llm_call = llm_call

    def critique(
        self,
        *,
        candidates: tuple[StrategySpec, ...],
        train_results: tuple[BacktestSliceResult, ...],
        validation_results: tuple[BacktestSliceResult, ...],
    ) -> Critique:
        system = (
            f"You are the {self.critic_name} critic in an EOD strategy council. "
            "Return JSON only. Do not use or ask for test-period data."
        )
        prompt = json.dumps(
            {
                "candidates": [candidate.__dict__ for candidate in candidates],
                "train_results": [result.__dict__ for result in train_results],
                "validation_results": [result.__dict__ for result in validation_results],
                "schema": {
                    "verdict": "accept|revise|reject",
                    "issues": ["string"],
                    "required_changes": ["string"],
                    "confidence_delta": 0.0,
                },
            },
            default=str,
        )
        response = self.llm_call(system, prompt)
        verdict = str(response.get("verdict") or "revise").lower()
        if verdict not in {"accept", "revise", "reject"}:
            verdict = "revise"
        issues = tuple(str(item) for item in (response.get("issues") or []))
        required_changes = tuple(str(item) for item in (response.get("required_changes") or []))
        try:
            confidence_delta = float(response.get("confidence_delta") or 0.0)
        except (TypeError, ValueError):
            confidence_delta = 0.0
        return Critique(
            critic=self.critic_name,
            verdict=verdict,
            issues=issues,
            required_changes=required_changes,
            confidence_delta=confidence_delta,
        )


def _openai_json_call(model: str) -> Callable[[str, str], dict[str, Any]]:
    def _call(system: str, prompt: str) -> dict[str, Any]:
        from openai import OpenAI

        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        content = resp.choices[0].message.content or "{}"
        return json.loads(content)

    return _call


def build_default_agents(use_llm: bool = True):
    """Return production strategist/critics with deterministic fallback."""
    if use_llm and os.environ.get("OPENAI_API_KEY"):
        model = os.environ.get("AGENT_ADDA_STRATEGY_COUNCIL_MODEL", "gpt-4o")
        call = _openai_json_call(model)
        return (
            JSONLLMStrategist(call),
            (
                JSONLLMCritic("data_leakage", call),
                JSONLLMCritic("market_risk", call),
            ),
        )
    return (
        RuleBasedStrategist(),
        (RuleBasedDataLeakageCritic(), RuleBasedRiskCritic()),
    )


class RuleBasedDataLeakageCritic:
    def critique(
        self,
        *,
        candidates: tuple[StrategySpec, ...],
        train_results: tuple[BacktestSliceResult, ...],
        validation_results: tuple[BacktestSliceResult, ...],
    ) -> Critique:
        issues: list[str] = []
        if not candidates:
            issues.append("No candidate strategies were proposed.")
        if any(result.split == "test" for result in train_results + validation_results):
            issues.append("Test split appeared before final lock.")
        verdict = "revise" if issues else "accept"
        return Critique(
            critic="data_leakage",
            verdict=verdict,
            issues=tuple(issues),
            required_changes=("hide test metrics until final lock",) if issues else (),
        )


class RuleBasedRiskCritic:
    def critique(
        self,
        *,
        candidates: tuple[StrategySpec, ...],
        train_results: tuple[BacktestSliceResult, ...],
        validation_results: tuple[BacktestSliceResult, ...],
    ) -> Critique:
        all_results = train_results + validation_results
        issues: list[str] = []
        if not all_results or all(result.trade_count == 0 for result in all_results):
            issues.append("Trade count is too low for a reliable conclusion.")
        validation_returns = [
            result.metrics.get("total_return_pct")
            for result in validation_results
            if isinstance(result.metrics.get("total_return_pct"), (int, float))
        ]
        if validation_returns and max(validation_returns) < 0:
            issues.append("All validation returns are negative.")
        verdict = "revise" if issues else "accept"
        return Critique(
            critic="market_risk",
            verdict=verdict,
            issues=tuple(issues),
            required_changes=("tighten filters or return NO_TRADE",) if issues else (),
        )
