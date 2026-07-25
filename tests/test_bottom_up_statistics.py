import pandas as pd

from terminal.bottom_up_statistics import (
    MultipleTestingConfig,
    benjamini_hochberg,
    bootstrap_mean_test,
    run_c4_multiple_testing,
    write_c4_outputs,
)


def test_benjamini_hochberg_uses_registered_trial_count():
    frame = pd.DataFrame({"candidate_id": ["a", "b", "c"], "p_value": [0.001, 0.02, 0.5]})

    out = benjamini_hochberg(frame, p_col="p_value", n_tests=100)

    q = out.set_index("candidate_id")["fdr_q_value"]
    assert round(q["a"], 4) == 0.1
    assert q["b"] == 1.0
    assert q["c"] == 1.0


def test_bootstrap_mean_test_separates_positive_from_flat_sample():
    positive = bootstrap_mean_test([0.6] * 30 + [-0.2] * 10, n_boot=500, seed=7)
    flat = bootstrap_mean_test([0.2, -0.2] * 20, n_boot=500, seed=7)

    assert positive.mean_r > 0
    assert positive.ci_low_r > 0
    assert positive.p_value < flat.p_value
    assert flat.ci_low_r < 0 < flat.ci_high_r


def test_run_c4_multiple_testing_applies_bootstrap_fdr_and_reality_check():
    summary = pd.DataFrame(
        [
            {"candidate_id": "strong", "trigger": "ema20_pullback_reclaim", "confirmations": "", "context_gates": "", "scope": "ALL|eod|normal"},
            {"candidate_id": "weak", "trigger": "breakout_20_volume", "confirmations": "", "context_gates": "", "scope": "ALL|eod|normal"},
        ]
    )
    trades = pd.DataFrame(
        [{"candidate_id": "strong", "r_net": 0.4} for _ in range(60)]
        + [{"candidate_id": "weak", "r_net": value} for value in ([0.2, -0.2] * 30)]
    )

    out = run_c4_multiple_testing(
        representatives=summary,
        candidate_trades=trades,
        n_trials=2,
        config=MultipleTestingConfig(n_boot=500, alpha=0.05, fdr_alpha=0.05, seed=11),
    )

    statuses = out.set_index("candidate_id")["c4_status"].to_dict()
    assert statuses["strong"] == "passed"
    assert statuses["weak"] == "rejected"
    assert out.loc[out["candidate_id"].eq("strong"), "reality_check_p_value"].iloc[0] <= 0.05


def test_write_c4_outputs(tmp_path):
    result = pd.DataFrame(
        [
            {
                "candidate_id": "strong",
                "trigger": "ema20_pullback_reclaim",
                "confirmations": "",
                "context_gates": "",
                "scope": "ALL|eod|normal",
                "trades": 60,
                "observed_mean_r": 0.4,
                "bootstrap_p_value": 0.001,
                "fdr_q_value": 0.002,
                "deflated_z": 2.0,
                "reality_check_p_value": 0.01,
                "c4_status": "passed",
                "c4_rejection_reason": "",
            }
        ]
    )

    paths = write_c4_outputs(output_dir=tmp_path, run_id="discovery_test", result=result, n_trials=2)

    assert paths["result_csv"].exists()
    assert paths["passed_csv"].exists()
    assert paths["rejections_jsonl"].exists()
    assert "Passed C4: 1" in paths["markdown"].read_text()
