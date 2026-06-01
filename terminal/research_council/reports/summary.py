"""Top-level Research Council report summary generation."""

from __future__ import annotations

import json
from typing import Any, Callable

from terminal.research_council.llm_client import ResearchCouncilLLMUnavailable, call_llm_json


SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["headline", "stance", "key_takeaways", "top_candidates", "upgrade_triggers", "risk_flags"],
    "properties": {
        "headline": {"type": "string"},
        "stance": {"type": "string"},
        "key_takeaways": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "top_candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["symbol", "view", "reason"],
                "properties": {
                    "symbol": {"type": "string"},
                    "view": {"type": "string"},
                    "reason": {"type": "string"},
                },
            },
        },
        "upgrade_triggers": {"type": "array", "items": {"type": "string"}},
        "risk_flags": {"type": "array", "items": {"type": "string"}},
    },
}


def build_report_summary(state: object, *, llm_call: Callable[..., dict[str, Any]] | None = None) -> dict[str, Any]:
    """Build a compact LLM narrative summary, failing closed to deterministic text."""

    payload = _summary_payload(state)
    call = llm_call or call_llm_json
    try:
        summary = call(
            system=(
                "You are an institutional research report summarizer. Use only the supplied JSON. "
                "Do not make price targets, trade recommendations, or claims not present in evidence. "
                "Return concise JSON matching the schema."
            ),
            user=json.dumps(payload, default=str),
            schema=SUMMARY_SCHEMA,
        )
    except (ResearchCouncilLLMUnavailable, RuntimeError, ValueError, OSError) as exc:
        summary = _fallback_summary(state, error=str(exc))
    summary["source"] = summary.get("source") or ("llm" if "error" not in summary else "fallback")
    return summary


def _summary_payload(state: object) -> dict[str, Any]:
    decision = getattr(state, "decision", None)
    pack = getattr(state, "evidence_pack", None)
    return {
        "objective": getattr(state, "objective", None),
        "mode": getattr(state, "mode", None),
        "horizon": getattr(state, "horizon", None),
        "risk_budget": getattr(state, "risk_budget", None),
        "market": (pack.sections.get("market", {}) if pack else {}),
        "sector": (pack.sections.get("sector_opportunity") or pack.sections.get("sectors") if pack else {}),
        "decision": {
            "label": getattr(decision, "final_label", None),
            "confidence": getattr(decision, "confidence", None),
            "rationale": getattr(decision, "rationale", None),
            "candidates": (getattr(decision, "candidates", []) or [])[:5],
            "dissent_log": getattr(decision, "dissent_log", []) if decision else [],
        },
        "critic_reviews": [
            {"critic": review.critic, "severity": review.severity_max, "summary": review.summary}
            for group in (getattr(state, "critic_reviews", []) or [])
            for review in group
        ],
        "missing_evidence": [
            {"scope": item.scope, "subject": item.subject, "field": item.field, "severity": item.severity}
            for item in (getattr(decision, "missing_evidence", []) if decision else [])
        ],
    }


def _fallback_summary(state: object, *, error: str) -> dict[str, Any]:
    decision = getattr(state, "decision", None)
    candidates = getattr(decision, "candidates", []) if decision else []
    label = getattr(decision, "final_label", "WATCHLIST")
    top = candidates[:3]
    return {
        "headline": f"{label}: LLM summary unavailable; using deterministic council summary.",
        "stance": str(label),
        "key_takeaways": [
            getattr(decision, "rationale", "Council decision is unavailable.") if decision else "Council decision is unavailable.",
            "Use candidate table, evidence gates, and critic review before acting.",
        ],
        "top_candidates": [
            {
                "symbol": str(candidate.get("symbol", "n/a")),
                "view": str((candidate.get("quant_sweep") or {}).get("verdict") or label),
                "reason": str(candidate.get("supporting_branch") or "council shortlist"),
            }
            for candidate in top
        ],
        "upgrade_triggers": ["Pending evidence gates confirm with source-backed specialist findings."],
        "risk_flags": [f"LLM summary unavailable: {error}"],
        "source": "fallback",
        "error": error,
    }
