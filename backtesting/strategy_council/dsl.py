"""Constrained strategy-spec compiler for LLM strategist proposals."""

from __future__ import annotations

from typing import Any

from backtesting.strategy_council.types import StrategySpec


_FORBIDDEN_TOKENS = ("eval", "exec", "__", "import", "open(", "subprocess", "os.", "sys.")


def _clean_rules(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError(f"{field} must be a non-empty list")
    rules = tuple(str(item).strip() for item in value if str(item).strip())
    if not rules:
        raise ValueError(f"{field} must contain at least one rule")
    lowered = " ".join(rules).lower()
    if any(token in lowered for token in _FORBIDDEN_TOKENS):
        raise ValueError(f"{field} contains forbidden executable content")
    return rules


def compile_strategy_proposal(
    proposal: dict[str, Any],
    *,
    allowed_strategies: tuple[str, ...],
    allowed_horizons: tuple[int, ...],
) -> StrategySpec:
    strategy_id = str(proposal.get("strategy_id", "")).strip().lower().replace("-", "_")
    if strategy_id not in allowed_strategies:
        raise ValueError(f"Strategy '{strategy_id}' is not allowed")
    horizon = int(proposal.get("horizon_days", 0))
    if horizon not in allowed_horizons:
        raise ValueError(f"Horizon '{horizon}' is not allowed")
    thesis = str(proposal.get("thesis", "")).strip()
    if not thesis:
        raise ValueError("thesis is required")
    return StrategySpec(
        strategy_id=strategy_id,
        horizon_days=horizon,
        entry_rules=_clean_rules(proposal.get("entry_rules"), "entry_rules"),
        exit_rules=_clean_rules(proposal.get("exit_rules"), "exit_rules"),
        risk_rules=_clean_rules(proposal.get("risk_rules"), "risk_rules"),
        thesis=thesis,
        params=dict(proposal.get("params") or {}),
        origin=str(proposal.get("origin") or "llm"),
    )
