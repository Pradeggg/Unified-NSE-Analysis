from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .schema import RUNTIME_STATUSES, validate_skill_card


_BLOCKED_SQL_WORDS = {
    "alter",
    "call",
    "create",
    "delete",
    "drop",
    "exec",
    "execute",
    "grant",
    "insert",
    "merge",
    "revoke",
    "truncate",
    "update",
}
_STOPWORDS = {
    "a",
    "and",
    "are",
    "for",
    "from",
    "get",
    "in",
    "is",
    "me",
    "my",
    "of",
    "or",
    "the",
    "to",
    "with",
}


def load_jsonl_cards(path: Path | str) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for line_no, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if not stripped:
            continue
        parsed = json.loads(stripped)
        if not isinstance(parsed, dict):
            raise ValueError(f"line {line_no} is not a JSON object")
        cards.append(parsed)
    return cards


def _walk_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        strings: list[str] = []
        for item in value.values():
            strings.extend(_walk_strings(item))
        return strings
    if isinstance(value, list):
        strings = []
        for item in value:
            strings.extend(_walk_strings(item))
        return strings
    return []


def _looks_like_sql(text: str) -> bool:
    lowered = text.strip().lower()
    return lowered.startswith(("select ", "with ")) or any(f" {word} " in f" {lowered} " for word in _BLOCKED_SQL_WORDS)


def _is_read_only_sql(text: str) -> bool:
    lowered = re.sub(r"\s+", " ", text.strip().lower())
    if not lowered.startswith(("select ", "with ")):
        return False
    words = set(re.findall(r"[a-z_]+", lowered))
    return not words.intersection(_BLOCKED_SQL_WORDS)


def safety_findings(cards: list[dict[str, Any]]) -> list[str]:
    findings: list[str] = []
    for card in cards:
        skill_id = str(card.get("id") or "<missing-id>")
        for error in validate_skill_card(card, generated_only=True):
            findings.append(f"{skill_id}: {error}")
        if card.get("status") in RUNTIME_STATUSES:
            findings.append(f"{skill_id}: generated skill must not be runtime eligible")
        for sql_text in _walk_strings(card.get("sql_templates", {})):
            if _looks_like_sql(sql_text) and not _is_read_only_sql(sql_text):
                findings.append(f"{skill_id}: sql template is not read-only")
        for text in _walk_strings(card):
            lowered = text.lower()
            if "openai_api_key" in lowered or re.search(r"\bsk-[a-z0-9]{8,}", lowered):
                findings.append(f"{skill_id}: possible secret material found")
    return findings


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 2 and token not in _STOPWORDS
    }


def _selection_text(card: dict[str, Any]) -> str:
    parts: list[str] = []
    for field in ("id", "domain", "title", "description"):
        parts.append(str(card.get(field) or ""))
    parts.extend(str(item) for item in card.get("input_patterns", []) if item)
    parts.extend(str(item) for item in card.get("tags", []) if item)
    return " ".join(parts)


def select_candidate_skills(
    query: str,
    cards: list[dict[str, Any]],
    *,
    limit: int = 3,
    min_score: float = 0.12,
) -> list[dict[str, Any]]:
    query_tokens = _tokens(query)
    if not query_tokens:
        return []

    selected: list[dict[str, Any]] = []
    for card in cards:
        if card.get("status") in RUNTIME_STATUSES:
            continue
        card_tokens = _tokens(_selection_text(card))
        if not card_tokens:
            continue
        overlap = query_tokens.intersection(card_tokens)
        score = len(overlap) / max(1, len(query_tokens))
        if score >= min_score:
            selected.append(
                {
                    "id": card["id"],
                    "score": round(score, 4),
                    "matched_terms": sorted(overlap),
                    "status": card.get("status"),
                }
            )

    selected.sort(key=lambda item: (-item["score"], item["id"]))
    return selected[:limit]


def select_runtime_skills(
    query: str,
    cards: list[dict[str, Any]],
    *,
    limit: int = 3,
    min_score: float = 0.12,
) -> list[dict[str, Any]]:
    runtime_cards = [card for card in cards if card.get("status") in RUNTIME_STATUSES]
    query_tokens = _tokens(query)
    if not query_tokens:
        return []

    selected: list[dict[str, Any]] = []
    for card in runtime_cards:
        card_tokens = _tokens(_selection_text(card))
        if not card_tokens:
            continue
        overlap = query_tokens.intersection(card_tokens)
        score = len(overlap) / max(1, len(query_tokens))
        if score >= min_score:
            selected.append(
                {
                    "id": card["id"],
                    "score": round(score, 4),
                    "matched_terms": sorted(overlap),
                    "status": card.get("status"),
                }
            )

    selected.sort(key=lambda item: (-item["score"], item["id"]))
    return selected[:limit]
