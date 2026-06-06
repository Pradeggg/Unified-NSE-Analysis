from __future__ import annotations

from typing import Any


GENERATED_STATUSES = {"generated", "test_failed", "review_pending"}
RUNTIME_STATUSES = {"validated", "production"}
ALL_STATUSES = GENERATED_STATUSES | RUNTIME_STATUSES | {"deprecated"}
REQUIRED_FIELDS = (
    "id",
    "version",
    "status",
    "domain",
    "title",
    "description",
    "input_patterns",
    "tags",
    "evidence_required",
    "output_contract",
    "validation_rules",
)


def validate_skill_card(card: dict[str, Any], *, generated_only: bool = False) -> list[str]:
    errors: list[str] = []
    for field in REQUIRED_FIELDS:
        if field not in card or card[field] in (None, "", [], {}):
            errors.append(f"{field} is required")
    status = str(card.get("status") or "")
    if status not in ALL_STATUSES:
        errors.append(f"status must be one of {sorted(ALL_STATUSES)}")
    if generated_only and status in RUNTIME_STATUSES:
        errors.append("status must not be runtime-eligible during generation")
    if status in RUNTIME_STATUSES and card.get("validation_errors"):
        errors.append("runtime-eligible cards must not include validation_errors")
    version = card.get("version")
    if not isinstance(version, int) or version < 1:
        errors.append("version must be a positive integer")
    for field in ("input_patterns", "tags", "output_contract", "validation_rules"):
        if field in card and not isinstance(card[field], list):
            errors.append(f"{field} must be a list")
    if "evidence_required" in card and not isinstance(card["evidence_required"], dict):
        errors.append("evidence_required must be an object")
    if "tool_plan_template" in card and not isinstance(card["tool_plan_template"], list):
        errors.append("tool_plan_template must be a list")
    if "python_tools" in card and not isinstance(card["python_tools"], list):
        errors.append("python_tools must be a list")
    return errors


def slugify(value: str) -> str:
    chars = []
    previous_underscore = False
    for char in value.lower():
        if char.isalnum():
            chars.append(char)
            previous_underscore = False
        elif not previous_underscore:
            chars.append("_")
            previous_underscore = True
    return "".join(chars).strip("_") or "skill"
