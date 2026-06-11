from __future__ import annotations


class FakeAuditRepo:
    def __init__(self):
        self.patterns = [
            {
                "pattern_id": 1,
                "status": "observed",
                "pattern_payload": {
                    "pattern_key": "workflow:daily_refresh_report_review_email",
                    "pattern_type": "recurring_workflow_chain",
                    "label": "daily_refresh_report_review_email",
                    "frequency": 4,
                    "score": 72,
                    "priority": "high",
                },
            },
            {
                "pattern_id": 2,
                "status": "observed",
                "pattern_payload": {
                    "pattern_key": "fallback_failure:missing required tool: get_latest_results",
                    "pattern_type": "repeated_llm_fallback_failure",
                    "label": "missing required tool: get_latest_results",
                    "frequency": 3,
                    "score": 69,
                    "priority": "high",
                },
            },
        ]
        self.proposals = [
            {
                "proposal_id": 10,
                "proposal_type": "tool_proposal",
                "title": "Add latest results tool",
                "status": "validated",
                "source_pattern_id": 2,
                "proposal_payload": {"observed_pattern": {"pattern_key": "fallback_failure:missing required tool: get_latest_results"}},
            },
            {
                "proposal_id": 11,
                "proposal_type": "workflow_proposal",
                "title": "Automate daily refresh",
                "status": "deprecated",
                "source_pattern_id": 1,
                "proposal_payload": {"observed_pattern": {"pattern_key": "workflow:daily_refresh_report_review_email"}},
            },
        ]
        self.promotion_runs = [
            {"promotion_run_id": 30, "proposal_id": 10, "status": "validated", "promotion_payload": {"artifact_path": "reports/learning/backlog/proposal_10.md"}},
            {"promotion_run_id": 31, "proposal_id": 11, "status": "deprecated", "promotion_payload": {"reason": "duplicate"}},
        ]
        self.saved_audits = []

    def list_patterns(self, status=None, limit=None):
        rows = list(self.patterns)
        if status:
            rows = [row for row in rows if row.get("status") == status]
        return rows[:limit] if limit else rows

    def list_proposals(self, status=None):
        rows = list(self.proposals)
        if status:
            rows = [row for row in rows if row.get("status") == status]
        return rows

    def list_promotion_runs(self, limit=None):
        return self.promotion_runs[:limit] if limit else list(self.promotion_runs)

    def record_learning_audit(self, audit):
        self.saved_audits.append(dict(audit))
        return 5001


def test_learning_audit_links_patterns_proposals_and_promotions(tmp_path):
    from terminal.learning.audit import generate_learning_audit

    repo = FakeAuditRepo()

    result = generate_learning_audit(repository=repo, window="14d", output_dir=tmp_path, save=True)

    assert result.audit_id == 5001
    assert result.markdown_path == tmp_path / "learning_audit_14d.md"
    assert result.html_path == tmp_path / "learning_audit_14d.html"
    markdown = result.markdown_path.read_text(encoding="utf-8")
    assert "daily_refresh_report_review_email" in markdown
    assert "missing required tool: get_latest_results" in markdown
    assert "Add latest results tool" in markdown
    assert "reports/learning/backlog/proposal_10.md" in markdown
    assert "Recommended Next Backlog Tasks" in markdown
    assert "hidden model reasoning" not in markdown.lower()
    assert repo.saved_audits[0]["audit_type"] == "fortnightly_learning"
    assert repo.saved_audits[0]["audit_payload"]["window"] == "14d"


def test_agent_adda_parser_accepts_learning_audit_command():
    from agent_adda.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(["learning", "audit", "--window", "14d", "--output-dir", "reports/learning"])

    assert args.command == "learning"
    assert args.learning_command == "audit"
    assert args.window == "14d"
    assert args.output_dir == "reports/learning"
