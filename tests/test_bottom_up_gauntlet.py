import json
from datetime import date

import pandas as pd

from terminal.bottom_up_discovery import (
    ContextGateSpec,
    DiscoveryPartitionPlan,
    ExitSpec,
    PrimitiveSpec,
    SetupScope,
    SetupSpec,
    TrialRegistry,
    TriggerSpec,
)
from terminal.bottom_up_gauntlet import (
    ScreeningConfig,
    build_candidate_train_trades,
    candidate_matches_event,
    run_train_screening,
    summarize_candidate_trades,
    write_screening_outputs,
)


def _exit() -> ExitSpec:
    return ExitSpec(
        primitive_id="atr_stop_2r_10bar",
        family="exit",
        parameters={"stop_atr": 1.5, "target_r": 2.0, "timeout_bars": 10},
    )


def _breakout_candidate(*, confirmations=(), gates=(), vol_regime="normal") -> SetupSpec:
    return SetupSpec(
        trigger=TriggerSpec(
            primitive_id="breakout_20_volume",
            family="price_structure",
            parameters={"lookback": 20},
        ),
        confirmations=tuple(confirmations),
        context_gates=tuple(gates),
        exit=_exit(),
        scope=SetupScope(symbol="ALL", session_bucket="eod", vol_regime=vol_regime),
    )


def _partition() -> DiscoveryPartitionPlan:
    return DiscoveryPartitionPlan(
        train_start=date(2023, 1, 1),
        train_end=date(2023, 1, 31),
        validation_start=date(2023, 2, 15),
        validation_end=date(2023, 12, 31),
        lockbox_start=date(2024, 1, 15),
        lockbox_end=date(2024, 6, 30),
        purge_bars=2,
        embargo_bars=1,
    )


def _event_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": "2023-01-03",
                "symbol": "AAA",
                "setup": "breakout_20_volume",
                "sector": "TEST",
                "net_r_multiple": 1.0,
                "r_multiple": 1.2,
                "estimated_cost_r": 0.2,
                "volume_ratio_20d": 1.8,
                "turnover_cr_20d": 80.0,
                "breadth_positive_pct": 62.0,
                "sector_rank_1d": 81.0,
                "relative_strength": 82.0,
                "stage": "STAGE_2",
                "adr_pct_20": 3.0,
                "model_split": "train",
            },
            {
                "date": "2023-01-06",
                "symbol": "BBB",
                "setup": "breakout_20_volume",
                "sector": "TEST",
                "net_r_multiple": 0.4,
                "r_multiple": 0.6,
                "estimated_cost_r": 0.2,
                "volume_ratio_20d": 1.5,
                "turnover_cr_20d": 70.0,
                "breadth_positive_pct": 59.0,
                "sector_rank_1d": 77.0,
                "relative_strength": 79.0,
                "stage": "STAGE_2",
                "adr_pct_20": 3.5,
                "model_split": "train",
            },
            {
                "date": "2023-01-20",
                "symbol": "CCC",
                "setup": "breakout_20_volume",
                "sector": "TEST",
                "net_r_multiple": -0.2,
                "r_multiple": 0.0,
                "estimated_cost_r": 0.2,
                "volume_ratio_20d": 1.1,
                "turnover_cr_20d": 5.0,
                "breadth_positive_pct": 48.0,
                "sector_rank_1d": 40.0,
                "relative_strength": 50.0,
                "stage": "STAGE_1",
                "adr_pct_20": 7.0,
                "model_split": "train",
            },
            {
                "date": "2023-02-20",
                "symbol": "DDD",
                "setup": "breakout_20_volume",
                "sector": "TEST",
                "net_r_multiple": 2.0,
                "r_multiple": 2.2,
                "estimated_cost_r": 0.2,
                "volume_ratio_20d": 2.0,
                "turnover_cr_20d": 90.0,
                "breadth_positive_pct": 65.0,
                "sector_rank_1d": 85.0,
                "relative_strength": 88.0,
                "stage": "STAGE_2",
                "adr_pct_20": 3.0,
                "model_split": "test",
            },
        ]
    )


def test_candidate_matches_event_confirmations_gates_and_scope():
    candidate = _breakout_candidate(
        confirmations=(
            PrimitiveSpec(
                primitive_id="volume_surge_floor",
                family="participation",
                role="confirmation",
                parameters={"min_volume_ratio": 1.2},
            ),
            PrimitiveSpec(
                primitive_id="liquidity_turnover_floor",
                family="microstructure",
                role="confirmation",
                parameters={"min_turnover_inr": 50_000_000},
            ),
        ),
        gates=(
            ContextGateSpec(
                primitive_id="breadth_positive",
                family="exogenous_context",
                parameters={"min_breadth_pct": 55},
            ),
        ),
    )

    events = _event_rows()

    assert candidate_matches_event(candidate, events.iloc[0]) is True
    assert candidate_matches_event(candidate, events.iloc[2]) is False


def test_build_candidate_train_trades_uses_train_partition_only():
    candidate = _breakout_candidate(
        confirmations=(
            PrimitiveSpec(
                primitive_id="volume_surge_floor",
                family="participation",
                role="confirmation",
                parameters={"min_volume_ratio": 1.2},
            ),
        ),
        gates=(
            ContextGateSpec(
                primitive_id="breadth_positive",
                family="exogenous_context",
                parameters={"min_breadth_pct": 55},
            ),
        ),
    )

    trades = build_candidate_train_trades([candidate], _event_rows(), _partition(), ScreeningConfig())

    assert trades["symbol"].tolist() == ["AAA", "BBB"]
    assert set(trades["candidate_id"]) == {candidate.candidate_id}
    assert trades["stage"].tolist() == ["C2_train_screen", "C2_train_screen"]


def test_run_train_screening_logs_c2_and_c3_rejections(tmp_path):
    strong = _breakout_candidate(
        confirmations=(
            PrimitiveSpec("volume_surge_floor", "participation", "confirmation", {"min_volume_ratio": 1.2}),
        ),
        gates=(ContextGateSpec("breadth_positive", "exogenous_context", {"min_breadth_pct": 55}),),
    )
    weak = _breakout_candidate(
        confirmations=(
            PrimitiveSpec(
                "relative_strength_rank_top_quartile",
                "momentum",
                "confirmation",
                {"rank_pct": 95},
            ),
        ),
        gates=(ContextGateSpec("sector_rotation_top_quartile", "exogenous_context", {"sector_rank_pct": 75}),),
    )
    unstable = _breakout_candidate(vol_regime="any")
    registry = TrialRegistry.create(
        registry_dir=tmp_path,
        run_id="discovery_test",
        data_set_id="synthetic",
        code_version="test",
        partition_plan=_partition(),
        candidates=(strong, weak, unstable),
    )
    events = _event_rows().copy()
    events.loc[events["symbol"].isin(["AAA", "BBB"]), "net_r_multiple"] = [0.8, 0.7]
    events.loc[events["symbol"] == "CCC", "net_r_multiple"] = -1.4

    result = run_train_screening(
        candidates=(strong, weak, unstable),
        events=events,
        partition=_partition(),
        config=ScreeningConfig(min_trades=2, min_profit_factor=1.01, require_positive_time_halves=True),
        registry=registry,
    )

    assert result.survivors["candidate_id"].tolist() == [strong.candidate_id]
    summary = result.summary.set_index("candidate_id")
    assert summary.loc[weak.candidate_id, "status"] == "rejected"
    assert summary.loc[unstable.candidate_id, "rejection_stage"] == "C3"
    rejections = [
        json.loads(line)
        for line in (tmp_path / "discovery_test_rejections.jsonl").read_text().splitlines()
    ]
    assert {row["candidate_id"] for row in rejections} == {weak.candidate_id, unstable.candidate_id}


def test_summarize_and_write_screening_outputs(tmp_path):
    candidate = _breakout_candidate(vol_regime="any")
    trades = build_candidate_train_trades([candidate], _event_rows(), _partition(), ScreeningConfig())
    summary = summarize_candidate_trades([candidate], trades, ScreeningConfig(min_trades=1))

    paths = write_screening_outputs(
        output_dir=tmp_path,
        run_id="discovery_test",
        summary=summary,
        survivors=summary[summary["status"].eq("passed")],
        candidate_trades=trades,
        n_trials=1,
        partition=_partition(),
    )

    assert summary.loc[0, "trades"] == 3
    assert paths["summary_csv"].exists()
    assert paths["trades_csv"].exists()
    assert "N Trials: 1" in paths["markdown"].read_text()
