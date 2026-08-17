"""Callable Agent Adda tools for packaged analysis and Skill Store workflows."""
from __future__ import annotations

import importlib.util
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from terminal.skills.execution_plan import build_skill_execution_plan
from terminal.skills.executor import execute_skill_plan
from terminal.skills.registry import list_skills as list_static_skills
from terminal.skills.retriever import retrieve_skill_candidates
from terminal.skills.store_repo import SkillStoreRepository


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ANALYZER_PATH = PROJECT_ROOT / ".agents/skills/fundamental-analyze/scripts/fundamental_analyzer.py"
REPORT_ROOT = PROJECT_ROOT / "reports/fundamental"


@lru_cache(maxsize=1)
def _fundamental_analyzer() -> Any:
    spec = importlib.util.spec_from_file_location("agent_adda_fundamental_analyzer", ANALYZER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load fundamental analyzer at {ANALYZER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def render_fundamental_analysis_report(
    dataset: dict[str, Any],
    output_format: str = "html",
    output_path: str | None = None,
) -> dict[str, Any]:
    """Validate a sourced fundamental dataset and render HTML, Markdown, or JSON."""
    if not isinstance(dataset, dict):
        return {"success": False, "errors": ["dataset must be an object"]}
    analyzer = _fundamental_analyzer()
    errors = analyzer.validate(dataset)
    if errors:
        return {"success": False, "errors": list(errors)}
    normalized_format = str(output_format or "html").strip().lower()
    if normalized_format not in {"html", "markdown", "json"}:
        return {"success": False, "errors": ["output_format must be html, markdown, or json"]}

    enriched = analyzer.enrich(dataset)
    if normalized_format == "html":
        content, suffix = analyzer.render_html(enriched), ".html"
    elif normalized_format == "markdown":
        content, suffix = analyzer.render_markdown(enriched), ".md"
    else:
        content, suffix = json.dumps(enriched, indent=2, ensure_ascii=False) + "\n", ".json"

    destination = _report_destination(dataset, output_path, suffix)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")
    return {
        "success": True,
        "format": normalized_format,
        "path": str(destination),
        "company": dict(dataset.get("company") or {}),
        "source_count": len(dataset.get("sources") or []),
        "annual_period_count": len(dataset.get("annuals") or []),
    }


def list_agent_adda_skills(
    status: str | None = None,
    domain: str | None = None,
    include_contracts: bool = True,
    *,
    repository: Any | None = None,
) -> dict[str, Any]:
    """List callable Skill Store cards and optionally static skill contracts."""
    repo = repository or SkillStoreRepository()
    cards = repo.list_skill_cards(status=status, domain=domain)
    runtime = [
        {
            "id": row.get("id"),
            "version": row.get("version"),
            "status": row.get("status"),
            "domain": row.get("domain"),
            "title": row.get("title"),
            "maturity": "executable" if row.get("status") in {"validated", "production"} else "contract",
        }
        for row in cards
    ]
    contracts = []
    if include_contracts:
        contracts = [
            {"id": skill.id, "name": skill.name, "description": skill.description, "maturity": skill.maturity}
            for skill in list_static_skills()
        ]
    return {"runtime_skills": runtime, "static_skills": contracts, "counts": {"runtime": len(runtime), "static": len(contracts)}}


def find_agent_adda_skills(
    query: str,
    top_n: int = 5,
    domain: str | None = None,
    *,
    repository: Any | None = None,
) -> dict[str, Any]:
    """Retrieve runtime Skill Store cards and record retrieval telemetry."""
    candidates = retrieve_skill_candidates(
        query,
        top_n=max(1, min(int(top_n), 30)),
        repo=repository or SkillStoreRepository(),
        domain=domain,
        log_event=True,
    )
    return {"query": query, "candidates": [candidate.to_dict() for candidate in candidates], "count": len(candidates)}


def execute_agent_adda_skill(
    skill_id: str,
    params: dict[str, Any] | None = None,
    version: int | None = None,
    retrieval_id: int | None = None,
    *,
    repository: Any | None = None,
    call_tool_fn: Any | None = None,
) -> dict[str, Any]:
    """Execute one validated/production Skill Store card with validation and telemetry."""
    repo = repository or SkillStoreRepository()
    row = repo.get_skill_card(str(skill_id), version=version)
    if not row:
        return {"passed": False, "errors": [f"skill card not found: {skill_id}"]}
    card = _runtime_card(row)
    if str(card.get("status") or "") not in {"validated", "production"}:
        return {"passed": False, "errors": [f"skill is not runtime eligible: {card.get('status') or 'unknown'}"]}

    defaults = (((card.get("metadata") or {}).get("runtime") or {}).get("default_params") or {})
    runtime_params = {**dict(defaults), **dict(params or {})}
    decision = {
        "decision": "select",
        "selected_skill_id": str(card["id"]),
        "selected_version": int(card.get("version") or 1),
        "candidate_ids": [str(card["id"])],
    }
    from terminal.tools import TOOL_REGISTRY, call_tool

    plan = build_skill_execution_plan(
        decision,
        skill_cards=[card],
        params=runtime_params,
        available_tools={name.lower() for name in TOOL_REGISTRY},
    )
    execution = execute_skill_plan(
        plan,
        repository=repo,
        call_tool_fn=call_tool_fn or call_tool,
        available_tools={name.lower() for name in TOOL_REGISTRY},
        output_contract=card.get("output_contract") or [],
        freshness=(card.get("evidence_required") or {}).get("freshness") or {},
        retrieval_id=retrieval_id,
    )
    return {**execution.to_dict(), "skill_id": card["id"], "skill_version": card.get("version"), "params": runtime_params}


def _runtime_card(row: Mapping[str, Any]) -> dict[str, Any]:
    payload = row.get("card_payload")
    card = dict(payload) if isinstance(payload, Mapping) else dict(row)
    for field in ("id", "version", "status", "domain", "title", "description"):
        if row.get(field) is not None:
            card[field] = row[field]
    return card


def _report_destination(dataset: Mapping[str, Any], output_path: str | None, suffix: str) -> Path:
    if output_path:
        candidate = Path(output_path).expanduser()
        candidate = candidate if candidate.is_absolute() else PROJECT_ROOT / candidate
        destination = candidate.resolve()
        if PROJECT_ROOT not in destination.parents and destination != PROJECT_ROOT:
            raise ValueError("output_path must remain inside the project workspace")
        return destination.with_suffix(suffix) if destination.suffix.lower() != suffix else destination
    company = dict(dataset.get("company") or {})
    symbol = re.sub(r"[^A-Za-z0-9_-]+", "-", str(company.get("symbol") or "company")).strip("-").lower()
    as_of = re.sub(r"[^0-9-]+", "", str(company.get("as_of_date") or "undated"))
    return (REPORT_ROOT / f"{symbol}_{as_of}{suffix}").resolve()
