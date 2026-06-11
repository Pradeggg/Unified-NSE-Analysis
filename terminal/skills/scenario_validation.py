"""Offline validation for generated Skill Store scenario cards."""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from skill_store.pipeline import Healer, PipelineResult, run_review_heal_pipeline
from skill_store.schema_catalog import SchemaCatalog


DEFAULT_VALIDATED_DIR = Path("data") / "skill_store" / "generated" / "validated"


@dataclass(frozen=True)
class ScenarioValidationResult:
    total: int
    jsonl_path: Path
    report_path: Path
    status_counts: dict[str, int]
    failed: int


def validate_skill_scenarios(
    input_jsonl: Path | str,
    *,
    output_dir: Path | str = DEFAULT_VALIDATED_DIR,
    schema_catalog: SchemaCatalog | None = None,
    healer: Healer | None = None,
    max_attempts: int = 3,
) -> ScenarioValidationResult:
    """Validate generated cards and write a reviewed JSONL plus report."""
    source = Path(input_jsonl)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    jsonl_path = out_dir / f"validated_skill_cards_{timestamp}.jsonl"
    report_path = out_dir / f"validation_report_{timestamp}.md"

    pipeline_results = [
        _validate_card(card, schema_catalog=schema_catalog, healer=healer, max_attempts=max_attempts)
        for card in _load_jsonl_cards(source)
    ]
    status_counts = Counter(str(result.card.get("status") or "unknown") for result in pipeline_results)

    with jsonl_path.open("w", encoding="utf-8") as handle:
        for result in pipeline_results:
            handle.write(json.dumps(result.card, sort_keys=True) + "\n")

    report_path.write_text(_render_report(source, pipeline_results, status_counts), encoding="utf-8")

    return ScenarioValidationResult(
        total=len(pipeline_results),
        jsonl_path=jsonl_path,
        report_path=report_path,
        status_counts=dict(status_counts),
        failed=status_counts.get("test_failed", 0),
    )


def _validate_card(
    card: dict[str, Any],
    *,
    schema_catalog: SchemaCatalog | None,
    healer: Healer | None,
    max_attempts: int,
) -> PipelineResult:
    return run_review_heal_pipeline(
        card,
        schema_catalog=schema_catalog,
        healer=healer,
        max_attempts=max_attempts,
    )


def _load_jsonl_cards(path: Path) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as exc:
            cards.append(_parse_failed_card(path, line_no, f"JSONDecodeError: {exc}"))
            continue
        if not isinstance(parsed, dict):
            cards.append(_parse_failed_card(path, line_no, f"expected object, got {type(parsed).__name__}"))
            continue
        cards.append(parsed)
    return cards


def _parse_failed_card(path: Path, line_no: int, error: str) -> dict[str, Any]:
    return {
        "id": f"{path.stem}_line_{line_no}_parse_failed",
        "version": 1,
        "status": "generated",
        "domain": "data_quality",
        "title": "Parse Failed Skill Scenario",
        "description": "Placeholder generated when a JSONL row cannot be parsed.",
        "input_patterns": ["parse failed generated scenario"],
        "tags": ["parse_failed"],
        "evidence_required": {"tables": []},
        "output_contract": ["validation_error"],
        "validation_rules": ["jsonl_row_must_be_object"],
        "validation_errors": [error],
    }


def _render_report(source: Path, results: list[PipelineResult], status_counts: Counter[str]) -> str:
    lines = [
        "# Skill Scenario Validation Report",
        "",
        f"Source: `{source}`",
        f"Total: {len(results)}",
        "",
        "## Status Counts",
        "",
    ]
    for status, count in sorted(status_counts.items()):
        lines.append(f"- {status}: {count}")
    lines.extend(["", "## Findings", ""])
    for result in results:
        card = result.card
        card_id = card.get("id") or "<missing-id>"
        status = card.get("status") or "unknown"
        lines.append(f"### {card_id}")
        lines.append("")
        lines.append(f"- status: {status}")
        lines.append(f"- attempts: {result.attempts}")
        findings = result.findings or card.get("validation_errors") or []
        if findings:
            for finding in findings:
                lines.append(f"- finding: {finding}")
        else:
            lines.append("- finding: none")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
