"""Atomic rule registry, RuleComposer, and CompositeStrategist.

This module gives the Strategy Council a deterministic, fully-auditable way to
generate candidate :class:`StrategySpec` objects by combining a small library of
primitive entry/exit/risk *atoms*.

Design goals
------------

* Atoms are described by static strings that contain **no executable tokens** so
  every composed spec round-trips through :func:`compile_strategy_proposal`.
* The composer never evaluates atom text — atom ids are stored in
  ``StrategySpec.params`` and looked up against this module's registry at
  execution time.
* Generation is deterministic given a seed, enabling reproducible council runs.
* Outputs are valid drop-in replacements for the existing rule-based
  strategist; both can coexist via :class:`CompositeStrategist`.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from itertools import product
from typing import Any, Mapping, Sequence

from backtesting.strategy_council.dsl import compile_strategy_proposal
from backtesting.strategy_council.types import (
    CouncilConfig,
    Critique,
    EvidencePack,
    StrategySpec,
)


@dataclass(frozen=True)
class AtomicRule:
    """A primitive entry/exit/risk rule.

    ``description`` is the human-readable rule text that ends up in
    :class:`StrategySpec`. It must remain free of DSL forbidden tokens.
    """

    rule_id: str
    parameters: Mapping[str, Any]
    description: str


# ---------------------------------------------------------------------------
# Registries
# ---------------------------------------------------------------------------

ENTRY_RULES: dict[str, AtomicRule] = {
    "ema_bullish": AtomicRule(
        rule_id="ema_bullish",
        parameters={"period": 20},
        description="close above EMA period 20",
    ),
    "rsi_oversold": AtomicRule(
        rule_id="rsi_oversold",
        parameters={"period": 14, "threshold": 30},
        description="RSI period 14 below 30",
    ),
    "volume_spike": AtomicRule(
        rule_id="volume_spike",
        parameters={"period": 20, "multiplier": 1.5},
        description="volume above 1.5 times SMA period 20",
    ),
    "macd_cross": AtomicRule(
        rule_id="macd_cross",
        parameters={"fast": 12, "slow": 26, "signal": 9},
        description="MACD line above signal line on fast 12 slow 26 signal 9",
    ),
}


EXIT_RULES: dict[str, AtomicRule] = {
    "profit_target": AtomicRule(
        rule_id="profit_target",
        parameters={"pct": 2.0},
        description="exit on plus 2 percent profit",
    ),
    "stop_loss": AtomicRule(
        rule_id="stop_loss",
        parameters={"pct": 1.0},
        description="exit on minus 1 percent loss",
    ),
    "time_stop": AtomicRule(
        rule_id="time_stop",
        parameters={"days": 5},
        description="exit after 5 trading days",
    ),
    "trailing_stop": AtomicRule(
        rule_id="trailing_stop",
        parameters={"pct": 1.5},
        description="exit on minus 1.5 percent from running high",
    ),
}


RISK_RULES: dict[str, AtomicRule] = {
    "position_size": AtomicRule(
        rule_id="position_size",
        parameters={"pct_capital": 2.0},
        description="risk 2 percent of capital per trade",
    ),
    "max_open": AtomicRule(
        rule_id="max_open",
        parameters={"count": 3},
        description="cap concurrent positions at 3",
    ),
    "correlate_filter": AtomicRule(
        rule_id="correlate_filter",
        parameters={"threshold": 0.7},
        description="avoid positions correlated above 0.7",
    ),
    "research_only": AtomicRule(
        rule_id="research_only",
        parameters={},
        description="research only and next open fills",
    ),
}


COMPOSED_STRATEGY_ID = "rule_composed"


# ---------------------------------------------------------------------------
# Composer
# ---------------------------------------------------------------------------


class RuleComposer:
    """Combines atomic rules into validated :class:`StrategySpec` objects."""

    def __init__(
        self,
        entry_rules: Mapping[str, AtomicRule] | None = None,
        exit_rules: Mapping[str, AtomicRule] | None = None,
        risk_rules: Mapping[str, AtomicRule] | None = None,
    ) -> None:
        self._entry = dict(entry_rules or ENTRY_RULES)
        self._exit = dict(exit_rules or EXIT_RULES)
        self._risk = dict(risk_rules or RISK_RULES)

    def compose(
        self,
        *,
        entry_atoms: Sequence[str],
        exit_atoms: Sequence[str],
        risk_atoms: Sequence[str],
        horizon_days: int,
        thesis: str,
        strategy_id: str = COMPOSED_STRATEGY_ID,
        allowed_strategies: Sequence[str] = (COMPOSED_STRATEGY_ID,),
        allowed_horizons: Sequence[int] = (5, 10, 20),
        extra_params: Mapping[str, Any] | None = None,
    ) -> StrategySpec:
        entry = tuple(self._entry[a].description for a in entry_atoms if a in self._entry)
        exit_ = tuple(self._exit[a].description for a in exit_atoms if a in self._exit)
        risk = tuple(self._risk[a].description for a in risk_atoms if a in self._risk)
        if not entry:
            raise ValueError("RuleComposer requires at least one valid entry atom")
        if not exit_:
            raise ValueError("RuleComposer requires at least one valid exit atom")
        if not risk:
            risk = (self._risk["research_only"].description,)

        kept_entry = tuple(a for a in entry_atoms if a in self._entry)
        kept_exit = tuple(a for a in exit_atoms if a in self._exit)
        kept_risk = tuple(a for a in risk_atoms if a in self._risk)

        params: dict[str, Any] = {
            "entry_atoms": list(kept_entry),
            "exit_atoms": list(kept_exit),
            "risk_atoms": list(kept_risk),
            "entry_atom_params": {a: dict(self._entry[a].parameters) for a in kept_entry},
            "exit_atom_params": {a: dict(self._exit[a].parameters) for a in kept_exit},
            "risk_atom_params": {a: dict(self._risk[a].parameters) for a in kept_risk},
        }
        if extra_params:
            params.update(dict(extra_params))

        proposal = {
            "strategy_id": strategy_id,
            "horizon_days": horizon_days,
            "entry_rules": list(entry),
            "exit_rules": list(exit_),
            "risk_rules": list(risk),
            "thesis": thesis,
            "params": params,
            "origin": "rule_composer",
        }
        return compile_strategy_proposal(
            proposal,
            allowed_strategies=tuple(allowed_strategies),
            allowed_horizons=tuple(allowed_horizons),
        )


# ---------------------------------------------------------------------------
# Candidate generation
# ---------------------------------------------------------------------------


def _default_thesis(
    *, symbol: str, horizon_days: int, entry: Sequence[str], exit_: Sequence[str]
) -> str:
    entry_text = ", ".join(entry) if entry else "none"
    exit_text = ", ".join(exit_) if exit_ else "none"
    return (
        f"Rule-composed candidate for {symbol} over {horizon_days} trading days. "
        f"Entry atoms: {entry_text}. Exit atoms: {exit_text}."
    )


def _allowed_strategies_for_composed(config: CouncilConfig) -> tuple[str, ...]:
    if COMPOSED_STRATEGY_ID in config.allowed_strategies:
        return config.allowed_strategies
    return tuple(config.allowed_strategies) + (COMPOSED_STRATEGY_ID,)


def generate_candidates_via_rules(
    config: CouncilConfig,
    *,
    method: str = "sampled",
    max_candidates: int | None = None,
    seed: int = 0,
    composer: RuleComposer | None = None,
    entry_choices: int = 2,
    exit_choices: int = 2,
    risk_choices: int = 1,
) -> tuple[StrategySpec, ...]:
    """Generate composed candidates.

    ``method`` is ``"sampled"`` (deterministic random combinations) or
    ``"exhaustive"`` (enumerate all combinations up to ``max_candidates``).
    """

    composer = composer or RuleComposer()
    limit = max_candidates if max_candidates is not None else config.max_candidates
    if limit <= 0:
        return ()
    allowed = _allowed_strategies_for_composed(config)
    horizons = tuple(config.horizons) or (10,)

    entry_atoms = sorted(ENTRY_RULES.keys())
    exit_atoms = sorted(EXIT_RULES.keys())
    risk_atoms = sorted(RISK_RULES.keys())

    candidates: list[StrategySpec] = []
    seen: set[tuple[Any, ...]] = set()

    def _add(entry: tuple[str, ...], exit_: tuple[str, ...], risk: tuple[str, ...], horizon: int) -> None:
        key = (horizon, entry, exit_, risk)
        if key in seen:
            return
        try:
            spec = composer.compose(
                entry_atoms=entry,
                exit_atoms=exit_,
                risk_atoms=risk,
                horizon_days=horizon,
                thesis=_default_thesis(
                    symbol=config.symbol, horizon_days=horizon, entry=entry, exit_=exit_
                ),
                allowed_strategies=allowed,
                allowed_horizons=horizons,
            )
        except ValueError:
            return
        seen.add(key)
        candidates.append(spec)

    if method == "exhaustive":
        for horizon in horizons:
            for entry_combo in _kcombos(entry_atoms, entry_choices):
                for exit_combo in _kcombos(exit_atoms, exit_choices):
                    for risk_combo in _kcombos(risk_atoms, max(risk_choices, 1)):
                        _add(entry_combo, exit_combo, risk_combo, horizon)
                        if len(candidates) >= limit:
                            return tuple(candidates)
        return tuple(candidates)

    if method != "sampled":
        raise ValueError(f"Unknown generation method: {method!r}")

    rng = random.Random(seed)
    attempts = 0
    max_attempts = max(limit * 20, 50)
    while len(candidates) < limit and attempts < max_attempts:
        attempts += 1
        horizon = rng.choice(horizons)
        entry = tuple(sorted(rng.sample(entry_atoms, k=min(entry_choices, len(entry_atoms)))))
        exit_ = tuple(sorted(rng.sample(exit_atoms, k=min(exit_choices, len(exit_atoms)))))
        risk = tuple(sorted(rng.sample(risk_atoms, k=min(max(risk_choices, 1), len(risk_atoms)))))
        _add(entry, exit_, risk, horizon)
    return tuple(candidates)


def _kcombos(items: Sequence[str], k: int) -> list[tuple[str, ...]]:
    from itertools import combinations

    k = max(1, min(k, len(items)))
    return [tuple(combo) for combo in combinations(items, k)]


# ---------------------------------------------------------------------------
# Composite strategist
# ---------------------------------------------------------------------------


@dataclass
class CompositeStrategist:
    """Blend an LLM (or rule-based) strategist with rule-composed candidates.

    ``llm_ratio`` is the fraction of ``config.max_candidates`` reserved for the
    inner strategist; the remainder is filled by :func:`generate_candidates_via_rules`.
    De-duplication preserves the inner strategist's order so existing tests that
    inspect deterministic-fallback origins remain stable.
    """

    inner: Any
    llm_ratio: float = 0.4
    method: str = "sampled"
    seed: int = 0
    composer: RuleComposer = field(default_factory=RuleComposer)

    def propose(
        self,
        *,
        evidence: EvidencePack,
        config: CouncilConfig,
        prior_feedback: tuple[Critique, ...],
    ) -> tuple[StrategySpec, ...]:
        max_total = max(config.max_candidates, 0)
        if max_total == 0:
            return ()

        ratio = min(max(self.llm_ratio, 0.0), 1.0)
        llm_quota = int(round(max_total * ratio))
        # Guarantee at least one rule-composed candidate when ratio < 1.
        if ratio < 1.0 and llm_quota >= max_total:
            llm_quota = max_total - 1
        rule_quota = max_total - llm_quota

        inner_proposals = tuple(
            self.inner.propose(evidence=evidence, config=config, prior_feedback=prior_feedback)
        )[:llm_quota]

        rule_proposals: tuple[StrategySpec, ...] = ()
        if rule_quota > 0:
            rule_proposals = generate_candidates_via_rules(
                config,
                method=self.method,
                max_candidates=rule_quota,
                seed=self.seed,
                composer=self.composer,
            )

        combined: list[StrategySpec] = []
        seen: set[tuple[Any, ...]] = set()
        for spec in (*inner_proposals, *rule_proposals):
            key = (
                spec.strategy_id,
                spec.horizon_days,
                tuple(spec.entry_rules),
                tuple(spec.exit_rules),
            )
            if key in seen:
                continue
            seen.add(key)
            combined.append(spec)
            if len(combined) >= max_total:
                break
        return tuple(combined)


__all__ = [
    "AtomicRule",
    "ENTRY_RULES",
    "EXIT_RULES",
    "RISK_RULES",
    "COMPOSED_STRATEGY_ID",
    "RuleComposer",
    "generate_candidates_via_rules",
    "CompositeStrategist",
]
