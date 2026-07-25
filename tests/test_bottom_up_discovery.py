import json
from datetime import date

import pytest

from terminal.bottom_up_discovery import (
    ContextGateSpec,
    DiscoveryPartitionPlan,
    DiscoverySearchSpace,
    ExitSpec,
    PrimitiveSpec,
    SetupScope,
    SetupSpec,
    TrialRegistry,
    TriggerSpec,
    default_eod_discovery_space,
)


def _breakout_trigger() -> TriggerSpec:
    return TriggerSpec(
        primitive_id="breakout_20",
        family="price_structure",
        parameters={"lookback": 20},
        description="close clears prior 20-day high",
    )


def _volume_confirmation() -> PrimitiveSpec:
    return PrimitiveSpec(
        primitive_id="volume_surge",
        family="participation",
        role="confirmation",
        parameters={"ratio": 1.5},
        description="volume above 1.5x 20-day average",
    )


def _rsi_reversion_confirmation() -> PrimitiveSpec:
    return PrimitiveSpec(
        primitive_id="rsi_extreme",
        family="mean_reversion",
        role="confirmation",
        parameters={"threshold": 30},
        description="RSI below 30",
    )


def _breadth_gate() -> ContextGateSpec:
    return ContextGateSpec(
        primitive_id="breadth_positive",
        family="exogenous_context",
        parameters={"min_pct": 55},
        description="market breadth at least 55 percent positive",
    )


def _exit() -> ExitSpec:
    return ExitSpec(
        primitive_id="atr_target_stop",
        family="exit",
        parameters={"stop_atr": 1.5, "target_r": 2.0, "timeout_bars": 10},
        description="ATR stop with 2R target and time stop",
    )


def test_setup_spec_has_stable_canonical_id_and_scope():
    scope = SetupScope(symbol="ALL", session_bucket="eod", vol_regime="normal")
    first = SetupSpec(
        trigger=_breakout_trigger(),
        confirmations=(_volume_confirmation(),),
        context_gates=(_breadth_gate(),),
        exit=_exit(),
        scope=scope,
    )
    second = SetupSpec.from_dict(first.to_dict())

    assert first.candidate_id == second.candidate_id
    assert first.condition_count == 2
    assert first.scope.symbol == "ALL"
    assert first.to_dict()["scope"]["vol_regime"] == "normal"
    assert first.to_dict()["trigger"]["role"] == "trigger"
    assert first.to_dict()["exit"]["role"] == "exit"


def test_setup_spec_rejects_wrong_roles_and_complexity_budget():
    with pytest.raises(ValueError, match="trigger"):
        SetupSpec(
            trigger=PrimitiveSpec("bad", "price_structure", "confirmation", {}, "bad"),
            confirmations=(),
            context_gates=(),
            exit=_exit(),
            scope=SetupScope(),
        )

    spec = SetupSpec(
        trigger=_breakout_trigger(),
        confirmations=(_volume_confirmation(), _rsi_reversion_confirmation()),
        context_gates=(_breadth_gate(),),
        exit=_exit(),
        scope=SetupScope(),
    )
    with pytest.raises(ValueError, match="complexity"):
        spec.validate(max_conditions=2)


def test_search_space_enumerates_only_allowed_economic_combinations():
    search = DiscoverySearchSpace(
        triggers=(_breakout_trigger(),),
        confirmations=(_volume_confirmation(), _rsi_reversion_confirmation()),
        context_gates=(_breadth_gate(),),
        exits=(_exit(),),
        scopes=(SetupScope(symbol="ALL", session_bucket="eod", vol_regime="normal"),),
        allowed_confirmation_families={"price_structure": ("participation", "trend", "momentum")},
        max_confirmations=1,
        max_context_gates=1,
        max_conditions=2,
    )

    candidates = search.generate_candidates()

    assert len(candidates) == 4
    assert all(c.trigger.primitive_id == "breakout_20" for c in candidates)
    assert not any(
        confirmation.primitive_id == "rsi_extreme"
        for candidate in candidates
        for confirmation in candidate.confirmations
    )
    assert len({candidate.candidate_id for candidate in candidates}) == len(candidates)


def test_default_eod_discovery_space_is_bounded_and_economically_filtered():
    search = default_eod_discovery_space(
        scopes=(SetupScope(symbol="ALL", session_bucket="eod", vol_regime="normal"),),
        max_confirmations=2,
        max_context_gates=1,
        max_conditions=3,
    )

    candidates = search.generate_candidates()

    assert candidates
    assert all(candidate.condition_count <= 3 for candidate in candidates)
    assert len({candidate.candidate_id for candidate in candidates}) == len(candidates)
    for candidate in candidates:
        allowed = search.allowed_confirmation_families[candidate.trigger.family]
        assert all(confirmation.family in allowed for confirmation in candidate.confirmations)


def test_partition_plan_enforces_chronology_and_embargo_metadata():
    plan = DiscoveryPartitionPlan(
        train_start=date(2023, 1, 1),
        train_end=date(2024, 12, 31),
        validation_start=date(2025, 1, 15),
        validation_end=date(2025, 12, 31),
        lockbox_start=date(2026, 1, 15),
        lockbox_end=date(2026, 6, 19),
        purge_bars=10,
        embargo_bars=5,
    )

    assert plan.to_dict()["lockbox_touched"] is False
    assert plan.to_dict()["purge_bars"] == 10

    with pytest.raises(ValueError, match="chronological"):
        DiscoveryPartitionPlan(
            train_start=date(2025, 1, 1),
            train_end=date(2025, 6, 1),
            validation_start=date(2025, 5, 1),
            validation_end=date(2025, 12, 1),
            lockbox_start=date(2026, 1, 1),
            lockbox_end=date(2026, 6, 1),
        )


def test_trial_registry_persists_manifest_trials_and_rejections(tmp_path):
    candidates = DiscoverySearchSpace(
        triggers=(_breakout_trigger(),),
        confirmations=(_volume_confirmation(),),
        context_gates=(),
        exits=(_exit(),),
        scopes=(SetupScope(symbol="ALL", session_bucket="eod", vol_regime="normal"),),
    ).generate_candidates()
    partition = DiscoveryPartitionPlan(
        train_start=date(2023, 1, 1),
        train_end=date(2024, 12, 31),
        validation_start=date(2025, 1, 15),
        validation_end=date(2025, 12, 31),
        lockbox_start=date(2026, 1, 15),
        lockbox_end=date(2026, 6, 19),
    )

    registry = TrialRegistry.create(
        registry_dir=tmp_path,
        run_id="discovery_20260622_000000",
        data_set_id="nifty500_eod_3y",
        code_version="abc123",
        partition_plan=partition,
        candidates=candidates,
    )
    registry.record_rejection(candidates[0].candidate_id, stage="C2", reason="positive_net_expectancy_required")

    manifest = json.loads((tmp_path / "discovery_20260622_000000_manifest.json").read_text())
    trials = [json.loads(line) for line in (tmp_path / "discovery_20260622_000000_trials.jsonl").read_text().splitlines()]
    rejections = [json.loads(line) for line in (tmp_path / "discovery_20260622_000000_rejections.jsonl").read_text().splitlines()]

    assert registry.n_trials == len(candidates)
    assert manifest["n_trials"] == len(candidates)
    assert manifest["lockbox_touched"] is False
    assert trials[0]["ordinal"] == 1
    assert trials[0]["status"] == "registered"
    assert trials[0]["candidate_id"] == candidates[0].candidate_id
    assert rejections[0]["candidate_id"] == candidates[0].candidate_id
    assert rejections[0]["reason"] == "positive_net_expectancy_required"
