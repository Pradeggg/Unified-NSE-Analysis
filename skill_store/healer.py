from __future__ import annotations

import json
from typing import Any

from .config import GenerationConfig, load_generation_config
from .schema_catalog import SchemaCatalog, default_schema_catalog


def llm_heal_card(
    card: dict[str, Any],
    findings: list[str],
    *,
    config: GenerationConfig | None = None,
    schema_catalog: SchemaCatalog | None = None,
) -> dict[str, Any]:
    from openai import OpenAI

    cfg = config or load_generation_config()
    catalog = schema_catalog or default_schema_catalog()
    client = OpenAI()
    prompt = {
        "task": "Heal an untrusted generated Agent Adda skill card.",
        "rules": [
            "Return the full healed card as strict JSON.",
            "Keep status generated; the pipeline will promote after validation.",
            "Use only approved schema tables and columns.",
            "Use approved_schema._join_rules for joins; do not invent join conditions.",
            "Use approved_schema._global_rules for latest-date filters, stage labels, and PostgreSQL date syntax.",
            "Use column_details for data types, value examples, and semantic meaning before writing SQL.",
            "Python tools must be read-only and define run(context).",
            "Remove unsafe Python, broker/order automation, network calls, subprocess calls, and DB writes.",
        ],
        "approved_schema": catalog.as_prompt_payload(),
        "findings": findings,
        "card": card,
    }
    response = client.responses.create(
        model=cfg.model,
        input=[
            {"role": "system", "content": "You repair generated market-intelligence skill cards safely."},
            {"role": "user", "content": json.dumps(prompt, default=str)},
        ],
        text={"format": {"type": "json_object"}},
    )
    payload = json.loads(getattr(response, "output_text", "") or "{}")
    if not isinstance(payload, dict):
        raise ValueError("healer returned non-object JSON")
    payload["status"] = "generated"
    return payload
