from datetime import datetime

from terminal.research_council.critics.leakage import LeakageCritic
from terminal.research_council.schemas import CouncilState


def _state(flags):
    return CouncilState(
        run_id="run_1",
        session_id="s1",
        created_at=datetime(2026, 5, 27, 10, 0),
        mode="strategy_build",
        stage="critic_review",
        objective="test strategy",
        horizon="swing",
        risk_budget="moderate",
        universe_filter="liquid",
        flags=flags,
    )


def test_leakage_blocks_latest_fundamentals_in_historical_backtest():
    review = LeakageCritic().review(_state({"latest_fundamentals_used_in_history": True}))

    assert review.severity_max == "block"
    assert review.findings[0].target == {"kind": "backtest", "id": "fundamentals"}


def test_leakage_blocks_non_time_ordered_split_policy():
    review = LeakageCritic().review(_state({"split_policy": "random"}))

    assert review.severity_max == "block"
    assert "time ordered" in review.findings[0].recommendation


def test_leakage_returns_info_when_no_backtest_metadata_present():
    review = LeakageCritic().review(_state({}))

    assert review.severity_max == "info"
    assert review.findings == []
