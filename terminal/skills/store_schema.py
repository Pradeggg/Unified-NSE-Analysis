from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


SkillStatus = Literal["generated", "test_failed", "review_pending", "validated", "production", "deprecated"]
ReviewerStatus = Literal["pass", "needs_heal", "reject", "abstain"]

GENERATED_STATUSES: frozenset[str] = frozenset({"generated", "test_failed", "review_pending"})
RUNTIME_STATUSES: frozenset[str] = frozenset({"validated", "production"})
ALL_STATUSES: frozenset[str] = GENERATED_STATUSES | RUNTIME_STATUSES | frozenset({"deprecated"})
REVIEWER_STATUSES: frozenset[str] = frozenset({"pass", "needs_heal", "reject", "abstain"})


def _string_tuple(value: Any, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        values = (value,)
    elif isinstance(value, (list, tuple)):
        values = tuple(value)
    else:
        raise ValueError(f"{field_name} must be a string or list of strings")
    if not all(isinstance(item, str) and item for item in values):
        raise ValueError(f"{field_name} must contain only non-empty strings")
    return values


def _dict_value(value: Any, *, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")
    return dict(value)


def _list_of_dicts(value: Any, *, field_name: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"{field_name} must be a list of objects")
    return [dict(item) for item in value]


def _validate_status(status: str) -> SkillStatus:
    if status not in ALL_STATUSES:
        raise ValueError(f"status must be one of {sorted(ALL_STATUSES)}")
    return status  # type: ignore[return-value]


def _normalize_validation_rules(value: Any) -> tuple[SkillValidationRule, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError("validation_rules must be a list")
    return tuple(item if isinstance(item, SkillValidationRule) else SkillValidationRule.from_value(item) for item in value)


def _normalize_tool_templates(value: Any) -> tuple[SkillToolTemplate, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError("tool_plan_template must be a list")
    return tuple(item if isinstance(item, SkillToolTemplate) else SkillToolTemplate.from_dict(item) for item in value)


def _normalize_sql_templates(value: Any) -> tuple[SkillSQLTemplate, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError("sql_templates must be a list")
    return tuple(item if isinstance(item, SkillSQLTemplate) else SkillSQLTemplate.from_dict(item) for item in value)


def is_runtime_eligible_status(status: str) -> bool:
    return status in RUNTIME_STATUSES


def is_runtime_eligible_card(card: SkillCard | dict[str, Any]) -> bool:
    parsed = card if isinstance(card, SkillCard) else None
    if parsed is None:
        try:
            parsed = skill_card_from_dict(card)
        except ValueError:
            return False
    if parsed.status not in RUNTIME_STATUSES:
        return False
    if not parsed.validation_rules:
        return False
    if any(template.safety_status != "passed" for template in parsed.sql_templates):
        return False
    return not validate_skill_card_contract(parsed)


@dataclass(frozen=True)
class SkillEvidenceRequirement:
    tables: tuple[str, ...] = ()
    freshness: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "tables", _string_tuple(self.tables, field_name="evidence_required.tables"))
        object.__setattr__(self, "freshness", _dict_value(self.freshness, field_name="evidence_required.freshness"))
        object.__setattr__(self, "metadata", _dict_value(self.metadata, field_name="evidence_required.metadata"))

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SkillEvidenceRequirement:
        data = _dict_value(payload, field_name="evidence_required")
        known = {"tables", "freshness"}
        metadata = dict(data.get("metadata") or {})
        for key, value in data.items():
            if key not in known and key != "metadata":
                metadata[key] = value
        return cls(
            tables=_string_tuple(data.get("tables"), field_name="evidence_required.tables"),
            freshness=_dict_value(data.get("freshness"), field_name="evidence_required.freshness"),
            metadata=metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"tables": list(self.tables)}
        if self.freshness:
            payload["freshness"] = dict(self.freshness)
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


@dataclass(frozen=True)
class SkillSQLTemplate:
    name: str
    sql: str
    required_params: tuple[str, ...] = ()
    expected_columns: tuple[str, ...] = ()
    row_limit: int = 500
    safety_status: Literal["pending", "passed", "failed"] = "pending"
    safety_findings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "required_params", _string_tuple(self.required_params, field_name="required_params"))
        object.__setattr__(self, "expected_columns", _string_tuple(self.expected_columns, field_name="expected_columns"))
        object.__setattr__(self, "safety_findings", _string_tuple(self.safety_findings, field_name="safety_findings"))
        if not self.name:
            raise ValueError("sql template name is required")
        if not self.sql:
            raise ValueError("sql template sql is required")
        if self.row_limit < 1:
            raise ValueError("sql template row_limit must be positive")
        if self.safety_status not in {"pending", "passed", "failed"}:
            raise ValueError("sql template safety_status is invalid")

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SkillSQLTemplate:
        data = _dict_value(payload, field_name="sql_template")
        return cls(
            name=str(data.get("name") or data.get("template_name") or data.get("id") or ""),
            sql=str(data.get("sql") or data.get("sql_text") or data.get("template") or data.get("query") or ""),
            required_params=_string_tuple(data.get("required_params"), field_name="required_params"),
            expected_columns=_string_tuple(data.get("expected_columns"), field_name="expected_columns"),
            row_limit=int(data.get("row_limit") or 500),
            safety_status=str(data.get("safety_status") or "pending"),  # type: ignore[arg-type]
            safety_findings=_string_tuple(data.get("safety_findings"), field_name="safety_findings"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "sql": self.sql,
            "required_params": list(self.required_params),
            "expected_columns": list(self.expected_columns),
            "row_limit": self.row_limit,
            "safety_status": self.safety_status,
            "safety_findings": list(self.safety_findings),
        }


@dataclass(frozen=True)
class SkillToolTemplate:
    name: str
    tool_name: str
    params: dict[str, Any] = field(default_factory=dict)
    required: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "params", _dict_value(self.params, field_name="tool template params"))
        if not self.name:
            raise ValueError("tool template name is required")
        if not self.tool_name:
            raise ValueError("tool template tool_name is required")

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SkillToolTemplate:
        data = _dict_value(payload, field_name="tool_template")
        return cls(
            name=str(data.get("name") or data.get("id") or ""),
            tool_name=str(data.get("tool_name") or data.get("tool") or ""),
            params=_dict_value(data.get("params"), field_name="tool template params"),
            required=bool(data.get("required", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "tool_name": self.tool_name,
            "params": dict(self.params),
            "required": self.required,
        }


@dataclass(frozen=True)
class SkillValidationRule:
    name: str
    severity: Literal["error", "warning"] = "error"
    config: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "config", _dict_value(self.config, field_name="validation rule config"))
        if not self.name:
            raise ValueError("validation rule name is required")
        if self.severity not in {"error", "warning"}:
            raise ValueError("validation rule severity is invalid")

    @classmethod
    def from_value(cls, value: str | dict[str, Any]) -> SkillValidationRule:
        if isinstance(value, str):
            return cls(name=value)
        data = _dict_value(value, field_name="validation_rule")
        return cls(
            name=str(data.get("name") or data.get("id") or ""),
            severity=str(data.get("severity") or "error"),  # type: ignore[arg-type]
            config=_dict_value(data.get("config"), field_name="validation rule config"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "severity": self.severity, "config": dict(self.config)}


@dataclass(frozen=True)
class SkillRetrievalCandidate:
    skill_id: str
    version: int
    score: float
    status: SkillStatus
    domain: str
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _dict_value(self.metadata, field_name="candidate metadata"))
        if not self.skill_id:
            raise ValueError("candidate skill_id is required")
        if self.version < 1:
            raise ValueError("candidate version must be positive")
        if not self.domain:
            raise ValueError("candidate domain is required")
        _validate_status(self.status)

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "version": self.version,
            "score": self.score,
            "status": self.status,
            "domain": self.domain,
            "reason": self.reason,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class SkillReviewerDecision:
    status: ReviewerStatus
    rationale: str = ""
    findings: tuple[str, ...] = ()
    selected_skill_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "findings", _string_tuple(self.findings, field_name="reviewer findings"))
        object.__setattr__(self, "metadata", _dict_value(self.metadata, field_name="reviewer metadata"))
        if self.status not in REVIEWER_STATUSES:
            raise ValueError(f"reviewer status must be one of {sorted(REVIEWER_STATUSES)}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "rationale": self.rationale,
            "findings": list(self.findings),
            "selected_skill_id": self.selected_skill_id,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class SkillCard:
    id: str
    version: int
    status: SkillStatus
    domain: str
    title: str
    description: str
    input_patterns: tuple[str, ...]
    tags: tuple[str, ...]
    evidence_required: SkillEvidenceRequirement
    output_contract: tuple[str, ...]
    validation_rules: tuple[SkillValidationRule, ...]
    tool_plan_template: tuple[SkillToolTemplate, ...] = ()
    sql_templates: tuple[SkillSQLTemplate, ...] = ()
    synthesis_guidance: str | None = None
    generation_model: str | None = None
    created_by: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", _validate_status(self.status))
        object.__setattr__(self, "input_patterns", _string_tuple(self.input_patterns, field_name="input_patterns"))
        object.__setattr__(self, "tags", _string_tuple(self.tags, field_name="tags"))
        object.__setattr__(self, "output_contract", _string_tuple(self.output_contract, field_name="output_contract"))
        object.__setattr__(self, "validation_rules", _normalize_validation_rules(self.validation_rules))
        object.__setattr__(self, "tool_plan_template", _normalize_tool_templates(self.tool_plan_template))
        object.__setattr__(self, "sql_templates", _normalize_sql_templates(self.sql_templates))
        object.__setattr__(self, "metadata", _dict_value(self.metadata, field_name="metadata"))
        errors = validate_skill_card_contract(self)
        if errors:
            raise ValueError("; ".join(errors))

    @property
    def runtime_eligible(self) -> bool:
        return is_runtime_eligible_card(self)


def validate_skill_card_contract(card: SkillCard | dict[str, Any]) -> list[str]:
    try:
        already_parsed = isinstance(card, SkillCard)
        if already_parsed:
            payload = skill_card_to_dict(card)
        else:
            payload = dict(card)
    except Exception as exc:
        return [str(exc)]

    errors: list[str] = []
    for field_name in ("id", "domain", "status", "output_contract"):
        if payload.get(field_name) in (None, "", [], {}):
            errors.append(f"{field_name} is required")
    if payload.get("status") not in ALL_STATUSES:
        errors.append(f"status must be one of {sorted(ALL_STATUSES)}")
    if not isinstance(payload.get("version"), int) or payload.get("version", 0) < 1:
        errors.append("version must be a positive integer")
    if not isinstance(payload.get("evidence_required"), dict):
        errors.append("evidence_required must be an object")
    for list_field in ("input_patterns", "tags", "output_contract", "validation_rules"):
        if not isinstance(payload.get(list_field), list):
            errors.append(f"{list_field} must be a list")
    if payload.get("status") in RUNTIME_STATUSES and payload.get("validation_errors"):
        errors.append("runtime-eligible cards must not include validation_errors")
    if not errors and not already_parsed:
        try:
            skill_card_from_dict(payload)
        except Exception as exc:
            errors.append(str(exc))
    return sorted(dict.fromkeys(errors))


def skill_card_to_dict(card: SkillCard) -> dict[str, Any]:
    return {
        "id": card.id,
        "version": card.version,
        "status": card.status,
        "domain": card.domain,
        "title": card.title,
        "description": card.description,
        "input_patterns": list(card.input_patterns),
        "tags": list(card.tags),
        "evidence_required": card.evidence_required.to_dict(),
        "tool_plan_template": [item.to_dict() for item in card.tool_plan_template],
        "sql_templates": [item.to_dict() for item in card.sql_templates],
        "output_contract": list(card.output_contract),
        "validation_rules": [item.to_dict() for item in card.validation_rules],
        "synthesis_guidance": card.synthesis_guidance,
        "generation_model": card.generation_model,
        "created_by": card.created_by,
        "metadata": dict(card.metadata),
    }


def skill_card_from_dict(payload: dict[str, Any]) -> SkillCard:
    data = _dict_value(payload, field_name="skill_card")
    status = _validate_status(str(data.get("status") or ""))
    validation_values = data.get("validation_rules") or []
    if not isinstance(validation_values, list):
        raise ValueError("validation_rules must be a list")
    return SkillCard(
        id=str(data.get("id") or ""),
        version=int(data.get("version") or 1),
        status=status,
        domain=str(data.get("domain") or ""),
        title=str(data.get("title") or ""),
        description=str(data.get("description") or ""),
        input_patterns=_string_tuple(data.get("input_patterns"), field_name="input_patterns"),
        tags=_string_tuple(data.get("tags"), field_name="tags"),
        evidence_required=SkillEvidenceRequirement.from_dict(data.get("evidence_required") or {}),
        tool_plan_template=tuple(SkillToolTemplate.from_dict(item) for item in _list_of_dicts(data.get("tool_plan_template"), field_name="tool_plan_template")),
        sql_templates=tuple(SkillSQLTemplate.from_dict(item) for item in _list_of_dicts(data.get("sql_templates"), field_name="sql_templates")),
        output_contract=_string_tuple(data.get("output_contract"), field_name="output_contract"),
        validation_rules=tuple(SkillValidationRule.from_value(item) for item in validation_values),
        synthesis_guidance=data.get("synthesis_guidance"),
        generation_model=data.get("generation_model"),
        created_by=data.get("created_by"),
        metadata=_dict_value(data.get("metadata"), field_name="metadata"),
    )
