from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal, Mapping

from terminal.skills.sql_safety import validate_sql_template
from terminal.skills.store_schema import RUNTIME_STATUSES, validate_skill_card_contract


ReviewAction = Literal["select", "merge", "ask_clarification", "fallback_to_router", "reject"]

DETERMINISTIC_FALLBACK_THRESHOLD = 0.90
RELEVANCE_MIN_SIGNAL = 0.20
MERGE_SCORE_GAP = 0.05
_TIMEFRAME_RE = re.compile(
    r"\b(?:\d+\s*(?:d|day|days|w|week|weeks|m|month|months|y|year|years)|"
    r"today|intraday|daily|weekly|monthly|quarter|quarterly|last\s+\d+)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ReviewDecision:
    decision: ReviewAction
    selected_skill_id: str | None = None
    selected_version: int | None = None
    candidate_ids: tuple[str, ...] = ()
    reason: str = ""
    missing_inputs: tuple[str, ...] = ()
    findings: tuple[str, ...] = ()
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.decision not in {"select", "merge", "ask_clarification", "fallback_to_router", "reject"}:
            raise ValueError("invalid review decision")
        object.__setattr__(self, "candidate_ids", _string_tuple(self.candidate_ids))
        object.__setattr__(self, "missing_inputs", _string_tuple(self.missing_inputs))
        object.__setattr__(self, "findings", _string_tuple(self.findings))
        object.__setattr__(self, "confidence", _bounded(self.confidence))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "selected_skill_id": self.selected_skill_id,
            "selected_version": self.selected_version,
            "candidate_ids": list(self.candidate_ids),
            "reason": self.reason,
            "missing_inputs": list(self.missing_inputs),
            "findings": list(self.findings),
            "confidence": self.confidence,
            "metadata": dict(self.metadata),
        }


def review_skill_candidates(
    query: str,
    candidates: Any,
    *,
    required_entities: Iterable[str] | None = None,
    available_entities: Iterable[str] | None = None,
    required_tools: Iterable[str] | None = None,
    available_tools: Iterable[str] | None = None,
    required_tables: Iterable[str] | None = None,
    available_tables: Iterable[str] | None = None,
    required_output_contract: Iterable[str] | None = None,
    deterministic_intent: str | None = None,
    deterministic_confidence: float = 0.0,
    min_confidence: float = 0.35,
) -> ReviewDecision:
    if deterministic_intent and deterministic_confidence >= DETERMINISTIC_FALLBACK_THRESHOLD:
        return ReviewDecision(
            decision="fallback_to_router",
            reason="deterministic_route_is_stronger",
            confidence=deterministic_confidence,
            metadata={"deterministic_intent": deterministic_intent},
        )

    normalized = _normalize_candidates(candidates)
    if not normalized:
        return ReviewDecision(decision="reject", reason="no_candidates", findings=("no_candidates",))

    external_missing = _missing_required_external_inputs(
        required_entities=required_entities,
        available_entities=available_entities,
        required_tools=required_tools,
        available_tools=available_tools,
        required_tables=required_tables,
        available_tables=available_tables,
    )
    if external_missing:
        return ReviewDecision(
            decision="ask_clarification",
            reason="required_context_missing",
            missing_inputs=external_missing,
            findings=("missing_required_context",),
            candidate_ids=tuple(item["skill_id"] for item in normalized[:3]),
        )

    viable: list[dict[str, Any]] = []
    rejected_findings: list[str] = []
    for candidate in normalized:
        findings = _candidate_findings(
            query,
            candidate,
            required_tools=required_tools,
            required_tables=required_tables,
            required_output_contract=required_output_contract,
            min_confidence=min_confidence,
        )
        missing_inputs = [finding.removeprefix("missing_input:") for finding in findings if finding.startswith("missing_input:")]
        if missing_inputs:
            return ReviewDecision(
                decision="ask_clarification",
                reason="candidate_requires_more_input",
                missing_inputs=tuple(missing_inputs),
                findings=tuple(findings),
                candidate_ids=(candidate["skill_id"],),
                confidence=_candidate_confidence(candidate),
            )
        if findings:
            rejected_findings.extend(findings)
            continue
        viable.append(candidate)

    if not viable:
        return ReviewDecision(
            decision="reject",
            reason="no_reviewable_candidate",
            findings=tuple(sorted(dict.fromkeys(rejected_findings or ["no_reviewable_candidate"]))),
            candidate_ids=tuple(item["skill_id"] for item in normalized[:3]),
            confidence=_candidate_confidence(normalized[0]),
        )

    top = viable[0]
    if len(viable) >= 2 and _should_merge(top, viable[1]):
        pair = (top, viable[1])
        return ReviewDecision(
            decision="merge",
            reason="close_complementary_candidates",
            candidate_ids=tuple(item["skill_id"] for item in pair),
            findings=("merge_close_complementary_candidates",),
            confidence=min(_candidate_confidence(top), _candidate_confidence(viable[1])),
            metadata={"domains": [item.get("domain") for item in pair]},
        )

    return ReviewDecision(
        decision="select",
        selected_skill_id=top["skill_id"],
        selected_version=top["version"],
        candidate_ids=(top["skill_id"],),
        reason="selected_reviewable_candidate",
        findings=("selected",),
        confidence=_candidate_confidence(top),
    )


def _normalize_candidates(candidates: Any) -> list[dict[str, Any]]:
    if candidates is None:
        return []
    if getattr(candidates, "abstain", False) is True and getattr(candidates, "selected", None) is None:
        raw_candidates = list(getattr(candidates, "candidates", ()) or ())
        if not raw_candidates:
            return []
    elif hasattr(candidates, "candidates"):
        raw_candidates = list(getattr(candidates, "candidates") or ())
    elif isinstance(candidates, Iterable) and not isinstance(candidates, (str, bytes, Mapping)):
        raw_candidates = list(candidates)
    else:
        raw_candidates = [candidates]

    normalized = [_normalize_candidate(item) for item in raw_candidates]
    normalized.sort(key=lambda item: (_candidate_confidence(item), item["skill_id"]), reverse=True)
    return normalized


def _normalize_candidate(candidate: Any) -> dict[str, Any]:
    if hasattr(candidate, "to_dict"):
        payload = candidate.to_dict()
    elif isinstance(candidate, Mapping):
        payload = dict(candidate)
    else:
        payload = dict(candidate)
    if "skill_id" not in payload and "id" in payload:
        payload["skill_id"] = payload["id"]
    metadata = dict(payload.get("metadata") or {})
    return {
        **payload,
        "skill_id": str(payload.get("skill_id") or ""),
        "version": int(payload.get("version") or payload.get("skill_version") or 1),
        "status": str(payload.get("status") or ""),
        "domain": str(payload.get("domain") or ""),
        "score": _bounded(payload.get("score", payload.get("confidence"))),
        "confidence": _bounded(payload.get("confidence", payload.get("score"))),
        "vector_score": _bounded(payload.get("vector_score")),
        "tag_score": _bounded(payload.get("tag_score")),
        "intent_score": _bounded(metadata.get("intent_score", payload.get("intent_score"))),
        "matched_tags": tuple(_strings(payload.get("matched_tags"))),
        "metadata": metadata,
    }


def _candidate_findings(
    query: str,
    candidate: dict[str, Any],
    *,
    required_tools: Iterable[str] | None,
    required_tables: Iterable[str] | None,
    required_output_contract: Iterable[str] | None,
    min_confidence: float,
) -> list[str]:
    findings: list[str] = []
    metadata = dict(candidate.get("metadata") or {})
    if not candidate.get("skill_id"):
        findings.append("candidate_skill_id_missing")
    if candidate.get("status") not in RUNTIME_STATUSES:
        findings.append("candidate_not_runtime_eligible")
    if _candidate_confidence(candidate) < min_confidence:
        findings.append("candidate_confidence_below_threshold")
    if candidate.get("validation_errors") or metadata.get("validation_errors"):
        findings.append("candidate_has_validation_errors")

    contract_errors = validate_skill_card_contract(_card_contract_payload(candidate))
    ignored_contract_errors = {"evidence_required must be an object"}
    actionable_contract_errors = [item for item in contract_errors if item not in ignored_contract_errors]
    if actionable_contract_errors:
        findings.append("candidate_contract_invalid")

    if _requires_timeframe(candidate) and not _query_has_timeframe(query):
        findings.append("missing_input:timeframe")

    if _is_irrelevant_match(query, candidate):
        findings.append("candidate_does_not_answer_query")

    missing_tools = _missing_values(required_tools, _candidate_tools(candidate))
    if missing_tools:
        findings.extend(f"missing_tool:{item}" for item in missing_tools)

    missing_tables = _missing_values(required_tables, _candidate_tables(candidate))
    if missing_tables:
        findings.extend(f"missing_table:{item}" for item in missing_tables)

    missing_output = _missing_values(required_output_contract, _candidate_output_contract(candidate))
    if missing_output:
        findings.extend(f"missing_output_contract:{item}" for item in missing_output)

    if _has_unsafe_sql(candidate):
        findings.append("unsafe_sql_template")

    return sorted(dict.fromkeys(findings))


def _card_contract_payload(candidate: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(candidate.get("metadata") or {})
    return {
        "id": candidate.get("skill_id"),
        "version": candidate.get("version"),
        "status": candidate.get("status"),
        "domain": candidate.get("domain"),
        "title": candidate.get("title") or candidate.get("skill_id"),
        "description": metadata.get("description") or candidate.get("title") or candidate.get("skill_id"),
        "input_patterns": list(_strings(metadata.get("input_patterns") or candidate.get("input_patterns"))),
        "tags": list(_strings(metadata.get("tags") or candidate.get("matched_tags"))),
        "evidence_required": {"tables": list(_candidate_tables(candidate))},
        "output_contract": list(_candidate_output_contract(candidate)),
        "validation_rules": list(_strings(metadata.get("validation_rules"))) or ["runtime_reviewer_gate"],
        "tool_plan_template": list(metadata.get("tool_plan_template") or []),
        "sql_templates": list(metadata.get("sql_templates") or []),
    }


def _missing_required_external_inputs(
    *,
    required_entities: Iterable[str] | None,
    available_entities: Iterable[str] | None,
    required_tools: Iterable[str] | None,
    available_tools: Iterable[str] | None,
    required_tables: Iterable[str] | None,
    available_tables: Iterable[str] | None,
) -> tuple[str, ...]:
    missing: list[str] = []
    missing.extend(f"entity:{item}" for item in _missing_values(required_entities, available_entities))
    missing.extend(f"tool:{item}" for item in _missing_values(required_tools, available_tools))
    missing.extend(f"table:{item}" for item in _missing_values(required_tables, available_tables))
    return tuple(missing)


def _is_irrelevant_match(query: str, candidate: dict[str, Any]) -> bool:
    if candidate["tag_score"] >= RELEVANCE_MIN_SIGNAL or candidate["intent_score"] >= RELEVANCE_MIN_SIGNAL:
        return False
    searchable = " ".join(
        [
            str(candidate.get("title") or ""),
            str(candidate.get("domain") or ""),
            " ".join(candidate.get("matched_tags") or ()),
            " ".join(_strings((candidate.get("metadata") or {}).get("tags"))),
        ]
    )
    return not (_token_set(query) & _token_set(searchable))


def _requires_timeframe(candidate: dict[str, Any]) -> bool:
    required = set(_strings((candidate.get("metadata") or {}).get("required_inputs")))
    return "timeframe" in required


def _query_has_timeframe(query: str) -> bool:
    return bool(_TIMEFRAME_RE.search(query or ""))


def _has_unsafe_sql(candidate: dict[str, Any]) -> bool:
    for template in (candidate.get("metadata") or {}).get("sql_templates") or []:
        if not isinstance(template, Mapping):
            return True
        if str(template.get("safety_status") or "").lower() != "passed":
            return True
        result = validate_sql_template(str(template.get("sql") or ""))
        if not result.passed:
            return True
    return False


def _candidate_tools(candidate: dict[str, Any]) -> tuple[str, ...]:
    metadata = dict(candidate.get("metadata") or {})
    explicit = _strings(metadata.get("available_tools") or candidate.get("available_tools"))
    tool_plan = [
        item.get("tool_name") or item.get("tool")
        for item in metadata.get("tool_plan_template") or []
        if isinstance(item, Mapping)
    ]
    return tuple(sorted(set(explicit + _strings(tool_plan))))


def _candidate_tables(candidate: dict[str, Any]) -> tuple[str, ...]:
    metadata = dict(candidate.get("metadata") or {})
    explicit = _strings(metadata.get("available_tables") or candidate.get("available_tables"))
    evidence_tables = _strings((metadata.get("evidence_required") or {}).get("tables") if isinstance(metadata.get("evidence_required"), Mapping) else None)
    return tuple(sorted(set(explicit + evidence_tables)))


def _candidate_output_contract(candidate: dict[str, Any]) -> tuple[str, ...]:
    metadata = dict(candidate.get("metadata") or {})
    return tuple(sorted(set(_strings(metadata.get("output_contract") or candidate.get("output_contract")))))


def _should_merge(first: dict[str, Any], second: dict[str, Any]) -> bool:
    if abs(_candidate_confidence(first) - _candidate_confidence(second)) > MERGE_SCORE_GAP:
        return False
    first_metadata = dict(first.get("metadata") or {})
    second_metadata = dict(second.get("metadata") or {})
    if first_metadata.get("complementary") is True or second_metadata.get("complementary") is True:
        return True
    return str(first.get("domain") or "") != str(second.get("domain") or "")


def _candidate_confidence(candidate: dict[str, Any]) -> float:
    return _bounded(candidate.get("confidence", candidate.get("score")))


def _missing_values(required: Iterable[str] | None, available: Iterable[str] | None) -> tuple[str, ...]:
    required_set = set(_strings(required))
    if not required_set:
        return ()
    available_set = set(_strings(available))
    return tuple(sorted(required_set - available_set))


def _token_set(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9_]+", (text or "").lower()) if len(token) > 2}


def _strings(values: Iterable[Any] | Any | None) -> list[str]:
    if values in (None, "", [], {}):
        return []
    if isinstance(values, str):
        items = [values]
    elif isinstance(values, Iterable):
        items = list(values)
    else:
        items = [values]
    return [str(item).strip().lower() for item in items if str(item).strip()]


def _string_tuple(values: Iterable[Any] | Any | None) -> tuple[str, ...]:
    return tuple(_strings(values))


def _bounded(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))
