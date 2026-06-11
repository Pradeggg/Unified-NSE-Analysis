from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from terminal.learning.repository import LearningRepository


PROPOSAL_TYPES = {
    "route_proposal",
    "tool_proposal",
    "skill_proposal",
    "prompt_proposal",
    "report_validation_proposal",
    "workflow_proposal",
    "deprecation_proposal",
}


@dataclass(frozen=True)
class ProposalValidationResult:
    proposal_id: int
    proposal_type: str
    status_before: str
    status_after: str
    checks: list[dict[str, Any]]
    findings: list[str] = field(default_factory=list)
    backlog_snippet: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status_after == "review_pending"

    def to_validation_run(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "status_before": self.status_before,
            "status_after": self.status_after,
            "checks": self.checks,
            "findings": self.findings,
        }


@dataclass(frozen=True)
class ProposalValidationBatchResult:
    results: list[ProposalValidationResult]
    validation_run_ids: list[int] = field(default_factory=list)


def validate_learning_proposal(proposal: Mapping[str, Any]) -> ProposalValidationResult:
    normalized = _normalize_proposal(proposal)
    findings: list[str] = []
    checks: list[dict[str, Any]] = []

    _check_required_payload(normalized, findings)
    _check_generated_tests(normalized, findings)
    _check_type_specific_rules(normalized, findings)

    status_after = "test_failed" if findings else "review_pending"
    for name in ["proposal_payload", "generated_test_cases", "type_specific_rules"]:
        checks.append({"name": name, "status": "fail" if findings else "pass"})

    backlog_snippet = _build_backlog_snippet(normalized) if not findings else {}
    return ProposalValidationResult(
        proposal_id=normalized["proposal_id"],
        proposal_type=normalized["proposal_type"],
        status_before=normalized["status_before"],
        status_after=status_after,
        checks=checks,
        findings=findings,
        backlog_snippet=backlog_snippet,
    )


def validate_and_store_learning_proposals(
    *,
    repository: Any | None = None,
    status: str = "proposed",
) -> ProposalValidationBatchResult:
    repo = repository or LearningRepository()
    proposals = repo.list_proposals(status=status)
    results = [validate_learning_proposal(proposal) for proposal in proposals]
    validation_ids: list[int] = []
    for result in results:
        repo.update_proposal_status(result.proposal_id, result.status_after)
        validation_ids.append(int(repo.record_proposal_validation_run(result.to_validation_run())))
    return ProposalValidationBatchResult(results=results, validation_run_ids=validation_ids)


def _check_required_payload(proposal: dict[str, Any], findings: list[str]) -> None:
    if proposal["proposal_type"] not in PROPOSAL_TYPES:
        findings.append(f"unsupported proposal_type: {proposal['proposal_type']}")
    payload = proposal["payload"]
    for key in [
        "observed_pattern",
        "proposed_behavior",
        "affected_surfaces",
        "generated_test_cases",
        "expected_tool_calls",
        "must_not_call_rules",
        "acceptance_criteria",
    ]:
        if key not in payload:
            findings.append(f"{key} is required")
    if not _strings(payload.get("acceptance_criteria")):
        findings.append("acceptance_criteria must not be empty")


def _check_generated_tests(proposal: dict[str, Any], findings: list[str]) -> None:
    tests = proposal["payload"].get("generated_test_cases")
    if not isinstance(tests, list) or not tests:
        findings.append("generated_test_cases must include at least one test")
        return
    for index, test in enumerate(tests):
        if not isinstance(test, Mapping):
            findings.append(f"generated_test_cases[{index}] must be an object")
            continue
        if not str(test.get("name") or "").strip():
            findings.append(f"generated_test_cases[{index}].name is required")
        if not str(test.get("input") or "").strip():
            findings.append(f"generated_test_cases[{index}].input is required")
        if not _strings(test.get("assertions")):
            findings.append(f"generated_test_cases[{index}].assertions must not be empty")


def _check_type_specific_rules(proposal: dict[str, Any], findings: list[str]) -> None:
    proposal_type = proposal["proposal_type"]
    payload = proposal["payload"]
    if proposal_type == "skill_proposal":
        evidence = payload.get("validation_evidence") if isinstance(payload.get("validation_evidence"), Mapping) else {}
        required = {
            "schema_validation": "schema_validation=pass",
            "sql_safety": "sql_safety=pass",
            "fixture_execution": "fixture_execution=pass",
            "reviewer_approval": "reviewer_approval=pass",
        }
        for key, label in required.items():
            if str(evidence.get(key) or "").lower() != "pass":
                findings.append(f"skill proposal requires {label}")
    if proposal_type == "deprecation_proposal":
        evidence = payload.get("deprecation_evidence") if isinstance(payload.get("deprecation_evidence"), Mapping) else {}
        repeated_failures = int(evidence.get("repeated_failure_count") or 0)
        replacement = str(evidence.get("replacement") or "").strip()
        if repeated_failures < 2 and not replacement:
            findings.append("deprecation proposal requires repeated failure evidence or replacement target")


def _build_backlog_snippet(proposal: dict[str, Any]) -> dict[str, Any]:
    payload = proposal["payload"]
    proposal_type = proposal["proposal_type"]
    surfaces = payload.get("affected_surfaces") if isinstance(payload.get("affected_surfaces"), Mapping) else {}
    files = _files_for_proposal(proposal_type, surfaces)
    tests = [f"tests/test_learning_generated_{proposal_type}_{proposal['proposal_id']}.py"]
    snippet = {
        "title": proposal["title"],
        "proposal_id": proposal["proposal_id"],
        "proposal_type": proposal_type,
        "files_to_edit": files,
        "tests_to_add": tests,
        "generated_test_cases": payload.get("generated_test_cases") or [],
        "expected_tool_calls": _strings(payload.get("expected_tool_calls")),
        "must_not_call_rules": _strings(payload.get("must_not_call_rules")),
        "acceptance_criteria": _strings(payload.get("acceptance_criteria")),
    }
    if proposal_type == "skill_proposal":
        snippet["skill_cards_to_create"] = _strings(surfaces.get("skills"))
    return snippet


def _files_for_proposal(proposal_type: str, surfaces: Mapping[str, Any]) -> list[str]:
    files: list[str] = []
    routes = set(_strings(surfaces.get("routes")))
    tools = set(_strings(surfaces.get("tools")))
    reports = set(_strings(surfaces.get("reports")))
    if proposal_type in {"route_proposal", "prompt_proposal", "workflow_proposal"} or routes:
        files.extend(["terminal/situation_assessment.py", "terminal/router/providers.py"])
    if proposal_type == "tool_proposal" or tools:
        files.append("terminal/tools.py")
    if proposal_type == "skill_proposal":
        files.extend(["terminal/skills/seed_cards/", "terminal/skills/store_schema.py"])
    if proposal_type == "report_validation_proposal" or reports:
        files.extend(["terminal/report_validation.py", "report_validation.py"])
    if proposal_type == "deprecation_proposal":
        files.append("terminal/skills/promote.py")
    return list(dict.fromkeys(files))


def _normalize_proposal(proposal: Mapping[str, Any]) -> dict[str, Any]:
    payload = proposal.get("proposal_payload") if isinstance(proposal.get("proposal_payload"), Mapping) else {}
    return {
        "proposal_id": int(proposal.get("proposal_id") or payload.get("proposal_id") or 0),
        "proposal_type": str(proposal.get("proposal_type") or payload.get("proposal_type") or ""),
        "title": str(proposal.get("title") or payload.get("title") or ""),
        "status_before": str(proposal.get("status") or "proposed"),
        "payload": dict(payload),
    }


def _strings(value: Any) -> list[str]:
    if value in (None, "", [], {}):
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [str(value)]
    if isinstance(value, (list, tuple, set, frozenset)):
        return [str(item) for item in value if str(item)]
    return [str(value)]
