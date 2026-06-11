#!/usr/bin/env bash
# End-to-end smoke for the Agent Adda learning loop:
#   mine patterns -> generate proposals -> validate proposals -> promote one artifact
#   -> generate audit -> verify audit HTML with Playwright.
#
# Run from anywhere:
#   bash scripts/smoke_learning_loop.sh
#
# Optional:
#   OUTPUT_DIR=reports/learning/e2e PYTHON=.venv/bin/python bash scripts/smoke_learning_loop.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY="${PYTHON:-$ROOT/.venv/bin/python}"
OUTPUT="${OUTPUT_DIR:-reports/learning/e2e}"

"$PY" - <<'PY'
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

from terminal.learning.audit import generate_learning_audit
from terminal.learning.pattern_miner import mine_learning_patterns
from terminal.learning.promotion import promote_learning_proposal
from terminal.learning.proposal_generator import generate_learning_proposals
from terminal.learning.proposal_validator import validate_learning_proposal


class SmokeLearningRepo:
    def __init__(self):
        self.patterns = []
        self.proposals = []
        self.promotion_runs = []
        self.audits = []
        self.next_pattern_id = 1
        self.next_proposal_id = 10
        self.next_promotion_id = 100
        self.next_audit_id = 1000

    def save_pattern(self, record):
        row = {"pattern_id": self.next_pattern_id, **record}
        self.next_pattern_id += 1
        self.patterns.append(row)
        return row["pattern_id"]

    def list_patterns(self, status=None, limit=None):
        rows = list(self.patterns)
        if status:
            rows = [row for row in rows if row.get("status") == status]
        return rows[:limit] if limit else rows

    def save_proposal(self, record):
        row = {"proposal_id": self.next_proposal_id, **record}
        self.next_proposal_id += 1
        self.proposals.append(row)
        return row["proposal_id"]

    def list_proposals(self, status=None):
        rows = list(self.proposals)
        if status:
            rows = [row for row in rows if row.get("status") == status]
        return rows

    def get_proposal(self, proposal_id):
        return next((row for row in self.proposals if row["proposal_id"] == proposal_id), None)

    def update_proposal_status(self, proposal_id, status):
        self.get_proposal(proposal_id)["status"] = status
        return proposal_id

    def record_proposal_validation_run(self, run):
        return 9000

    def record_promotion_run(self, run):
        row = {"promotion_run_id": self.next_promotion_id, **run}
        self.next_promotion_id += 1
        self.promotion_runs.append(row)
        return row["promotion_run_id"]

    def list_promotion_runs(self, limit=None):
        return self.promotion_runs[:limit] if limit else list(self.promotion_runs)

    def record_learning_audit(self, audit):
        row = {"audit_id": self.next_audit_id, **audit}
        self.next_audit_id += 1
        self.audits.append(row)
        return row["audit_id"]


def sample_events():
    return [
        {
            "event_id": 1,
            "event_ts": "2026-06-06T09:00:00+00:00",
            "raw_query": "latest quarterly results analysis",
            "normalized_query": "latest quarterly results analysis",
            "selected_intent": "llm_driven_fallback",
            "route_type": "agent_query",
            "detected_entities": [],
            "tools_executed": ["get_latest_results"],
            "artifacts": [],
            "errors": ["missing required tool: get_latest_results"],
            "missing_evidence": ["scores.quarterly_results"],
            "payload": {},
        },
        {
            "event_id": 2,
            "event_ts": "2026-06-07T09:00:00+00:00",
            "raw_query": "latest quarterly results analysis",
            "normalized_query": "latest quarterly results analysis",
            "selected_intent": "llm_driven_fallback",
            "route_type": "agent_query",
            "detected_entities": [],
            "tools_executed": ["get_latest_results"],
            "artifacts": [],
            "errors": ["missing required tool: get_latest_results"],
            "missing_evidence": ["scores.quarterly_results"],
            "payload": {},
        },
    ]


def sample_chains():
    return [
        {
            "chain_id": 1,
            "started_at": "2026-06-06T09:00:00+00:00",
            "chain_payload": {"chain_type": "fallback_failure_recovery", "errors": ["missing required tool"]},
        },
        {
            "chain_id": 2,
            "started_at": "2026-06-07T09:00:00+00:00",
            "chain_payload": {"chain_type": "fallback_failure_recovery", "errors": ["missing required tool"]},
        },
    ]


repo = SmokeLearningRepo()
output_dir = Path(os.environ.get("OUTPUT_DIR", "reports/learning/e2e"))
backlog_dir = output_dir / "backlog"

pattern_result = mine_learning_patterns(
    events=sample_events(),
    workflow_chains=sample_chains(),
    start_date="2026-05-25",
    end_date="2026-06-07",
)
assert pattern_result.patterns, "expected mined patterns"
for pattern in pattern_result.patterns:
    repo.save_pattern(pattern.to_record())

proposal_result = generate_learning_proposals(repo.list_patterns(status="observed"))
assert proposal_result.proposals, "expected generated proposals"
for proposal in proposal_result.proposals:
    repo.save_proposal(proposal.to_record())

for proposal in list(repo.proposals):
    validation = validate_learning_proposal(proposal)
    repo.update_proposal_status(proposal["proposal_id"], validation.status_after)
    repo.record_proposal_validation_run(validation.to_validation_run())

valid = [proposal for proposal in repo.proposals if proposal["status"] == "review_pending"]
assert valid, "expected at least one review_pending proposal"
promotion = promote_learning_proposal(valid[0]["proposal_id"], repository=repo, output_dir=backlog_dir)
assert promotion.ok, promotion.message

audit = generate_learning_audit(repository=repo, window="14d", output_dir=output_dir, save=True)
assert audit.html_path.exists(), audit.html_path

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(audit.html_path.resolve().as_uri())
    title = page.locator("h1").inner_text()
    body = page.locator("body").inner_text()
    assert "Agent Adda Fortnightly Learning Audit" in title
    assert "Recurring Failures" in body
    assert "missing required tool: get_latest_results" in body
    assert "Promoted Proposals" in body
    assert "Recommended Next Backlog Tasks" in body
    browser.close()

print("E2E_OK")
print(f"patterns={len(repo.patterns)} proposals={len(repo.proposals)} promotions={len(repo.promotion_runs)} audits={len(repo.audits)}")
print(f"audit_html={audit.html_path}")
print(f"audit_md={audit.markdown_path}")
print(f"promotion_artifact={promotion.artifact_path}")
PY
