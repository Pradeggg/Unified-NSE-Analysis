from __future__ import annotations

import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from .generator import _minimal_yaml, _write_python_tools
from .healer import llm_heal_card
from .pipeline import run_review_heal_pipeline
from .reviewer import deterministic_review
from .schema_catalog import SchemaCatalog, default_schema_catalog
from .testing import load_jsonl_cards


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
class HealingPassResult:
    total: int
    attempted: int
    healed: int
    jsonl_path: Path
    before_status_counts: Counter
    after_status_counts: Counter


def _heal_one(
    card: dict,
    *,
    healer: Healer,
    catalog: SchemaCatalog,
    max_attempts: int,
) -> dict:
    if card.get("status") != "test_failed":
        return card
    def preserving_healer(current: dict, findings: list[str]) -> dict:
        healed = healer(current, findings)
        preserved = dict(current)
        preserved.update(healed)
        for key in IDENTITY_KEYS:
            if key not in preserved or preserved[key] in (None, "", [], {}):
                preserved[key] = card.get(key) or current.get(key)
        return preserved

    result = run_review_heal_pipeline(
        card,
        reviewer=deterministic_review,
        healer=preserving_healer,
        schema_catalog=catalog,
        max_attempts=max_attempts,
    )
    preserved = dict(card)
    preserved.update(result.card)
    for key in IDENTITY_KEYS:
        if key not in preserved or preserved[key] in (None, "", [], {}):
            preserved[key] = card.get(key)
    return preserved


def heal_failed_jsonl(
    source_jsonl: Path | str,
    output_dir: Path | str,
    *,
    healer: Healer | None = None,
    schema_catalog: SchemaCatalog | None = None,
    max_attempts: int = 3,
    parallelism: int = 10,
    checkpoint_size: int = 50,
) -> HealingPassResult:
    source = Path(source_jsonl)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    catalog = schema_catalog or default_schema_catalog()
    heal = healer or (lambda card, findings: llm_heal_card(card, findings, schema_catalog=catalog))
    cards = load_jsonl_cards(source)
    before = Counter(card.get("status") for card in cards)
    attempted = before.get("test_failed", 0)

    healed_cards: list[dict] = []
    batch_size = max(1, checkpoint_size)
    for batch_no, start in enumerate(range(0, len(cards), batch_size), 1):
        batch = cards[start : start + batch_size]
        if parallelism <= 1 or len(batch) <= 1:
            healed_batch = [
                _heal_one(card, healer=heal, catalog=catalog, max_attempts=max_attempts)
                for card in batch
            ]
        else:
            healed_cards_by_index: dict[int, dict] = {}
            with ThreadPoolExecutor(max_workers=max(1, parallelism)) as executor:
                futures = {
                    executor.submit(_heal_one, card, healer=heal, catalog=catalog, max_attempts=max_attempts): index
                    for index, card in enumerate(batch)
                }
                for future in as_completed(futures):
                    healed_cards_by_index[futures[future]] = future.result()
            healed_batch = [healed_cards_by_index[index] for index in range(len(batch))]
        healed_cards.extend(healed_batch)
        checkpoint_path = out_dir / f"checkpoint_{batch_no:04d}.jsonl"
        checkpoint_path.write_text(
            "\n".join(json.dumps(card, sort_keys=True) for card in healed_batch) + "\n",
            encoding="utf-8",
        )

    after = Counter(card.get("status") for card in healed_cards)
    healed_count = sum(
        1
        for before_card, after_card in zip(cards, healed_cards)
        if before_card.get("status") == "test_failed" and after_card.get("status") == "review_pending"
    )
    jsonl_path = out_dir / f"healed_skill_cards_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for card in healed_cards:
            handle.write(json.dumps(card, sort_keys=True) + "\n")
            (out_dir / f"{card['id']}.yml").write_text(_minimal_yaml(card) + "\n", encoding="utf-8")
            _write_python_tools(card, out_dir)

    return HealingPassResult(
        total=len(cards),
        attempted=attempted,
        healed=healed_count,
        jsonl_path=jsonl_path,
        before_status_counts=before,
        after_status_counts=after,
    )
