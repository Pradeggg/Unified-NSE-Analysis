from datetime import datetime

from terminal.research_council.critics.overfit import OverfitCritic
from terminal.research_council.schemas import CouncilState, ExecutionResult


def _state(metrics):
    return CouncilState(
        run_id="run_1",
        session_id="s1",
        created_at=datetime(2026, 5, 27, 10, 0),
        mode="strategy_build",
        stage="critic_review",
        objective="strategy",
        horizon="swing",
        risk_budget="moderate",
        universe_filter="liquid",
        flags={"strategy_metrics": metrics},
    )


def test_overfit_blocks_low_trade_count():
    review = OverfitCritic().review(_state({"trade_count": 12, "parameter_count": 4, "validation_pass": True}))

    assert review.severity_max == "block"
    assert "trade count" in review.findings[0].description


def test_overfit_warns_on_excessive_parameters():
    review = OverfitCritic().review(_state({"trade_count": 80, "parameter_count": 12, "validation_pass": True}))

    assert review.severity_max == "warn"


def test_overfit_blocks_failed_validation():
    review = OverfitCritic().review(_state({"trade_count": 80, "parameter_count": 4, "validation_pass": False}))

    assert review.severity_max == "block"


def test_overfit_reads_coder_quant_sweep_metrics_when_flags_missing():
    state = _state({})
    state = CouncilState.from_dict(
        {
            **state.to_dict(),
            "execution_results": {
                "plan_1": {
                    "coder_quant_shortlist_sweep": ExecutionResult(
                        result_id="er_1",
                        step_id="coder_quant_shortlist_sweep",
                        status="success",
                        outputs=[
                            {
                                "ok": True,
                                "best": {
                                    "result": {
                                        "metrics": {
                                            "trade_count": 12,
                                            "validation_pass": False,
                                            "splits": {"validation": {"trade_count": 3, "return_pct": -2.0, "sharpe": -0.2}},
                                        }
                                    }
                                },
                            }
                        ],
                    ).to_dict()
                }
            },
        }
    )

    review = OverfitCritic().review(state)

    assert review.severity_max == "block"
    assert {finding.finding_id for finding in review.findings} >= {"overfit_trade_count", "overfit_validation"}
