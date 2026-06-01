from datetime import date, datetime

from terminal.research_council.mode_profiles import load_mode_profile
from terminal.research_council.schemas import CouncilState, StewardVerdict
from terminal.research_council.states import data_steward
from terminal.research_council.states.data_steward import compute_verdict, run_check


def _base_snapshot():
    return {
        "eod_latest": date(2026, 5, 26),
        "stage_latest": date(2026, 5, 26),
        "fno_latest": date(2026, 5, 26),
        "financials_latest": date(2026, 5, 25),
        "intraday_latest": datetime(2026, 5, 26, 10, 0),
        "total_symbols": 2465,
        "liquid_symbols": 982,
        "analyzed_symbols": 968,
        "filters": ["close > 100", "volume > 100000", "at least 50 bars"],
    }


def test_compute_verdict_usable_when_required_data_is_fresh():
    verdict = compute_verdict(
        snapshot=_base_snapshot(),
        profile=load_mode_profile("market_council"),
        as_of=date(2026, 5, 26),
        now=datetime(2026, 5, 26, 10, 3),
    )

    assert verdict.data_status == "usable"
    assert verdict.blocking_gaps == []
    assert verdict.universe["total_symbols"] == 2465
    assert verdict.universe["liquid_symbols"] == 982
    assert verdict.universe["analyzed_symbols"] == 968


def test_compute_verdict_blocks_when_eod_is_stale():
    snapshot = _base_snapshot()
    snapshot["eod_latest"] = date(2026, 5, 22)

    verdict = compute_verdict(
        snapshot=snapshot,
        profile=load_mode_profile("market_council"),
        as_of=date(2026, 5, 26),
        now=datetime(2026, 5, 26, 10, 3),
    )

    assert verdict.data_status == "blocked"
    assert "eod_stale" in verdict.blocking_gaps
    assert "daily refresh" in (verdict.remediation or "").lower()


def test_compute_verdict_degrades_for_fno_lag_but_does_not_block_market_mode():
    snapshot = _base_snapshot()
    snapshot["fno_latest"] = date(2026, 5, 22)

    verdict = compute_verdict(
        snapshot=snapshot,
        profile=load_mode_profile("market_council"),
        as_of=date(2026, 5, 26),
        now=datetime(2026, 5, 26, 10, 3),
    )

    assert verdict.data_status == "degraded"
    assert "fno_stale" in verdict.non_blocking_gaps
    assert verdict.blocking_gaps == []


def test_report_review_mode_does_not_require_fno_or_fundamentals():
    snapshot = _base_snapshot()
    snapshot["fno_latest"] = None
    snapshot["financials_latest"] = None

    verdict = compute_verdict(
        snapshot=snapshot,
        profile=load_mode_profile("report_review"),
        as_of=date(2026, 5, 26),
        now=datetime(2026, 5, 26, 10, 3),
    )

    assert verdict.data_status == "usable"
    assert verdict.blocking_gaps == []
    assert verdict.non_blocking_gaps == []


def test_intraday_mode_blocks_when_intraday_snapshot_is_stale():
    snapshot = _base_snapshot()
    snapshot["intraday_latest"] = datetime(2026, 5, 26, 9, 45)

    verdict = compute_verdict(
        snapshot=snapshot,
        profile=load_mode_profile("intraday_tactical"),
        as_of=date(2026, 5, 26),
        now=datetime(2026, 5, 26, 10, 3),
    )

    assert verdict.data_status == "blocked"
    assert "intraday_stale" in verdict.blocking_gaps


def test_run_check_accepts_fake_snapshot_collector():
    verdict = run_check(
        mode="market_council",
        as_of=date(2026, 5, 26),
        now=datetime(2026, 5, 26, 10, 3),
        snapshot_loader=lambda: _base_snapshot(),
    )

    assert verdict.data_status == "usable"


def test_state_handler_skips_database_work_in_dry_run(monkeypatch):
    state = CouncilState(
        run_id="research_20260526_001",
        session_id="s1",
        created_at=datetime(2026, 5, 26, 10, 0),
        mode="market_council",
        stage="data_steward",
        objective="today",
        horizon="swing",
        risk_budget="moderate",
        universe_filter="liquid",
        flags={"dry_run": True},
    )

    monkeypatch.setattr(data_steward, "run_check", lambda **_: (_ for _ in ()).throw(AssertionError("called")))

    assert data_steward.run(state) == state


def test_state_handler_attaches_verdict(monkeypatch):
    state = CouncilState(
        run_id="research_20260526_001",
        session_id="s1",
        created_at=datetime(2026, 5, 26, 10, 0),
        mode="market_council",
        stage="data_steward",
        objective="today",
        horizon="swing",
        risk_budget="moderate",
        universe_filter="liquid",
    )
    verdict = StewardVerdict(as_of=date(2026, 5, 26), data_status="usable")
    monkeypatch.setattr(data_steward, "run_check", lambda **_: verdict)

    updated = data_steward.run(state)

    assert updated.steward_verdict == verdict
    assert updated.stage == "data_steward"
