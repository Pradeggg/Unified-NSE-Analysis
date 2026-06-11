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

IDENTITY_KEYS = (
    "id",
    "version",
    "domain",
    "title",
    "description",
    "input_patterns",
    "tags",
    "evidence_required",
    "output_contract",
    "validation_rules",
    "generation_model",
    "created_by",
    "created_at",
)


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


def _missing_value(value: object) -> bool:
    return value in (None, "", [], {})


def _merge_healed_card(original: dict, healed: dict) -> tuple[dict, list[str]]:
    merged = dict(original)
    merged.update(healed)
    findings: list[str] = []
    for key in IDENTITY_KEYS:
        if _missing_value(merged.get(key)) and not _missing_value(original.get(key)):
            merged[key] = original.get(key)
            findings.append(f"healer omitted {key}; preserved original value")
    return merged, findings


def _failed_result(
    card: dict,
    *,
    attempts: int,
    findings: list[str],
    history: list[dict],
    status: str,
    rationale: str,
) -> PipelineResult:
    failed = dict(card)
    failed["status"] = "test_failed"
    failed["validation_errors"] = list(findings)
    failed["review"] = {
        "status": status,
        "findings": list(findings),
        "rationale": rationale,
        "attempts": attempts,
    }
    return PipelineResult(card=failed, attempts=attempts, findings=list(findings), history=history)


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
            return _failed_result(
                current,
                attempts=attempt,
                findings=list(decision.findings or findings),
                history=history,
                status=decision.status,
                rationale=decision.rationale,
            )

        try:
            healed = healer(current, list(decision.findings or findings))
        except Exception as exc:
            healing_findings = list(decision.findings or findings)
            healing_findings.append(f"healer failed: {type(exc).__name__}: {exc}")
            return _failed_result(
                current,
                attempts=attempt,
                findings=healing_findings,
                history=history,
                status="healer_error",
                rationale=decision.rationale,
            )
        if not isinstance(healed, dict):
            healing_findings = list(decision.findings or findings)
            healing_findings.append(f"healer returned {type(healed).__name__}; expected object")
            return _failed_result(
                current,
                attempts=attempt,
                findings=healing_findings,
                history=history,
                status="healer_error",
                rationale=decision.rationale,
            )
        current, merge_findings = _merge_healed_card(current, healed)
        if merge_findings:
            history[-1]["findings"] = list(history[-1]["findings"]) + merge_findings
        current["status"] = "generated"

    failed = dict(current)
    failed["status"] = "test_failed"
    failed["validation_errors"] = ["pipeline exhausted without decision"]
    return PipelineResult(card=failed, attempts=max_attempts, findings=failed["validation_errors"], history=history)
