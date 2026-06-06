from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .code_policy import audit_python_tools
from .reviewer import ReviewDecision, deterministic_review
from .schema import validate_skill_card
from .schema_auditor import audit_skill_card
from .schema_catalog import SchemaCatalog, default_schema_catalog
from .test_runner import run_card_python_tool_tests


Reviewer = Callable[[dict, list[str]], ReviewDecision]
Healer = Callable[[dict, list[str]], dict]


@dataclass(frozen=True)
class PipelineResult:
    card: dict
    attempts: int
    findings: list[str]
    history: list[dict]


def _collect_findings(card: dict, catalog: SchemaCatalog) -> list[str]:
    findings: list[str] = []
    findings.extend(validate_skill_card(card, generated_only=True))
    findings.extend(audit_skill_card(card, catalog))
    python_findings = audit_python_tools(card)
    findings.extend(python_findings)
    if not python_findings:
        findings.extend(run_card_python_tool_tests(card))
    return sorted(dict.fromkeys(findings))


def run_review_heal_pipeline(
    card: dict,
    *,
    reviewer: Reviewer | None = None,
    healer: Healer | None = None,
    schema_catalog: SchemaCatalog | None = None,
    max_attempts: int = 3,
) -> PipelineResult:
    catalog = schema_catalog or default_schema_catalog()
    review = reviewer or deterministic_review
    current = dict(card)
    history: list[dict] = []

    for attempt in range(1, max(1, max_attempts) + 1):
        findings = _collect_findings(current, catalog)
        decision = review(current, findings)
        history.append(
            {
                "attempt": attempt,
                "status": decision.status,
                "findings": list(decision.findings),
                "rationale": decision.rationale,
            }
        )

        if decision.status == "pass" and not findings:
            accepted = dict(current)
            accepted["status"] = "review_pending"
            accepted.pop("validation_errors", None)
            accepted["review"] = {
                "status": decision.status,
                "findings": [],
                "rationale": decision.rationale,
                "attempts": attempt,
            }
            return PipelineResult(card=accepted, attempts=attempt, findings=[], history=history)

        if decision.status == "reject" or healer is None or attempt >= max_attempts:
            failed = dict(current)
            failed["status"] = "test_failed"
            failed["validation_errors"] = list(decision.findings or findings)
            failed["review"] = {
                "status": decision.status,
                "findings": list(decision.findings or findings),
                "rationale": decision.rationale,
                "attempts": attempt,
            }
            return PipelineResult(
                card=failed,
                attempts=attempt,
                findings=list(decision.findings or findings),
                history=history,
            )

        current = healer(current, list(decision.findings or findings))
        current["status"] = "generated"

    failed = dict(current)
    failed["status"] = "test_failed"
    failed["validation_errors"] = ["pipeline exhausted without decision"]
    return PipelineResult(card=failed, attempts=max_attempts, findings=failed["validation_errors"], history=history)
