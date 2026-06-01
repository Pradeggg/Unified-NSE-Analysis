from __future__ import annotations

from datetime import datetime

from terminal.research_council.schemas import CouncilState


BROKEN_REPORT = """▶ REQUIRED TOOL VALIDATION FAILED
  Intent: stock_brief
  Missing required tool(s): resolve_symbol, get_symbol_snapshot
  No market conclusion was rendered because the mandatory evidence plan did not run.

▶ SOURCE TRAIL
  search_yahoo_finance: ok
"""


def _report_review_state(path: str) -> CouncilState:
    return CouncilState(
        run_id="research_review_1",
        session_id="s1",
        created_at=datetime(2026, 5, 27, 10, 0),
        mode="report_review",
        stage="market_state",
        objective=f"/council review --file {path}",
        horizon="swing",
        risk_budget="moderate",
        universe_filter="report",
        flags={"report_path": path},
    )


def test_build_report_review_pack_flags_required_tool_failure(tmp_path):
    report = tmp_path / "MODISONLTD_research.html"
    report.write_text(BROKEN_REPORT, encoding="utf-8")

    from terminal.research_council.report_review import build_report_review_evidence_pack

    pack = build_report_review_evidence_pack(report_path=str(report))

    assert pack.mode == "report_review"
    assert pack.symbols == ["MODISONLTD"]
    assert [item.field for item in pack.missing_evidence] == [
        "required_tool_validation_failed",
        "missing_required_tools",
    ]
    review = pack.sections["report_review"]
    assert review["findings"][0]["line"] == 1
    assert review["findings"][0]["severity"] == "block"
    assert review["findings"][0]["remediation"] == "Rerun with mandatory evidence plan before rendering a market conclusion."
    assert review["missing_required_tools"] == ["resolve_symbol", "get_symbol_snapshot"]
    assert pack.source_trail[0].source == str(report)
    assert pack.source_trail[0].rows == 7


def test_market_state_uses_report_review_pack_in_report_review_mode(tmp_path):
    report = tmp_path / "broken_report.md"
    report.write_text(BROKEN_REPORT, encoding="utf-8")

    from terminal.research_council.states import market_state

    updated = market_state.run(_report_review_state(str(report)))

    assert updated.evidence_pack is not None
    assert updated.evidence_pack.mode == "report_review"
    assert updated.evidence_pack.sections["report_review"]["status"] == "blocked"


def test_report_review_critic_state_uses_data_quality_and_evidence_only(tmp_path, monkeypatch):
    report = tmp_path / "broken_report.md"
    report.write_text(BROKEN_REPORT, encoding="utf-8")

    from terminal.research_council.states import critic_review, market_state

    monkeypatch.setattr(critic_review, "save_critic_reviews", lambda *_args, **_kwargs: None)
    state = market_state.run(_report_review_state(str(report)))
    state = CouncilState.from_dict({**state.to_dict(), "stage": "critic_review"})

    updated = critic_review.run(state)

    critics = {review.critic for review in updated.critic_reviews[0]}
    assert critics == {"data_quality", "evidence"}
    findings = [
        finding
        for review in updated.critic_reviews[0]
        for finding in review.findings
    ]
    assert any(finding.target.get("line") == "1" for finding in findings)
    assert any("Missing required tool" in finding.description for finding in findings)
