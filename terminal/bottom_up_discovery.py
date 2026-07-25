"""Bottom-up setup discovery schema and trial registry.

This module implements the first build slice of the Agent Adda bottom-up
discovery protocol: a declarative setup DSL, bounded candidate enumeration, a
chronological partition plan, and an auditable trial registry. It deliberately
does not run a backtest or compute significance; those later stages must consume
the registered candidate set so their multiple-testing denominator is honest.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _norm(value: Any, default: str = "-") -> str:
    text = str(value if value is not None else default).strip()
    return text if text else default


@dataclass(frozen=True)
class PrimitiveSpec:
    primitive_id: str
    family: str
    role: str
    parameters: dict[str, Any] = field(default_factory=dict)
    description: str = ""

    def __post_init__(self) -> None:
        if not _norm(self.primitive_id, ""):
            raise ValueError("primitive_id is required")
        if not _norm(self.family, ""):
            raise ValueError("family is required")
        if self.role not in {"trigger", "confirmation", "context_gate", "exit"}:
            raise ValueError("role must be trigger, confirmation, context_gate, or exit")

    def to_dict(self) -> dict[str, Any]:
        return {
            "primitive_id": self.primitive_id,
            "family": self.family,
            "role": self.role,
            "parameters": dict(sorted((self.parameters or {}).items())),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PrimitiveSpec":
        role = data.get("role")
        kwargs = dict(
            primitive_id=str(data.get("primitive_id") or ""),
            family=str(data.get("family") or ""),
            parameters=dict(data.get("parameters") or {}),
            description=str(data.get("description") or ""),
        )
        if role == "trigger":
            return TriggerSpec(**kwargs)
        if role == "context_gate":
            return ContextGateSpec(**kwargs)
        if role == "exit":
            return ExitSpec(**kwargs)
        return cls(role=str(role or ""), **kwargs)


class TriggerSpec(PrimitiveSpec):
    def __init__(self, primitive_id: str, family: str, parameters: dict[str, Any] | None = None, description: str = ""):
        super().__init__(primitive_id=primitive_id, family=family, role="trigger", parameters=parameters or {}, description=description)


class ContextGateSpec(PrimitiveSpec):
    def __init__(self, primitive_id: str, family: str, parameters: dict[str, Any] | None = None, description: str = ""):
        super().__init__(primitive_id=primitive_id, family=family, role="context_gate", parameters=parameters or {}, description=description)


class ExitSpec(PrimitiveSpec):
    def __init__(self, primitive_id: str, family: str, parameters: dict[str, Any] | None = None, description: str = ""):
        super().__init__(primitive_id=primitive_id, family=family, role="exit", parameters=parameters or {}, description=description)


@dataclass(frozen=True)
class SetupScope:
    symbol: str = "ALL"
    session_bucket: str = "any"
    vol_regime: str = "any"

    def to_dict(self) -> dict[str, str]:
        return {
            "symbol": _norm(self.symbol).upper(),
            "session_bucket": _norm(self.session_bucket).lower(),
            "vol_regime": _norm(self.vol_regime).lower(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SetupScope":
        return cls(
            symbol=str(data.get("symbol") or "ALL"),
            session_bucket=str(data.get("session_bucket") or "any"),
            vol_regime=str(data.get("vol_regime") or "any"),
        )


@dataclass(frozen=True)
class SetupSpec:
    trigger: PrimitiveSpec
    confirmations: tuple[PrimitiveSpec, ...]
    context_gates: tuple[PrimitiveSpec, ...]
    exit: PrimitiveSpec
    scope: SetupScope = field(default_factory=SetupScope)

    def __post_init__(self) -> None:
        object.__setattr__(self, "confirmations", tuple(sorted(self.confirmations, key=lambda item: item.primitive_id)))
        object.__setattr__(self, "context_gates", tuple(sorted(self.context_gates, key=lambda item: item.primitive_id)))
        self.validate()

    @property
    def condition_count(self) -> int:
        return len(self.confirmations) + len(self.context_gates)

    @property
    def candidate_id(self) -> str:
        raw = {
            "trigger": self.trigger.to_dict(),
            "confirmations": [item.to_dict() for item in self.confirmations],
            "context_gates": [item.to_dict() for item in self.context_gates],
            "exit": self.exit.to_dict(),
            "scope": self.scope.to_dict(),
        }
        digest = hashlib.sha1(_canonical_json(raw).encode("utf-8")).hexdigest()[:16]
        return f"setup_{digest}"

    def validate(self, *, max_conditions: int | None = None) -> None:
        if self.trigger.role != "trigger":
            raise ValueError("SetupSpec trigger must have role trigger")
        if self.exit.role != "exit":
            raise ValueError("SetupSpec exit must have role exit")
        bad_confirmations = [item.primitive_id for item in self.confirmations if item.role != "confirmation"]
        if bad_confirmations:
            raise ValueError(f"confirmations must have role confirmation: {bad_confirmations}")
        bad_gates = [item.primitive_id for item in self.context_gates if item.role != "context_gate"]
        if bad_gates:
            raise ValueError(f"context_gates must have role context_gate: {bad_gates}")
        if max_conditions is not None and self.condition_count > int(max_conditions):
            raise ValueError("setup complexity exceeds max_conditions")

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "trigger": self.trigger.to_dict(),
            "confirmations": [item.to_dict() for item in self.confirmations],
            "context_gates": [item.to_dict() for item in self.context_gates],
            "exit": self.exit.to_dict(),
            "scope": self.scope.to_dict(),
        }

    def canonical_dict(self) -> dict[str, Any]:
        out = self.to_dict()
        out.pop("candidate_id", None)
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SetupSpec":
        return cls(
            trigger=PrimitiveSpec.from_dict(data["trigger"]),
            confirmations=tuple(PrimitiveSpec.from_dict(item) for item in data.get("confirmations", [])),
            context_gates=tuple(PrimitiveSpec.from_dict(item) for item in data.get("context_gates", [])),
            exit=PrimitiveSpec.from_dict(data["exit"]),
            scope=SetupScope.from_dict(data.get("scope") or {}),
        )


@dataclass(frozen=True)
class DiscoverySearchSpace:
    triggers: tuple[PrimitiveSpec, ...]
    confirmations: tuple[PrimitiveSpec, ...]
    context_gates: tuple[PrimitiveSpec, ...]
    exits: tuple[PrimitiveSpec, ...]
    scopes: tuple[SetupScope, ...] = (SetupScope(),)
    allowed_confirmation_families: dict[str, tuple[str, ...]] = field(default_factory=dict)
    max_confirmations: int = 2
    max_context_gates: int = 1
    max_conditions: int = 3

    def generate_candidates(self) -> list[SetupSpec]:
        candidates: list[SetupSpec] = []
        seen: set[str] = set()
        for trigger in self.triggers:
            if trigger.role != "trigger":
                continue
            confirmations = [item for item in self.confirmations if self._confirmation_allowed(trigger, item)]
            confirmation_sets = _subsets(confirmations, max_items=self.max_confirmations)
            context_sets = _subsets([item for item in self.context_gates if item.role == "context_gate"], max_items=self.max_context_gates)
            for exit_spec in self.exits:
                if exit_spec.role != "exit":
                    continue
                for scope in self.scopes:
                    for confirmation_set in confirmation_sets:
                        for context_set in context_sets:
                            spec = SetupSpec(
                                trigger=trigger,
                                confirmations=tuple(confirmation_set),
                                context_gates=tuple(context_set),
                                exit=exit_spec,
                                scope=scope,
                            )
                            try:
                                spec.validate(max_conditions=self.max_conditions)
                            except ValueError:
                                continue
                            if spec.candidate_id not in seen:
                                seen.add(spec.candidate_id)
                                candidates.append(spec)
        return candidates

    def _confirmation_allowed(self, trigger: PrimitiveSpec, confirmation: PrimitiveSpec) -> bool:
        if confirmation.role != "confirmation":
            return False
        allowed = self.allowed_confirmation_families.get(trigger.family)
        if allowed is None:
            return True
        return confirmation.family in set(allowed)


def _subsets(items: list[PrimitiveSpec], *, max_items: int) -> list[tuple[PrimitiveSpec, ...]]:
    out: list[tuple[PrimitiveSpec, ...]] = [()]
    limit = max(0, min(int(max_items), len(items)))
    for size in range(1, limit + 1):
        out.extend(tuple(combo) for combo in combinations(items, size))
    return out


def default_eod_discovery_space(
    *,
    scopes: Iterable[SetupScope] | None = None,
    max_confirmations: int = 2,
    max_context_gates: int = 1,
    max_conditions: int = 3,
) -> DiscoverySearchSpace:
    """Bounded EOD taxonomy for the first bottom-up discovery registry.

    The primitives mirror the setup families already used in the EOD research
    reports, but keep discovery honest by generating only economically plausible
    trigger/confirmation combinations.
    """
    triggers: tuple[PrimitiveSpec, ...] = (
        TriggerSpec(
            primitive_id="breakout_20_volume",
            family="price_structure",
            parameters={"lookback": 20},
            description="close clears the prior 20-session high",
        ),
        TriggerSpec(
            primitive_id="breakout_50_volume",
            family="price_structure",
            parameters={"lookback": 50},
            description="close clears the prior 50-session high",
        ),
        TriggerSpec(
            primitive_id="ema20_pullback_reclaim",
            family="trend",
            parameters={"ema": 20, "pullback_bars": 5},
            description="pullback reclaims the 20-session EMA",
        ),
        TriggerSpec(
            primitive_id="relative_strength_breakout",
            family="momentum",
            parameters={"rs_lookback": 20, "breakout_lookback": 20},
            description="relative strength improves while price breaks out",
        ),
        TriggerSpec(
            primitive_id="vcp_breakout_proxy",
            family="volatility",
            parameters={"contraction_lookback": 20, "breakout_lookback": 10},
            description="volatility contraction followed by range break",
        ),
        TriggerSpec(
            primitive_id="return_zscore_reversion",
            family="mean_reversion",
            parameters={"lookback": 20, "zscore": -2.0},
            description="negative return z-score reversion trigger",
        ),
    )
    confirmations: tuple[PrimitiveSpec, ...] = (
        PrimitiveSpec(
            primitive_id="volume_surge_floor",
            family="participation",
            role="confirmation",
            parameters={"min_volume_ratio": 1.2},
            description="participation confirms the trigger without requiring an extreme spike",
        ),
        PrimitiveSpec(
            primitive_id="relative_strength_rank_top_quartile",
            family="momentum",
            role="confirmation",
            parameters={"rank_pct": 75},
            description="symbol ranks in the upper relative-strength quartile",
        ),
        PrimitiveSpec(
            primitive_id="stage2_trend_state",
            family="trend",
            role="confirmation",
            parameters={"required_stage": 2},
            description="Weinstein-style stage 2 trend state",
        ),
        PrimitiveSpec(
            primitive_id="liquidity_turnover_floor",
            family="microstructure",
            role="confirmation",
            parameters={"min_turnover_inr": 50_000_000},
            description="minimum traded value floor for execution quality",
        ),
        PrimitiveSpec(
            primitive_id="volatility_not_extreme",
            family="volatility",
            role="confirmation",
            parameters={"allowed_regimes": ["low", "normal"]},
            description="exclude stretched high-volatility reversion risk",
        ),
    )
    context_gates: tuple[PrimitiveSpec, ...] = (
        ContextGateSpec(
            primitive_id="breadth_positive",
            family="exogenous_context",
            parameters={"min_breadth_pct": 55},
            description="broad market breadth is supportive",
        ),
        ContextGateSpec(
            primitive_id="sector_rotation_top_quartile",
            family="exogenous_context",
            parameters={"sector_rank_pct": 75},
            description="sector is in the top rotation quartile",
        ),
        ContextGateSpec(
            primitive_id="volatility_regime_allowed",
            family="volatility",
            parameters={"allowed_regimes": ["low", "normal", "high"]},
            description="explicit volatility-regime scope gate",
        ),
        ContextGateSpec(
            primitive_id="fno_pcr_supportive",
            family="options_flow",
            parameters={"allowed_pcr_regimes": ["balanced", "put_heavy"]},
            description="F&O options context is supportive when present",
        ),
    )
    exits: tuple[PrimitiveSpec, ...] = (
        ExitSpec(
            primitive_id="atr_stop_2r_10bar",
            family="exit",
            parameters={"stop_atr": 1.5, "target_r": 2.0, "timeout_bars": 10},
            description="ATR structural stop, 2R target, and 10-bar timeout",
        ),
    )
    allowed_confirmation_families = {
        "price_structure": ("participation", "trend", "momentum", "microstructure"),
        "trend": ("participation", "trend", "momentum", "microstructure"),
        "momentum": ("participation", "trend", "momentum", "microstructure"),
        "volatility": ("participation", "trend", "momentum", "microstructure"),
        "mean_reversion": ("participation", "volatility", "microstructure"),
    }

    return DiscoverySearchSpace(
        triggers=triggers,
        confirmations=confirmations,
        context_gates=context_gates,
        exits=exits,
        scopes=tuple(scopes or (SetupScope(symbol="ALL", session_bucket="eod", vol_regime="any"),)),
        allowed_confirmation_families=allowed_confirmation_families,
        max_confirmations=max_confirmations,
        max_context_gates=max_context_gates,
        max_conditions=max_conditions,
    )


@dataclass(frozen=True)
class DiscoveryPartitionPlan:
    train_start: date
    train_end: date
    validation_start: date
    validation_end: date
    lockbox_start: date
    lockbox_end: date
    purge_bars: int = 0
    embargo_bars: int = 0
    lockbox_touched: bool = False

    def __post_init__(self) -> None:
        if not (
            self.train_start <= self.train_end
            < self.validation_start <= self.validation_end
            < self.lockbox_start <= self.lockbox_end
        ):
            raise ValueError("partition boundaries must be chronological and non-overlapping")
        if self.purge_bars < 0 or self.embargo_bars < 0:
            raise ValueError("purge_bars and embargo_bars must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "train_start": self.train_start.isoformat(),
            "train_end": self.train_end.isoformat(),
            "validation_start": self.validation_start.isoformat(),
            "validation_end": self.validation_end.isoformat(),
            "lockbox_start": self.lockbox_start.isoformat(),
            "lockbox_end": self.lockbox_end.isoformat(),
            "purge_bars": int(self.purge_bars),
            "embargo_bars": int(self.embargo_bars),
            "lockbox_touched": bool(self.lockbox_touched),
        }


@dataclass
class TrialRegistry:
    registry_dir: Path
    run_id: str
    data_set_id: str
    code_version: str
    partition_plan: DiscoveryPartitionPlan
    candidates: tuple[SetupSpec, ...]

    @property
    def n_trials(self) -> int:
        return len(self.candidates)

    @property
    def manifest_path(self) -> Path:
        return self.registry_dir / f"{self.run_id}_manifest.json"

    @property
    def trials_path(self) -> Path:
        return self.registry_dir / f"{self.run_id}_trials.jsonl"

    @property
    def rejections_path(self) -> Path:
        return self.registry_dir / f"{self.run_id}_rejections.jsonl"

    @classmethod
    def create(
        cls,
        *,
        registry_dir: str | Path,
        run_id: str,
        data_set_id: str,
        code_version: str,
        partition_plan: DiscoveryPartitionPlan,
        candidates: Iterable[SetupSpec],
    ) -> "TrialRegistry":
        registry = cls(
            registry_dir=Path(registry_dir),
            run_id=run_id,
            data_set_id=data_set_id,
            code_version=code_version,
            partition_plan=partition_plan,
            candidates=tuple(candidates),
        )
        registry.write()
        return registry

    def write(self) -> None:
        self.registry_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(json.dumps(self._manifest(), indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        lines = [json.dumps(self._trial_record(idx, spec), sort_keys=True, default=str) for idx, spec in enumerate(self.candidates, start=1)]
        self.trials_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        if not self.rejections_path.exists():
            self.rejections_path.write_text("", encoding="utf-8")

    def record_rejection(self, candidate_id: str, *, stage: str, reason: str, details: dict[str, Any] | None = None) -> None:
        known = {candidate.candidate_id for candidate in self.candidates}
        if candidate_id not in known:
            raise ValueError(f"candidate_id not registered: {candidate_id}")
        record = {
            "run_id": self.run_id,
            "candidate_id": candidate_id,
            "stage": stage,
            "reason": reason,
            "details": details or {},
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        with self.rejections_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")

    def _manifest(self) -> dict[str, Any]:
        partition = self.partition_plan.to_dict()
        return {
            "run_id": self.run_id,
            "data_set_id": self.data_set_id,
            "code_version": self.code_version,
            "n_trials": self.n_trials,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "partition": partition,
            "lockbox_touched": partition["lockbox_touched"],
        }

    def _trial_record(self, ordinal: int, spec: SetupSpec) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "ordinal": ordinal,
            "candidate_id": spec.candidate_id,
            "status": "registered",
            "spec": spec.canonical_dict(),
        }
