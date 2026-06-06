from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

from .config import GenerationConfig, load_generation_config
from .pipeline import run_review_heal_pipeline
from .schema_auditor import audit_skill_card, normalize_evidence_required
from .schema_catalog import SchemaCatalog, default_schema_catalog
from .schema import slugify, validate_skill_card
from .seeds import SeedBrief, default_seed_briefs, expanded_seed_briefs

Healer = Callable[[dict, list[str]], dict]


@dataclass(frozen=True)
class GenerationResult:
    generated: int
    output_dir: Path
    jsonl_path: Path
    yaml_paths: tuple[Path, ...]
    model: str
    dry_run: bool
    errors: tuple[str, ...] = ()


def _as_string_list(value: Any, fallback: Iterable[str] = ()) -> list[str]:
    raw = value if value not in (None, "", {}, []) else list(fallback)
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, (list, tuple)):
        return [str(item) for item in raw if item not in (None, "")]
    return [str(raw)]


def _normalize_tool_plan_template(value: Any) -> list[Any]:
    if value in (None, "", {}, []):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return [{"description": str(value)}]


def _normalize_python_tools(value: Any) -> list[dict[str, Any]]:
    if value in (None, "", {}, []):
        return []
    tools = value if isinstance(value, list) else [value]
    return [tool for tool in tools if isinstance(tool, dict)]


def _card_from_seed(seed: SeedBrief, *, model: str, llm_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = llm_payload or {}
    skill_id = slugify(f"{seed.id}_v1")
    if not skill_id.endswith("_v1"):
        skill_id = f"{skill_id}_v1"
    evidence_required = normalize_evidence_required(
        payload.get("evidence_required")
        or {"tables": list(seed.evidence_tables), "freshness": {"max_eod_age_days": 3}}
    )
    return {
        "id": skill_id,
        "version": 1,
        "status": "generated",
        "domain": str(payload.get("domain") or seed.domain),
        "title": str(payload.get("title") or seed.title),
        "description": str(payload.get("description") or seed.description),
        "input_patterns": _as_string_list(payload.get("input_patterns"), seed.input_patterns),
        "tags": _as_string_list(payload.get("tags"), seed.tags),
        "evidence_required": evidence_required,
        "tool_plan_template": _normalize_tool_plan_template(payload.get("tool_plan_template")),
        "sql_templates": payload.get("sql_templates") or [],
        "python_tools": _normalize_python_tools(payload.get("python_tools")),
        "output_contract": _as_string_list(payload.get("output_contract"), seed.output_contract),
        "validation_rules": _as_string_list(
            payload.get("validation_rules")
            or ["required_tables_exist", "sql_is_read_only", "output_contract_present"]
        ),
        "synthesis_guidance": str(
            payload.get("synthesis_guidance")
            or "Summarize only validated evidence, surface missing evidence, and keep research-only framing."
        ),
        "created_by": "llm_generated" if llm_payload else "deterministic_seed",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "generation_model": model,
    }


def _minimal_yaml(value: Any, indent: int = 0) -> str:
    pad = " " * indent
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"{pad}{key}:")
                lines.append(_minimal_yaml(item, indent + 2))
            else:
                lines.append(f"{pad}{key}: {json.dumps(item)}")
        return "\n".join(lines)
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f"{pad}-")
                lines.append(_minimal_yaml(item, indent + 2))
            else:
                lines.append(f"{pad}- {json.dumps(item)}")
        return "\n".join(lines)
    return f"{pad}{json.dumps(value)}"


def build_generation_prompt(seed: SeedBrief, schema_catalog: SchemaCatalog | None = None) -> dict[str, Any]:
    catalog = schema_catalog or default_schema_catalog()
    prompt_tables = tuple(table for table in seed.evidence_tables if catalog.has_table(table))
    approved_schema = catalog.as_prompt_payload(prompt_tables)
    return {
        "task": "Create one Agent Adda skill card as strict JSON.",
        "rules": [
            "Status must be generated.",
            "SQL templates, if any, must be read-only SELECT/WITH templates.",
            "Python evidence tools are allowed only when SQL would become complex; keep them read-only and quarantined.",
            "Use only these approved tables and columns; do not invent tables, aliases, or columns.",
            "Use approved_schema._join_rules for joins; do not invent join conditions.",
            "Use approved_schema._global_rules for latest-date filters, stage labels, and PostgreSQL date syntax.",
            "Use column_details for data types, value examples, and semantic meaning before writing SQL.",
            "If a required concept is missing from the approved schema, place it in evidence_gaps instead of inventing SQL.",
            "Use evidence_required.tables exactly; do not use primary_tables or required_tables.",
            "Use Agent Adda Indian market evidence and research-only framing.",
        ],
        "python_tool_policy": {
            "required_function": "run(context)",
            "language": "python",
            "mode": "read_only",
            "blocked_capabilities": ["network", "subprocess", "filesystem_write", "db_write", "broker_api"],
            "required_fields": ["id", "language", "mode", "inputs", "outputs", "approved_tables", "code"],
        },
        "seed": seed.__dict__,
        "approved_schema": approved_schema,
        "schema_join_rules": approved_schema["_join_rules"]["rules"],
        "global_sql_rules": approved_schema["_global_rules"]["rules"],
        "required_keys": [
            "id",
            "domain",
            "title",
            "description",
            "input_patterns",
            "tags",
            "evidence_required",
            "tool_plan_template",
            "sql_templates",
            "output_contract",
            "validation_rules",
            "synthesis_guidance",
        ],
        "optional_keys": ["python_tools", "evidence_gaps"],
    }


def _call_openai_for_seed(seed: SeedBrief, config: GenerationConfig, schema_catalog: SchemaCatalog) -> dict[str, Any]:
    from openai import OpenAI

    client = OpenAI()
    prompt = build_generation_prompt(seed, schema_catalog)
    response = client.responses.create(
        model=config.model,
        input=[
            {
                "role": "system",
                "content": (
                    "You generate schema-safe Agent Adda skill cards. "
                    "Return JSON only. Generated cards are untrusted and must remain status=generated."
                ),
            },
            {"role": "user", "content": json.dumps(prompt, default=str)},
        ],
        text={"format": {"type": "json_object"}},
    )
    text = getattr(response, "output_text", "") or "{}"
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("OpenAI returned non-object JSON")
    return parsed


def _call_openai_for_seed_with_retries(
    seed: SeedBrief,
    config: GenerationConfig,
    schema_catalog: SchemaCatalog,
    *,
    max_attempts: int = 3,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return _call_openai_for_seed(seed, config, schema_catalog)
        except Exception as exc:
            last_error = exc
            if attempt >= max_attempts:
                break
            time.sleep(min(8.0, 1.5 * attempt))
    assert last_error is not None
    raise last_error


def generate_skill_cards(
    *,
    seed_briefs: Iterable[SeedBrief] | None = None,
    output_dir: Path | str = Path("skill_store") / "generated",
    dry_run: bool = False,
    count: int | None = None,
    target_count: int | None = None,
    batch_size: int = 15,
    parallelism: int = 10,
    config: GenerationConfig | None = None,
    schema_catalog: SchemaCatalog | None = None,
    review_heal: bool = False,
    healer: Healer | None = None,
) -> GenerationResult:
    cfg = config or load_generation_config()
    catalog = schema_catalog or default_schema_catalog()
    seeds = list(seed_briefs or (expanded_seed_briefs(target_count) if target_count else default_seed_briefs()))
    if count is not None:
        seeds = seeds[: max(0, count)]

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_dir / f"generated_skill_cards_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
    yaml_paths: list[Path] = []
    errors: list[str] = []

    with jsonl_path.open("w", encoding="utf-8") as jsonl:
        for batch_index, batch in enumerate(_batches(seeds, max(1, batch_size)), start=1):
            batch_results = _generate_batch(
                batch,
                cfg=cfg,
                catalog=catalog,
                dry_run=dry_run,
                review_heal=review_heal,
                healer=healer,
                parallelism=parallelism,
            )
            checkpoint_path = out_dir / f"checkpoint_{batch_index:04d}.jsonl"
            with checkpoint_path.open("w", encoding="utf-8") as checkpoint:
                for card, _ in batch_results:
                    checkpoint.write(json.dumps(card, sort_keys=True) + "\n")
            for card, card_errors in batch_results:
                errors.extend(card_errors)
                jsonl.write(json.dumps(card, sort_keys=True) + "\n")
                yaml_path = out_dir / f"{card['id']}.yml"
                yaml_path.write_text(_minimal_yaml(card) + "\n", encoding="utf-8")
                yaml_paths.append(yaml_path)
                _write_python_tools(card, out_dir)

    return GenerationResult(
        generated=len(seeds),
        output_dir=out_dir,
        jsonl_path=jsonl_path,
        yaml_paths=tuple(yaml_paths),
        model=cfg.model,
        dry_run=dry_run,
        errors=tuple(errors),
    )


def _batches(values: list[SeedBrief], size: int) -> list[list[SeedBrief]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _generate_one_seed(
    seed: SeedBrief,
    *,
    cfg: GenerationConfig,
    catalog: SchemaCatalog,
    dry_run: bool,
    review_heal: bool,
    healer: Healer | None,
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    llm_payload: dict[str, Any] | None = None
    if not dry_run:
        try:
            llm_payload = _call_openai_for_seed_with_retries(seed, cfg, catalog)
        except Exception as exc:
            errors.append(f"{seed.id}: {type(exc).__name__}: {exc}")
    card = _card_from_seed(seed, model=cfg.model, llm_payload=llm_payload)
    validation_errors = validate_skill_card(card, generated_only=True)
    validation_errors.extend(audit_skill_card(card, catalog))
    if validation_errors and not review_heal:
        card["status"] = "test_failed"
        card["validation_errors"] = validation_errors
        errors.extend(f"{card['id']}: {err}" for err in validation_errors)
    elif review_heal:
        pipeline_result = run_review_heal_pipeline(card, healer=healer, schema_catalog=catalog)
        card = pipeline_result.card
        errors.extend(f"{card['id']}: {err}" for err in pipeline_result.findings)
    return card, errors


def _generate_batch(
    seeds: list[SeedBrief],
    *,
    cfg: GenerationConfig,
    catalog: SchemaCatalog,
    dry_run: bool,
    review_heal: bool,
    healer: Healer | None,
    parallelism: int,
) -> list[tuple[dict[str, Any], list[str]]]:
    if dry_run or parallelism <= 1 or len(seeds) <= 1:
        return [
            _generate_one_seed(
                seed,
                cfg=cfg,
                catalog=catalog,
                dry_run=dry_run,
                review_heal=review_heal,
                healer=healer,
            )
            for seed in seeds
        ]
    results_by_index: dict[int, tuple[dict[str, Any], list[str]]] = {}
    with ThreadPoolExecutor(max_workers=max(1, parallelism)) as executor:
        futures = {
            executor.submit(
                _generate_one_seed,
                seed,
                cfg=cfg,
                catalog=catalog,
                dry_run=dry_run,
                review_heal=review_heal,
                healer=healer,
                ): index
            for index, seed in enumerate(seeds)
        }
        for future in as_completed(futures):
            results_by_index[futures[future]] = future.result()
    return [results_by_index[index] for index in range(len(seeds))]


def _write_python_tools(card: dict[str, Any], out_dir: Path) -> None:
    tools = card.get("python_tools") or []
    if not isinstance(tools, list) or not tools:
        return
    scripts_dir = out_dir / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    for tool in tools:
        if not isinstance(tool, dict) or not tool.get("code"):
            continue
        tool_id = slugify(str(tool.get("id") or "tool"))
        path = scripts_dir / f"{card['id']}__{tool_id}.py"
        path.write_text(str(tool["code"]), encoding="utf-8")
