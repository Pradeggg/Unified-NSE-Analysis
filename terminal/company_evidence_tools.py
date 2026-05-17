"""Company evidence audit and promotion helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _attempt(query: str, source_group: str, results: list[dict] | None = None, failure_reason: str = "") -> dict:
    result_count = len(results or [])
    return {
        "query": query,
        "alias": "",
        "source_group": source_group,
        "result_count": result_count,
        "parse_status": "ok" if result_count else "no_results",
        "failure_reason": failure_reason,
    }


def search_company_official_sources(symbol: str, alias: str | None = None) -> dict:
    sym = symbol.strip().upper()
    query = f"{alias or sym} investor relations official"
    results: list[dict[str, Any]] = []
    return {
        "status": "no_results",
        "symbol": sym,
        "attempts": [_attempt(query, "official", results, "official source search adapter not configured")],
        "results": results,
    }


def search_company_filings(symbol: str, alias: str | None = None) -> dict:
    sym = symbol.strip().upper()
    query = f"{alias or sym} exchange filings results annual report"
    results: list[dict[str, Any]] = []
    return {
        "status": "no_results",
        "symbol": sym,
        "attempts": [_attempt(query, "filings", results, "filing source search adapter not configured")],
        "results": results,
    }


def _search_external_sources(symbol: str, alias: str | None = None) -> dict:
    sym = symbol.strip().upper()
    query = f"{alias or sym} company news investor presentation"
    results: list[dict[str, Any]] = []
    return {
        "status": "no_results",
        "symbol": sym,
        "attempts": [_attempt(query, "external", results, "external search adapter not configured")],
        "results": results,
    }


def audit_company_search(symbol: str, alias: str | None = None, include_external: bool = False) -> dict:
    """Audit company evidence search attempts in a deterministic source order."""
    sym = symbol.strip().upper()
    stages = [
        ("official", search_company_official_sources(sym, alias=alias)),
        ("filings", search_company_filings(sym, alias=alias)),
    ]
    if include_external:
        stages.append(("external", _search_external_sources(sym, alias=alias)))

    attempts: list[dict] = []
    results: list[dict] = []
    gaps: list[str] = []
    for group, payload in stages:
        for attempt in payload.get("attempts") or []:
            attempt = dict(attempt)
            attempt.setdefault("source_group", group)
            attempt.setdefault("alias", alias or "")
            attempt.setdefault("failure_reason", "")
            attempts.append(attempt)
        rows = payload.get("results") or []
        if rows:
            results.extend(rows)
        else:
            gaps.append(group)

    status = "ok" if results and not gaps else ("partial" if results else "no_evidence")
    return {
        "status": status,
        "symbol": sym,
        "alias": alias or "",
        "attempts": attempts,
        "results": results,
        "gaps": gaps,
        "source_order": [group for group, _ in stages],
    }


def promote_company_evidence_to_postgres(
    symbol: str,
    evidence: list[dict] | None = None,
    dsn: str | None = None,
    dry_run: bool = True,
) -> dict:
    """Prepare or insert company evidence records with source metadata."""
    sym = symbol.strip().upper()
    now = datetime.now(timezone.utc).isoformat()
    records = []
    for item in evidence or []:
        records.append(
            {
                "symbol": sym,
                "category": item.get("category") or "uncategorized",
                "title": item.get("title") or item.get("name") or "",
                "source_url": item.get("url") or item.get("source_url") or "",
                "source_path": item.get("path") or item.get("source_path") or "",
                "metadata": item,
                "promoted_at": now,
            }
        )
    if dry_run:
        return {"status": "dry_run", "symbol": sym, "records": records, "dsn": dsn or ""}
    # The durable PostgreSQL table is intentionally not auto-created here; use
    # ensure_postgres_schema/audit tools before enabling writes in production.
    return {
        "status": "not_configured",
        "symbol": sym,
        "records": records,
        "dsn": dsn or "",
        "message": "PostgreSQL promotion writes are not enabled; rerun as dry_run or wire target schema.",
    }


def get_company_evidence_coverage(symbol: str, alias: str | None = None) -> dict:
    audit = audit_company_search(symbol, alias=alias)
    coverage: dict[str, int] = {}
    for row in audit.get("results") or []:
        category = row.get("category") or row.get("source_group") or "uncategorized"
        coverage[category] = coverage.get(category, 0) + 1
    return {
        "status": audit.get("status"),
        "symbol": audit.get("symbol"),
        "coverage": coverage,
        "gaps": audit.get("gaps") or [],
        "attempt_count": len(audit.get("attempts") or []),
    }
