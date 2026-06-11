from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from terminal.skills.embedding_provider import EmbeddingProvider, get_embedding_provider
from terminal.skills.embedding_text import build_skill_embedding_text
from terminal.skills.store_repo import SkillStoreRepository, default_skill_store_dsn

from .schema import validate_skill_card
from .testing import load_jsonl_cards


DEFAULT_PG_DSN = "dbname=nse_market user=nse_admin host=/tmp"


@dataclass(frozen=True)
class SkillCardImportResult:
    source_jsonl: Path
    total: int
    selected: int
    imported: int
    skipped: int
    dry_run: bool
    source_status_counts: Counter
    imported_status_counts: Counter
    embedding_model: str | None
    errors: tuple[str, ...] = ()


def import_skill_cards_jsonl(
    source_jsonl: Path | str,
    *,
    source_statuses: Iterable[str] = ("review_pending",),
    target_status: str = "validated",
    require_review_pass: bool = True,
    dry_run: bool = False,
    dsn: str | None = None,
    repository: SkillStoreRepository | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    embedding_provider_name: str | None = None,
    batch_size: int = 32,
) -> SkillCardImportResult:
    source = Path(source_jsonl)
    cards = load_jsonl_cards(source)
    source_status_set = {str(status) for status in source_statuses}
    source_counts = Counter(card.get("status") for card in cards)

    selected: list[dict[str, Any]] = []
    errors: list[str] = []
    for card in cards:
        if str(card.get("status") or "") not in source_status_set:
            continue
        if card.get("validation_errors"):
            continue
        review = card.get("review") if isinstance(card.get("review"), dict) else {}
        if require_review_pass and review.get("status") not in (None, "pass"):
            continue
        promoted = _normalize_card_for_import(card)
        promoted["status"] = target_status
        promoted.pop("validation_errors", None)
        promoted["imported_to_skill_store_at"] = datetime.now().isoformat(timespec="seconds")
        promoted["source_status"] = card.get("status")
        validation_errors = validate_skill_card(promoted)
        if validation_errors:
            errors.extend(f"{promoted.get('id', '<missing-id>')}: {err}" for err in validation_errors)
            continue
        selected.append(promoted)

    if dry_run or not selected:
        return SkillCardImportResult(
            source_jsonl=source,
            total=len(cards),
            selected=len(selected),
            imported=0,
            skipped=len(cards) - len(selected),
            dry_run=dry_run,
            source_status_counts=source_counts,
            imported_status_counts=Counter(),
            embedding_model=None,
            errors=tuple(errors),
        )

    repo = repository or SkillStoreRepository(dsn=dsn or _default_dsn())
    provider = embedding_provider or get_embedding_provider(embedding_provider_name)
    imported_counts: Counter = Counter()
    imported = 0
    embedding_model: str | None = None

    for batch in _batches(selected, max(1, batch_size)):
        texts = [_embedding_text_for_card(card) for card in batch]
        embeddings = provider.embed_texts(texts)
        embedding_model = embeddings.model
        for card, text, vector in zip(batch, texts, embeddings.vectors, strict=True):
            repo.upsert_skill_card(card)
            repo.save_embedding(
                str(card["id"]),
                embeddings.model,
                embeddings.dimension,
                vector,
                text,
                version=int(card.get("version") or 1),
            )
            imported += 1
            imported_counts[str(card.get("status"))] += 1

    return SkillCardImportResult(
        source_jsonl=source,
        total=len(cards),
        selected=len(selected),
        imported=imported,
        skipped=len(cards) - len(selected),
        dry_run=dry_run,
        source_status_counts=source_counts,
        imported_status_counts=imported_counts,
        embedding_model=embedding_model,
        errors=tuple(errors),
    )


def _embedding_text_for_card(card: dict[str, Any]) -> str:
    try:
        return build_skill_embedding_text(card)
    except ValueError:
        return _fallback_embedding_text(card)


def _normalize_card_for_import(card: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(card)
    raw_fields: dict[str, Any] = {}
    sql_templates = normalized.get("sql_templates")
    if sql_templates not in (None, ""):
        normalized_sql_templates = _normalize_sql_templates(sql_templates)
        if normalized_sql_templates != sql_templates:
            raw_fields["sql_templates"] = sql_templates
            normalized["sql_templates"] = normalized_sql_templates
    if raw_fields:
        existing = normalized.get("raw_generated_fields")
        merged = dict(existing) if isinstance(existing, dict) else {}
        merged.update(raw_fields)
        normalized["raw_generated_fields"] = merged
    for field in ("input_patterns", "tags", "output_contract", "validation_rules"):
        normalized[field] = _normalize_text_array(normalized.get(field))
    if normalized.get("synthesis_guidance") not in (None, "") and not isinstance(normalized.get("synthesis_guidance"), str):
        normalized["synthesis_guidance"] = json.dumps(normalized["synthesis_guidance"], sort_keys=True)
    return normalized


def _normalize_sql_templates(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        templates: list[dict[str, Any]] = []
        for name, sql_value in value.items():
            templates.append(_normalize_sql_template(sql_value, fallback_name=str(name)))
        return templates
    if isinstance(value, list):
        return [_normalize_sql_template(item, fallback_name=f"template_{index}") for index, item in enumerate(value, 1)]
    return []


def _normalize_sql_template(value: Any, *, fallback_name: str) -> dict[str, Any]:
    if isinstance(value, dict):
        template = dict(value)
        template.setdefault("name", fallback_name)
        if not any(template.get(key) for key in ("sql_text", "sql", "template", "query")):
            for source_key in (
                "template_sql",
                "sql_query",
                "sql_template",
                "statement",
                "value",
                "sql_string",
                "content",
                "code",
            ):
                if template.get(source_key):
                    template["sql"] = str(template[source_key])
                    break
    else:
        template = {"name": fallback_name, "sql": str(value)}
    template.setdefault("safety_status", "passed")
    template.setdefault("safety_findings", [])
    return template


def _normalize_text_array(value: Any) -> list[str]:
    if value in (None, "", [], {}):
        return []
    raw = value if isinstance(value, list) else [value]
    normalized: list[str] = []
    for item in raw:
        if item in (None, ""):
            continue
        if isinstance(item, str):
            normalized.append(item)
        else:
            normalized.append(json.dumps(item, sort_keys=True))
    return normalized


def _fallback_embedding_text(card: dict[str, Any]) -> str:
    evidence = card.get("evidence_required") if isinstance(card.get("evidence_required"), dict) else {}
    lines = [
        _line("Title", card.get("title")),
        _line("Domain", card.get("domain")),
        _line("Description", card.get("description")),
        _line("Input Patterns", _joined(card.get("input_patterns"))),
        _line("Tags", _joined(card.get("tags"))),
        _line("Evidence Tables", _joined(evidence.get("tables"))),
        _line("Output Contract", _joined(card.get("output_contract"))),
    ]
    return "\n".join(line for line in lines if line)


def _line(label: str, value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    return f"{label}: {value}"


def _joined(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple, set, frozenset)):
        return ", ".join(sorted(str(item) for item in value if item not in (None, "")))
    return str(value)


def _batches(values: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _default_dsn() -> str:
    return default_skill_store_dsn()
