from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .generator import _minimal_yaml, _write_python_tools
from .pipeline import run_review_heal_pipeline
from .schema_catalog import SchemaCatalog, default_schema_catalog
from .testing import load_jsonl_cards


@dataclass(frozen=True)
class ReauditResult:
    total: int
    jsonl_path: Path
    before_status_counts: Counter
    after_status_counts: Counter


def _prepare_card_for_reaudit(card: dict) -> dict:
    prepared = dict(card)
    original_status = str(prepared.get("status") or "")
    prepared["status"] = "generated"
    prepared["reaudit"] = {
        "original_status": original_status,
        "runtime_quarantined": original_status in {"validated", "production"},
    }
    prepared.pop("validation_errors", None)
    return prepared


def reaudit_jsonl(
    source_jsonl: Path | str,
    output_dir: Path | str,
    *,
    schema_catalog: SchemaCatalog | None = None,
    checkpoint_size: int = 50,
) -> ReauditResult:
    source = Path(source_jsonl)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    catalog = schema_catalog or default_schema_catalog()
    cards = load_jsonl_cards(source)
    before = Counter(card.get("status") for card in cards)

    reaudited_cards: list[dict] = []
    batch_size = max(1, checkpoint_size)
    for batch_no, start in enumerate(range(0, len(cards), batch_size), 1):
        batch = cards[start : start + batch_size]
        reaudited_batch = [
            run_review_heal_pipeline(
                _prepare_card_for_reaudit(card),
                schema_catalog=catalog,
                max_attempts=1,
            ).card
            for card in batch
        ]
        reaudited_cards.extend(reaudited_batch)
        checkpoint_path = out_dir / f"checkpoint_{batch_no:04d}.jsonl"
        checkpoint_path.write_text(
            "\n".join(json.dumps(card, sort_keys=True) for card in reaudited_batch) + "\n",
            encoding="utf-8",
        )

    after = Counter(card.get("status") for card in reaudited_cards)
    jsonl_path = out_dir / f"reaudited_skill_cards_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for card in reaudited_cards:
            handle.write(json.dumps(card, sort_keys=True) + "\n")
            (out_dir / f"{card['id']}.yml").write_text(_minimal_yaml(card) + "\n", encoding="utf-8")
            _write_python_tools(card, out_dir)

    return ReauditResult(
        total=len(cards),
        jsonl_path=jsonl_path,
        before_status_counts=before,
        after_status_counts=after,
    )
