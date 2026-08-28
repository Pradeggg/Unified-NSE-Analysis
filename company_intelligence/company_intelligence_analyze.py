"""Coverage scoring and deliberation helpers for Company X-Ray."""

from __future__ import annotations

from collections import defaultdict


def score_evidence_coverage(evidence: list[dict], search_attempts: list[dict]) -> dict:
    categories = defaultdict(list)
    for row in evidence:
        categories[str(row.get("category", "")).lower()].append(row)

    source_tiers = {int(row.get("source_tier", 99)) for row in evidence if row.get("source_tier") is not None}
    statuses = [str(row.get("status", "")).lower() for row in search_attempts]
    source_groups = [str(row.get("source_group", "")).lower() for row in search_attempts]

    known_gaps: list[str] = []
    if any("broker" in group for group in source_groups) or any("external" in group for group in source_groups):
        if "no_results" in statuses:
            known_gaps.append("Broker research unavailable")
    if not any("concall" in str(row.get("query", "")).lower() and row.get("status") == "parsed" for row in search_attempts):
        known_gaps.append("No parsed concall transcript found")

    coverage = {
        "official_evidence": _level(1 in source_tiers),
        "company_ir": _level(any(str(row.get("source_group", "")).lower() == "company_ir" and row.get("status") == "parsed" for row in search_attempts)),
        "broker_research": "Unavailable" if known_gaps and "Broker research" in known_gaps[0] else "Low",
        "business_model": _category_level(categories, "business model"),
        "sector_data": _category_level(categories, "sector structure"),
        "market_share": _category_level(categories, "market share"),
        "search_audit": _level(bool(search_attempts)),
        "known_gaps": known_gaps,
    }
    return coverage


def strict_mode_passes(coverage: dict) -> tuple[bool, list[str]]:
    required = {
        "official_evidence": "official evidence",
        "business_model": "business-model evidence",
        "sector_data": "sector evidence",
        "search_audit": "search audit",
    }
    failures = [
        f"Missing or weak {label}"
        for key, label in required.items()
        if coverage.get(key) not in {"Medium", "High"}
    ]
    return (not failures, failures)


def build_deliberation_view(
    symbol: str,
    evidence_by_category: dict,
    coverage: dict,
    policy_impacts: list[dict],
) -> dict:
    strengths = _texts(evidence_by_category.get("competitive advantage", []))
    risks = _texts(evidence_by_category.get("risks", []))
    business = _texts(evidence_by_category.get("business model", []))
    policy = [f"{row.get('impact_area')}: {row.get('rationale')}" for row in policy_impacts]
    gaps = list(coverage.get("known_gaps", []))

    return {
        "symbol": symbol.strip().upper(),
        "bull_case": strengths or business or ["Evidence supports a constructive view, but the source base is still limited."],
        "bear_case": risks or gaps or ["No strong disconfirming evidence captured yet; treat this as a research gap."],
        "base_case": business + policy or ["Base case requires more official business and policy evidence."],
        "evidence_gaps": gaps,
        "disconfirming_evidence": risks,
        "open_questions": [
            "What evidence would disprove the current business-quality view?",
            "Is market share independently verified by an official or high-quality industry source?",
            "Are customer concentration and margin drivers stable across cycles?",
        ],
    }


def _level(condition: bool) -> str:
    return "High" if condition else "Low"


def _category_level(categories: dict, category: str) -> str:
    rows = categories.get(category, [])
    if any(int(row.get("source_tier", 99)) == 1 for row in rows):
        return "High"
    if rows:
        return "Medium"
    return "Low"


def _texts(rows: list[dict]) -> list[str]:
    return [str(row.get("text", "")).strip() for row in rows if str(row.get("text", "")).strip()]
