from __future__ import annotations

from datetime import date


class FakeProposalRepo:
    def __init__(self, patterns=None):
        self.patterns = list(patterns or [])
        self.saved = []

    def list_patterns(self, status=None, limit=None):
        rows = list(self.patterns)
        if status:
            rows = [row for row in rows if row.get("status") == status]
        return rows[:limit] if limit else rows

    def save_proposal(self, proposal):
        self.saved.append(dict(proposal))
        return 2000 + len(self.saved)


def _pattern(pattern_key, pattern_type, label, *, candidate_type, examples=(), metadata=None, frequency=3, score=60):
    return {
        "pattern_id": abs(hash(pattern_key)) % 100000,
        "pattern_key": pattern_key,
        "status": "observed",
        "pattern_payload": {
            "pattern_key": pattern_key,
            "pattern_type": pattern_type,
            "label": label,
            "frequency": frequency,
            "score": score,
            "priority": "high" if score >= 50 else "medium",
            "candidate_type": candidate_type,
            "start_date": "2026-05-25",
            "end_date": "2026-06-07",
            "evidence_event_ids": [1, 2],
            "evidence_chain_ids": [10],
            "examples": list(examples),
            **dict(metadata or {}),
        },
    }


def test_fallback_failure_pattern_becomes_route_and_tool_proposal():
    from terminal.learning.proposal_generator import generate_learning_proposals

    result = generate_learning_proposals(
        [
            _pattern(
                "fallback_failure:missing required tool: get_latest_results",
                "repeated_llm_fallback_failure",
                "missing required tool: get_latest_results",
                candidate_type="route_tool_skill_candidate",
                examples=("latest quarterly results analysis",),
                metadata={"missing_evidence": ["scores.quarterly_results"]},
            )
        ]
    )

    assert len(result.proposals) == 1
    proposal = result.proposals[0]
    record = proposal.to_record()
    payload = record["proposal_payload"]
    assert record["proposal_type"] == "tool_proposal"
    assert record["status"] == "proposed"
    assert "latest quarterly results analysis" in payload["observed_pattern"]["examples"]
    assert payload["proposed_behavior"]["summary"].startswith("Add deterministic evidence/tool coverage")
    assert "get_latest_results" in payload["affected_surfaces"]["tools"]
    assert payload["expected_tool_calls"] == ["get_latest_results"]
    assert "Do not route this query through generic llm_driven_fallback until evidence collection succeeds." in payload["must_not_call_rules"]
    assert any("latest quarterly results analysis" in test["input"] for test in payload["generated_test_cases"])
    assert any("missing_evidence" in item for item in payload["acceptance_criteria"])


def test_vcp_breakout_phrasing_pattern_becomes_skill_proposal():
    from terminal.learning.proposal_generator import generate_learning_proposals

    result = generate_learning_proposals(
        [
            _pattern(
                "query:vcp breakouts with good fundamentals",
                "repeated_user_phrasing",
                "vcp breakouts with good fundamentals",
                candidate_type="route_or_prompt_proposal",
                examples=("stocks creating new highs or VCP or breakouts with good fundamentals",),
            )
        ]
    )

    proposal = result.proposals[0]
    payload = proposal.to_record()["proposal_payload"]
    assert proposal.proposal_type == "skill_proposal"
    assert "vcp_breakouts_with_fundamentals" in payload["affected_surfaces"]["skills"]
    assert payload["expected_tool_calls"] == ["run_quality_breakout_screener", "export_tradingview_watchlist"]
    assert any("TradingView" in item for item in payload["acceptance_criteria"])


def test_report_issue_pattern_becomes_report_validation_proposal():
    from terminal.learning.proposal_generator import generate_learning_proposals

    result = generate_learning_proposals(
        [
            _pattern(
                "report_issue:broken report links",
                "repeated_report_validation_issue",
                "broken report links",
                candidate_type="report_validation_proposal",
                examples=("results analysis links are not working",),
                metadata={"artifacts": ["reports/latest/results_analysis.html"]},
            )
        ]
    )

    proposal = result.proposals[0]
    payload = proposal.to_record()["proposal_payload"]
    assert proposal.proposal_type == "report_validation_proposal"
    assert "reports/latest/results_analysis.html" in payload["affected_surfaces"]["reports"]
    assert payload["expected_tool_calls"] == ["validate_report_links", "regenerate_report"]
    assert "Do not email or publish a report with failed validation." in payload["must_not_call_rules"]


def test_workflow_pattern_becomes_workflow_proposal():
    from terminal.learning.proposal_generator import generate_learning_proposals

    result = generate_learning_proposals(
        [
            _pattern(
                "workflow:daily_refresh_report_review_email",
                "recurring_workflow_chain",
                "daily_refresh_report_review_email",
                candidate_type="workflow_proposal",
            )
        ]
    )

    proposal = result.proposals[0]
    payload = proposal.to_record()["proposal_payload"]
    assert proposal.proposal_type == "workflow_proposal"
    assert "daily_refresh" in payload["affected_surfaces"]["routes"]
    assert payload["expected_tool_calls"] == ["daily_refresh", "generate_eod_reports", "validate_reports", "email_reports"]
    assert any("daily refresh" in test["input"] for test in payload["generated_test_cases"])


def test_generate_and_save_learning_proposals_persists_proposed_records_only():
    from terminal.learning.proposal_generator import generate_and_save_learning_proposals

    repo = FakeProposalRepo(
        patterns=[
            _pattern(
                "query:vcp breakouts with good fundamentals",
                "repeated_user_phrasing",
                "vcp breakouts with good fundamentals",
                candidate_type="route_or_prompt_proposal",
            )
        ]
    )

    result = generate_and_save_learning_proposals(repository=repo, status="observed")

    assert len(repo.saved) == 1
    assert repo.saved[0]["status"] == "proposed"
    assert repo.saved[0]["source_pattern_id"] is not None
    assert result.saved_proposal_ids == [2001]


def test_agent_adda_parser_accepts_learning_propose_command():
    from agent_adda.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(["learning", "propose", "--status", "observed", "--limit", "5"])

    assert args.command == "learning"
    assert args.learning_command == "propose"
    assert args.status == "observed"
    assert args.limit == 5
