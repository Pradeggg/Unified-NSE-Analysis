from __future__ import annotations

import re
from typing import Any

from .store_schema import SkillCard, skill_card_from_dict, skill_card_to_dict


_WHITESPACE_RE = re.compile(r"[ \t\r\f\v]+")


def build_skill_embedding_text(card: SkillCard | dict[str, Any], *, include_sql: bool = False) -> str:
    payload = _card_payload(card)
    evidence = payload.get("evidence_required") or {}

    lines: list[str] = []
    _add_line(lines, "Title", payload.get("title"))
    _add_line(lines, "Domain", payload.get("domain"))
    _add_line(lines, "Description", payload.get("description"))
    _add_joined(lines, "Input Patterns", payload.get("input_patterns"))
    _add_joined(lines, "Tags", payload.get("tags"))
    _add_joined(lines, "Intent Tags", _intent_tags(evidence))
    _add_joined(lines, "Evidence Tables", evidence.get("tables"))
    _add_mapping(lines, "Freshness", evidence.get("freshness"))
    _add_joined(lines, "Output Contract", payload.get("output_contract"))

    if include_sql:
        sql_templates = payload.get("sql_templates") or []
        names = [item.get("name") or item.get("template_name") for item in sql_templates if isinstance(item, dict)]
        _add_joined(lines, "SQL Templates", names)
        for item in sql_templates:
            if isinstance(item, dict):
                _add_line(lines, "SQL", item.get("sql") or item.get("sql_text"))

    return "\n".join(_normalize_line(line) for line in lines if _normalize_line(line))


def _card_payload(card: SkillCard | dict[str, Any]) -> dict[str, Any]:
    if isinstance(card, SkillCard):
        return skill_card_to_dict(card)
    return skill_card_to_dict(skill_card_from_dict(card))


def _add_line(lines: list[str], label: str, value: Any) -> None:
    if value in (None, "", [], {}):
        return
    lines.append(f"{label}: {value}")


def _add_joined(lines: list[str], label: str, values: Any) -> None:
    normalized = _sorted_strings(values)
    if normalized:
        lines.append(f"{label}: {', '.join(normalized)}")


def _add_mapping(lines: list[str], label: str, value: Any) -> None:
    if not isinstance(value, dict) or not value:
        return
    parts = [f"{key}={value[key]}" for key in sorted(value)]
    lines.append(f"{label}: {', '.join(parts)}")


def _intent_tags(evidence: dict[str, Any]) -> list[str]:
    tags = evidence.get("intent_tags")
    if tags is None:
        metadata = evidence.get("metadata")
        if isinstance(metadata, dict):
            tags = metadata.get("intent_tags")
    return _sorted_strings(tags)


def _sorted_strings(values: Any) -> list[str]:
    if values in (None, "", [], {}):
        return []
    if isinstance(values, str):
        items = [values]
    elif isinstance(values, (list, tuple, set, frozenset)):
        items = [str(item) for item in values if item not in (None, "")]
    else:
        items = [str(values)]
    return sorted({_normalize_text(item) for item in items if _normalize_text(item)})


def _normalize_line(value: str) -> str:
    return _normalize_text(value)


def _normalize_text(value: Any) -> str:
    return _WHITESPACE_RE.sub(" ", str(value).replace("\n", " ")).strip()
