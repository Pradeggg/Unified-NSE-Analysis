from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Literal, Mapping

from terminal.skills.reviewer import ReviewDecision
from terminal.skills.store_repo import SkillStoreRepository


StepType = Literal["tool_call", "sql_template", "report_lookup"]
EXECUTABLE_REVIEW_DECISIONS = {"select", "merge"}
KNOWN_STEP_TYPES = {"tool_call", "sql_template", "report_lookup"}


@dataclass(frozen=True)
class SkillExecutionStep:
    step_id: str
    step_type: StepType
    skill_id: str
    skill_version: int
    name: str
    target: str
    params: dict[str, Any] = field(default_factory=dict)
    required_params: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.step_type not in KNOWN_STEP_TYPES:
            raise ValueError(f"unknown execution step type: {self.step_type}")
        if not self.step_id:
            raise ValueError("step_id is required")
        if not self.skill_id:
            raise ValueError("skill_id is required")
        if self.skill_version < 1:
            raise ValueError("skill_version must be positive")
        if not self.name:
            raise ValueError("step name is required")
        if not self.target:
            raise ValueError("step target is required")
        object.__setattr__(self, "params", dict(self.params or {}))
        object.__setattr__(self, "required_params", _string_tuple(self.required_params))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "step_type": self.step_type,
            "skill_id": self.skill_id,
            "skill_version": self.skill_version,
            "name": self.name,
            "target": self.target,
            "params": dict(self.params),
            "required_params": list(self.required_params),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class SkillExecutionPlan:
    skill_ids: tuple[str, ...]
    skill_versions: dict[str, int]
    steps: tuple[SkillExecutionStep, ...]
    review_decision: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "skill_ids", _string_tuple(self.skill_ids))
        object.__setattr__(self, "skill_versions", {str(key): int(value) for key, value in dict(self.skill_versions).items()})
        object.__setattr__(self, "steps", tuple(self.steps))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_ids": list(self.skill_ids),
            "skill_versions": dict(self.skill_versions),
            "review_decision": self.review_decision,
            "steps": [step.to_dict() for step in self.steps],
            "metadata": dict(self.metadata),
        }


def build_skill_execution_plan(
    review_decision: ReviewDecision | Mapping[str, Any],
    *,
    repository: Any | None = None,
    skill_cards: Iterable[Mapping[str, Any]] | None = None,
    params: Mapping[str, Any] | None = None,
    available_tools: Iterable[str] | None = None,
    available_reports: Iterable[str] | None = None,
) -> SkillExecutionPlan:
    decision = _normalize_review_decision(review_decision)
    if decision["decision"] not in EXECUTABLE_REVIEW_DECISIONS:
        raise ValueError(f"review decision is not executable: {decision['decision']}")

    runtime_params = dict(params or {})
    cards = _load_skill_cards(decision, repository=repository, skill_cards=skill_cards)
    steps: list[SkillExecutionStep] = []
    for card in cards:
        steps.extend(
            _steps_for_card(
                card,
                runtime_params=runtime_params,
                available_tools=available_tools,
                available_reports=available_reports,
            )
        )

    skill_ids = tuple(str(card["id"]) for card in cards)
    return SkillExecutionPlan(
        skill_ids=skill_ids,
        skill_versions={str(card["id"]): int(card.get("version") or 1) for card in cards},
        steps=tuple(steps),
        review_decision=decision["decision"],
        metadata={
            "selected_skill_id": decision.get("selected_skill_id"),
            "candidate_ids": list(decision.get("candidate_ids") or []),
        },
    )


def _normalize_review_decision(review_decision: ReviewDecision | Mapping[str, Any]) -> dict[str, Any]:
    if hasattr(review_decision, "to_dict"):
        payload = review_decision.to_dict()
    else:
        payload = dict(review_decision)
    payload["decision"] = str(payload.get("decision") or "")
    payload["candidate_ids"] = _string_tuple(payload.get("candidate_ids"))
    selected = payload.get("selected_skill_id")
    if selected and selected not in payload["candidate_ids"]:
        payload["candidate_ids"] = (str(selected), *payload["candidate_ids"])
    return payload


def _load_skill_cards(
    decision: dict[str, Any],
    *,
    repository: Any | None,
    skill_cards: Iterable[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    repo = repository or (None if skill_cards is not None else SkillStoreRepository())
    supplied_cards = {str(card["id"]): dict(card) for card in skill_cards or []}
    skill_ids = _selected_skill_ids(decision)
    cards: list[dict[str, Any]] = []
    for skill_id in skill_ids:
        version = _selected_version_for(decision, skill_id)
        card = supplied_cards.get(skill_id)
        if card is None and repo is not None:
            card = repo.get_skill_card(skill_id, version=version)
        if card is None:
            raise ValueError(f"skill card not found: {skill_id}")
        cards.append(dict(card))
    return cards


def _selected_skill_ids(decision: dict[str, Any]) -> tuple[str, ...]:
    if decision["decision"] == "select":
        selected = str(decision.get("selected_skill_id") or "")
        if not selected:
            raise ValueError("selected skill id is required for select decision")
        return (selected,)
    ids = _string_tuple(decision.get("candidate_ids"))
    if not ids:
        raise ValueError("candidate ids are required for merge decision")
    return ids


def _selected_version_for(decision: dict[str, Any], skill_id: str) -> int | None:
    if decision.get("selected_skill_id") == skill_id and decision.get("selected_version"):
        return int(decision["selected_version"])
    versions = decision.get("skill_versions")
    if isinstance(versions, Mapping) and skill_id in versions:
        return int(versions[skill_id])
    return None


def _steps_for_card(
    card: dict[str, Any],
    *,
    runtime_params: dict[str, Any],
    available_tools: Iterable[str] | None,
    available_reports: Iterable[str] | None,
) -> list[SkillExecutionStep]:
    metadata = dict(card.get("metadata") or {})
    explicit_steps = metadata.get("execution_steps")
    if explicit_steps:
        return _explicit_steps_for_card(
            card,
            explicit_steps,
            runtime_params=runtime_params,
            available_tools=available_tools,
            available_reports=available_reports,
        )

    steps: list[SkillExecutionStep] = []
    for template in card.get("tool_plan_template") or []:
        steps.append(_tool_step(card, template, runtime_params=runtime_params, available_tools=available_tools))
    for template in card.get("sql_templates") or []:
        steps.append(_sql_step(card, template, runtime_params=runtime_params))
    for template in metadata.get("report_lookup_templates") or metadata.get("report_lookup_template") or []:
        steps.append(_report_step(card, template, runtime_params=runtime_params, available_reports=available_reports))
    return steps


def _explicit_steps_for_card(
    card: dict[str, Any],
    explicit_steps: Any,
    *,
    runtime_params: dict[str, Any],
    available_tools: Iterable[str] | None,
    available_reports: Iterable[str] | None,
) -> list[SkillExecutionStep]:
    if not isinstance(explicit_steps, list):
        raise ValueError("execution_steps must be a list")
    steps: list[SkillExecutionStep] = []
    sql_templates = _sql_templates_by_name(card)
    for raw_step in explicit_steps:
        if not isinstance(raw_step, Mapping):
            raise ValueError("execution step must be an object")
        step_type = str(raw_step.get("step_type") or raw_step.get("type") or "")
        if step_type not in KNOWN_STEP_TYPES:
            raise ValueError(f"unknown execution step type: {step_type}")
        if step_type == "tool_call":
            steps.append(_tool_step(card, raw_step, runtime_params=runtime_params, available_tools=available_tools))
        elif step_type == "sql_template":
            template_name = str(raw_step.get("template_name") or raw_step.get("name") or "")
            template = sql_templates.get(template_name)
            if template is None:
                raise ValueError(f"unknown SQL template: {template_name}")
            merged = {**template, **dict(raw_step), "name": template_name}
            steps.append(_sql_step(card, merged, runtime_params=runtime_params))
        elif step_type == "report_lookup":
            steps.append(_report_step(card, raw_step, runtime_params=runtime_params, available_reports=available_reports))
    return steps


def _tool_step(
    card: dict[str, Any],
    template: Mapping[str, Any],
    *,
    runtime_params: dict[str, Any],
    available_tools: Iterable[str] | None,
) -> SkillExecutionStep:
    tool_name = str(template.get("tool_name") or template.get("tool") or template.get("target") or "")
    if not tool_name:
        raise ValueError("tool step requires tool_name")
    if available_tools is not None and tool_name.lower() not in set(_strings(available_tools)):
        raise ValueError(f"unknown tool: {tool_name}")
    name = str(template.get("name") or tool_name)
    required_params = _string_tuple(template.get("required_params"))
    params = _bind_params(template.get("params"), required_params=required_params, runtime_params=runtime_params)
    return _step(card, "tool_call", name=name, target=tool_name, params=params, required_params=required_params)


def _sql_step(
    card: dict[str, Any],
    template: Mapping[str, Any],
    *,
    runtime_params: dict[str, Any],
) -> SkillExecutionStep:
    name = str(template.get("name") or template.get("template_name") or template.get("id") or "")
    if not name:
        raise ValueError("SQL step requires template name")
    required_params = _string_tuple(template.get("required_params"))
    params = _bind_params(template.get("params"), required_params=required_params, runtime_params=runtime_params)
    metadata = dict(template.get("metadata") or {})
    for field_name in ("optional", "required", "required_filters"):
        if field_name in template:
            metadata[field_name] = template[field_name]
    return _step(
        card,
        "sql_template",
        name=name,
        target=name,
        params=params,
        required_params=required_params,
        metadata={
            **metadata,
            "row_limit": template.get("row_limit"),
            "expected_columns": list(template.get("expected_columns") or []),
        },
    )


def _report_step(
    card: dict[str, Any],
    template: Mapping[str, Any],
    *,
    runtime_params: dict[str, Any],
    available_reports: Iterable[str] | None,
) -> SkillExecutionStep:
    report_name = str(template.get("report_name") or template.get("report") or template.get("target") or "")
    if not report_name:
        raise ValueError("report lookup step requires report_name")
    if available_reports is not None and report_name.lower() not in set(_strings(available_reports)):
        raise ValueError(f"unknown report: {report_name}")
    name = str(template.get("name") or report_name)
    required_params = _string_tuple(template.get("required_params"))
    params = _bind_params(template.get("params"), required_params=required_params, runtime_params=runtime_params)
    return _step(card, "report_lookup", name=name, target=report_name, params=params, required_params=required_params)


def _step(
    card: dict[str, Any],
    step_type: StepType,
    *,
    name: str,
    target: str,
    params: dict[str, Any],
    required_params: tuple[str, ...] = (),
    metadata: dict[str, Any] | None = None,
) -> SkillExecutionStep:
    skill_id = str(card["id"])
    skill_version = int(card.get("version") or 1)
    step_index = len(str(name)) + len(str(target))
    step_id = f"{skill_id}:{skill_version}:{step_type}:{name}:{step_index}"
    return SkillExecutionStep(
        step_id=step_id,
        step_type=step_type,
        skill_id=skill_id,
        skill_version=skill_version,
        name=name,
        target=target,
        params=params,
        required_params=required_params,
        metadata=metadata or {},
    )


def _bind_params(
    template_params: Any,
    *,
    required_params: tuple[str, ...],
    runtime_params: dict[str, Any],
) -> dict[str, Any]:
    bound = dict(template_params or {})
    for name in required_params:
        if name not in bound and name in runtime_params:
            bound[name] = runtime_params[name]
        if name not in bound:
            raise ValueError(f"missing required parameter: {name}")
    return bound


def _sql_templates_by_name(card: dict[str, Any]) -> dict[str, dict[str, Any]]:
    templates: dict[str, dict[str, Any]] = {}
    for template in card.get("sql_templates") or []:
        if isinstance(template, Mapping):
            name = str(template.get("name") or template.get("template_name") or template.get("id") or "")
            if name:
                templates[name] = dict(template)
    return templates


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
