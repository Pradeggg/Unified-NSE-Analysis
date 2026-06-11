from __future__ import annotations


class FakeProposalValidationRepo:
    def __init__(self, proposals=None):
        self.proposals = list(proposals or [])
        self.status_updates = []
        self.validation_runs = []

    def list_proposals(self, status=None):
        rows = list(self.proposals)
        if status:
            rows = [row for row in rows if row.get("status") == status]
        return rows

    def update_proposal_status(self, proposal_id, status):
        self.status_updates.append((proposal_id, status))
        return proposal_id

    def record_proposal_validation_run(self, run):
        self.validation_runs.append(dict(run))
        return 3000 + len(self.validation_runs)


def _proposal(proposal_id, proposal_type, *, payload=None, status="proposed"):
    return {
        "proposal_id": proposal_id,
        "proposal_type": proposal_type,
        "title": f"{proposal_type} title",
        "status": status,
        "source_pattern_id": 100 + proposal_id,
        "proposal_payload": {
            "proposal_type": proposal_type,
            "title": f"{proposal_type} title",
            "observed_pattern": {"pattern_key": f"pattern:{proposal_id}", "examples": ["sample user ask"]},
            "proposed_behavior": {"summary": "Do the deterministic thing."},
            "affected_surfaces": {
                "routes": ["situation_assessment"],
                "tools": ["get_latest_results"],
                "skills": [],
                "reports": [],
            },
            "generated_test_cases": [
                {
                    "name": "routes_user_query_to_tool",
                    "input": "latest quarterly results analysis",
                    "assertions": ["calls get_latest_results"],
                }
            ],
            "expected_tool_calls": ["get_latest_results"],
            "must_not_call_rules": ["Do not use generic fallback before evidence collection."],
            "acceptance_criteria": ["Tool evidence is present before synthesis."],
            **dict(payload or {}),
        },
    }


def test_invalid_proposal_fails_closed_and_validation_run_is_stored():
    from terminal.learning.proposal_validator import validate_learning_proposal

    proposal = _proposal(
        1,
        "tool_proposal",
        payload={"generated_test_cases": [{"name": "missing_input", "assertions": ["calls tool"]}]},
    )

    result = validate_learning_proposal(proposal)

    assert result.status_after == "test_failed"
    assert result.ok is False
    assert any("generated_test_cases[0].input is required" in finding for finding in result.findings)
    assert result.to_validation_run()["proposal_id"] == 1
    assert result.to_validation_run()["status_before"] == "proposed"
    assert result.to_validation_run()["status_after"] == "test_failed"


def test_valid_route_or_tool_proposal_produces_implementation_backlog_snippet():
    from terminal.learning.proposal_validator import validate_learning_proposal

    result = validate_learning_proposal(_proposal(2, "tool_proposal"))

    assert result.ok is True
    assert result.status_after == "review_pending"
    assert result.backlog_snippet["title"] == "tool_proposal title"
    assert "terminal/tools.py" in result.backlog_snippet["files_to_edit"]
    assert "tests/test_learning_generated_tool_proposal_2.py" in result.backlog_snippet["tests_to_add"]
    assert result.backlog_snippet["expected_tool_calls"] == ["get_latest_results"]
    assert result.backlog_snippet["must_not_call_rules"] == ["Do not use generic fallback before evidence collection."]


def test_skill_proposal_requires_schema_sql_fixture_and_reviewer_approval():
    from terminal.learning.proposal_validator import validate_learning_proposal

    missing_evidence = validate_learning_proposal(_proposal(3, "skill_proposal"))
    assert missing_evidence.status_after == "test_failed"
    assert "skill proposal requires schema_validation=pass" in missing_evidence.findings
    assert "skill proposal requires reviewer_approval=pass" in missing_evidence.findings

    valid = validate_learning_proposal(
        _proposal(
            4,
            "skill_proposal",
            payload={
                "affected_surfaces": {
                    "routes": ["quality_breakouts"],
                    "tools": ["run_quality_breakout_screener"],
                    "skills": ["vcp_breakouts_with_fundamentals"],
                    "reports": [],
                },
                "validation_evidence": {
                    "schema_validation": "pass",
                    "sql_safety": "pass",
                    "fixture_execution": "pass",
                    "reviewer_approval": "pass",
                },
            },
        )
    )

    assert valid.ok is True
    assert valid.status_after == "review_pending"
    assert valid.backlog_snippet["skill_cards_to_create"] == ["vcp_breakouts_with_fundamentals"]


def test_deprecation_proposal_requires_failure_evidence_or_replacement():
    from terminal.learning.proposal_validator import validate_learning_proposal

    invalid = validate_learning_proposal(_proposal(5, "deprecation_proposal"))
    assert invalid.status_after == "test_failed"
    assert "deprecation proposal requires repeated failure evidence or replacement target" in invalid.findings

    valid = validate_learning_proposal(
        _proposal(
            6,
            "deprecation_proposal",
            payload={"deprecation_evidence": {"repeated_failure_count": 3}},
        )
    )
    assert valid.status_after == "review_pending"


def test_validate_and_store_learning_proposals_updates_statuses_and_records_runs():
    from terminal.learning.proposal_validator import validate_and_store_learning_proposals

    repo = FakeProposalValidationRepo(
        proposals=[
            _proposal(7, "tool_proposal"),
            _proposal(8, "tool_proposal", payload={"generated_test_cases": []}),
        ]
    )

    result = validate_and_store_learning_proposals(repository=repo, status="proposed")

    assert [item.status_after for item in result.results] == ["review_pending", "test_failed"]
    assert repo.status_updates == [(7, "review_pending"), (8, "test_failed")]
    assert [run["status_after"] for run in repo.validation_runs] == ["review_pending", "test_failed"]
    assert result.validation_run_ids == [3001, 3002]


def test_agent_adda_parser_accepts_learning_validate_proposals_command():
    from agent_adda.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(["learning", "validate-proposals", "--status", "proposed"])

    assert args.command == "learning"
    assert args.learning_command == "validate-proposals"
    assert args.status == "proposed"
