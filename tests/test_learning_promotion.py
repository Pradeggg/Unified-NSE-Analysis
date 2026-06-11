from __future__ import annotations


class FakePromotionRepo:
    def __init__(self, proposals=None):
        self.proposals = {row["proposal_id"]: dict(row) for row in proposals or []}
        self.status_updates = []
        self.promotion_runs = []

    def list_proposals(self, status=None):
        rows = list(self.proposals.values())
        if status:
            rows = [row for row in rows if row.get("status") == status]
        return rows

    def get_proposal(self, proposal_id):
        return self.proposals.get(proposal_id)

    def update_proposal_status(self, proposal_id, status):
        self.status_updates.append((proposal_id, status))
        self.proposals[proposal_id]["status"] = status
        return proposal_id

    def record_promotion_run(self, run):
        self.promotion_runs.append(dict(run))
        return 4000 + len(self.promotion_runs)


def _proposal(proposal_id, proposal_type, *, status="review_pending", payload=None):
    return {
        "proposal_id": proposal_id,
        "proposal_type": proposal_type,
        "title": f"{proposal_type} title",
        "status": status,
        "proposal_payload": {
            "proposal_type": proposal_type,
            "title": f"{proposal_type} title",
            "observed_pattern": {"pattern_key": f"pattern:{proposal_id}"},
            "proposed_behavior": {"summary": "Create the implementation artifact."},
            "affected_surfaces": {
                "routes": ["situation_assessment"],
                "tools": ["get_latest_results"],
                "skills": ["vcp_breakouts_with_fundamentals"] if proposal_type == "skill_proposal" else [],
                "reports": ["reports/latest/results_analysis.html"] if proposal_type == "report_validation_proposal" else [],
            },
            "generated_test_cases": [{"name": "test_case", "input": "user input", "assertions": ["calls tool"]}],
            "expected_tool_calls": ["get_latest_results"],
            "must_not_call_rules": ["Do not mutate runtime code during proposal promotion."],
            "acceptance_criteria": ["Implementation task is explicit."],
            **dict(payload or {}),
        },
    }


def test_route_or_tool_promotion_creates_backlog_artifact_not_runtime_code(tmp_path):
    from terminal.learning.promotion import promote_learning_proposal

    repo = FakePromotionRepo([_proposal(10, "tool_proposal")])

    result = promote_learning_proposal(10, repository=repo, output_dir=tmp_path)

    assert result.ok is True
    assert result.status_after == "validated"
    assert result.artifact_path == tmp_path / "proposal_10_tool_proposal.md"
    text = result.artifact_path.read_text(encoding="utf-8")
    assert "terminal/tools.py" in text
    assert "Do not mutate runtime code during proposal promotion." in text
    assert repo.status_updates == [(10, "validated")]
    assert repo.promotion_runs[0]["status"] == "validated"
    assert repo.promotion_runs[0]["promotion_payload"]["artifact_path"] == str(result.artifact_path)


def test_proposal_cannot_jump_from_proposed_to_production():
    from terminal.learning.promotion import promote_learning_proposal

    repo = FakePromotionRepo([_proposal(11, "skill_proposal", status="proposed")])

    result = promote_learning_proposal(11, repository=repo, target_status="production", approve_production=False)

    assert result.ok is False
    assert result.status_after == "proposed"
    assert "proposal must be review_pending before promotion" in result.message
    assert repo.status_updates == []


def test_skill_prompt_report_and_deprecation_promotions_create_typed_artifacts(tmp_path):
    from terminal.learning.promotion import promote_learning_proposal

    repo = FakePromotionRepo(
        [
            _proposal(
                12,
                "skill_proposal",
                payload={
                    "validation_evidence": {
                        "schema_validation": "pass",
                        "sql_safety": "pass",
                        "fixture_execution": "pass",
                        "reviewer_approval": "pass",
                    }
                },
            ),
            _proposal(13, "prompt_proposal"),
            _proposal(14, "report_validation_proposal"),
            _proposal(15, "deprecation_proposal", payload={"deprecation_evidence": {"replacement": "new_skill"}}),
        ]
    )

    results = [promote_learning_proposal(proposal_id, repository=repo, output_dir=tmp_path) for proposal_id in [12, 13, 14, 15]]

    assert [result.promotion_kind for result in results] == [
        "skill_lifecycle_handoff",
        "prompt_review_artifact",
        "report_validation_task",
        "deprecation_task",
    ]
    assert all(result.artifact_path and result.artifact_path.exists() for result in results)
    assert repo.status_updates == [(12, "validated"), (13, "validated"), (14, "validated"), (15, "validated")]


def test_reject_learning_proposal_marks_deprecated_and_records_run():
    from terminal.learning.promotion import reject_learning_proposal

    repo = FakePromotionRepo([_proposal(16, "tool_proposal")])

    result = reject_learning_proposal(16, repository=repo, reason="not useful")

    assert result.ok is True
    assert result.status_after == "deprecated"
    assert repo.status_updates == [(16, "deprecated")]
    assert repo.promotion_runs[0]["promotion_payload"]["reason"] == "not useful"


def test_agent_adda_parser_accepts_learning_promotion_commands():
    from agent_adda.cli import build_parser

    parser = build_parser()
    assert parser.parse_args(["learning", "proposals", "--status", "review_pending"]).learning_command == "proposals"
    assert parser.parse_args(["learning", "show", "10"]).proposal_id == 10
    assert parser.parse_args(["learning", "promote", "10"]).proposal_id == 10
    reject = parser.parse_args(["learning", "reject", "10", "--reason", "duplicate"])
    assert reject.reason == "duplicate"
