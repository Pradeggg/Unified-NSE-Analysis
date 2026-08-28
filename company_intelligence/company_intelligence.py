"""Orchestration for Company + Sector X-Ray intelligence."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path

from .company_intelligence_analyze import (
    build_deliberation_view,
    score_evidence_coverage,
    strict_mode_passes,
)
from .company_intelligence_db import (
    add_company_alias,
    init_company_intelligence_db,
    record_analysis_run,
    upsert_company,
)
from .company_intelligence_extract import store_evidence_chunk
from .company_intelligence_promote import load_indexed_evidence_records, promote_indexed_company_evidence
from .company_intelligence_report import (
    render_company_xray_html,
    render_company_xray_markdown,
    write_company_xray_report,
)
from .company_intelligence_search import complete_search_run, log_search_attempt, start_search_run


DEFAULT_DB_PATH = Path("data/company_intelligence/company_intelligence.db")
DEFAULT_REPORT_DIR = Path("reports/company_xray")


def run_company_xray(
    symbol: str,
    strict: bool = False,
    refresh: bool = False,
    db_path: str | Path = DEFAULT_DB_PATH,
    output_dir: str | Path = DEFAULT_REPORT_DIR,
    evidence_records: list[dict] | None = None,
    search_attempts: list[dict] | None = None,
    company_profile: dict | None = None,
    policy_impacts: list[dict] | None = None,
    include_indexed_evidence: bool = True,
    pdf_parser=None,
) -> dict:
    """Run a deterministic Company X-Ray slice and write Markdown/HTML reports."""
    clean_symbol = symbol.strip().upper()
    db = init_company_intelligence_db(db_path)
    evidence_records = evidence_records or []
    search_attempts = search_attempts or []
    company_profile = company_profile or {"symbol": clean_symbol, "company_name": _default_company_name(clean_symbol)}
    policy_impacts = policy_impacts or []

    with sqlite3.connect(db) as conn:
        upsert_company(
            conn,
            clean_symbol,
            company_name=company_profile.get("company_name", _default_company_name(clean_symbol)),
            sector=company_profile.get("sector", ""),
            industry=company_profile.get("industry", ""),
            website=company_profile.get("website", ""),
        )
        for alias in _default_aliases(clean_symbol, company_profile):
            add_company_alias(conn, clean_symbol, alias, "system")

        run_id = start_search_run(conn, clean_symbol, _verticals_from_attempts(search_attempts), "strict" if strict else "permissive")
        for attempt in search_attempts:
            log_search_attempt(
                conn,
                run_id,
                source_group=attempt.get("source_group", "external_context"),
                query=attempt.get("query", ""),
                alias_used=attempt.get("alias_used", clean_symbol),
                result_count=int(attempt.get("result_count", 0)),
                urls_found=list(attempt.get("urls_found", [])),
                status=attempt.get("status", "unknown"),
                failure_reason=attempt.get("failure_reason", ""),
            )
        complete_search_run(conn, run_id, "completed", "Company X-Ray search audit completed.")

        indexed_promotion = {
            "website_chunks_promoted": 0,
            "documents_parsed": 0,
            "document_chunks_promoted": 0,
            "document_errors": 0,
        }
        if include_indexed_evidence:
            indexed_promotion = promote_indexed_company_evidence(conn, clean_symbol, pdf_parser=pdf_parser)
            if indexed_promotion["website_chunks_promoted"] or indexed_promotion["document_chunks_promoted"]:
                indexed_attempt = {
                    "source_group": "company_ir",
                    "query": f"{clean_symbol} indexed company website and investor documents",
                    "alias_used": clean_symbol,
                    "result_count": indexed_promotion["website_chunks_promoted"]
                    + indexed_promotion["document_chunks_promoted"],
                    "urls_found": [],
                    "status": "parsed",
                    "failure_reason": "",
                    "vertical": "website_index",
                }
                search_attempts.append(indexed_attempt)
                log_search_attempt(
                    conn,
                    run_id,
                    source_group=indexed_attempt["source_group"],
                    query=indexed_attempt["query"],
                    alias_used=indexed_attempt["alias_used"],
                    result_count=indexed_attempt["result_count"],
                    urls_found=[],
                    status=indexed_attempt["status"],
                    failure_reason="",
                )

        stored_evidence = []
        for row in evidence_records:
            chunk_id = store_evidence_chunk(
                conn,
                document_id=row.get("document_id", "manual"),
                symbol=clean_symbol,
                category=row.get("category", "uncategorized"),
                text=row.get("text", ""),
                source_tier=int(row.get("source_tier", 3)),
                confidence=float(row.get("confidence", 0.5)),
                page_number=row.get("page_number"),
                table_id=row.get("table_id", ""),
                evidence_date=row.get("evidence_date", ""),
            )
            stored = dict(row)
            stored.update({"chunk_id": chunk_id, "symbol": clean_symbol})
            stored_evidence.append(stored)
        if include_indexed_evidence:
            existing_ids = {int(row["chunk_id"]) for row in stored_evidence if row.get("chunk_id") is not None}
            for row in load_indexed_evidence_records(conn, clean_symbol):
                if int(row["chunk_id"]) not in existing_ids:
                    stored_evidence.append(row)

        coverage = score_evidence_coverage(stored_evidence, search_attempts)
        strict_ok, strict_failures = strict_mode_passes(coverage)
        status = "blocked" if strict and not strict_ok else "ok"
        model = _build_report_model(clean_symbol, company_profile, stored_evidence, coverage, policy_impacts, status, strict_failures)
        markdown = render_company_xray_markdown(model)
        html = render_company_xray_html(model)
        paths = write_company_xray_report(clean_symbol, markdown, html, Path(output_dir))

        record_analysis_run(
            conn,
            clean_symbol,
            workflow="company_xray",
            mode="strict" if strict else "permissive",
            status=status,
            report_path=paths["markdown"],
            coverage_score=_coverage_score(coverage),
            known_gaps=json.dumps(coverage.get("known_gaps", []) + strict_failures),
        )

    return {
        "symbol": clean_symbol,
        "status": status,
        "strict": strict,
        "refresh": refresh,
        "coverage": coverage,
        "known_gaps": coverage.get("known_gaps", []),
        "strict_failures": strict_failures,
        "report_markdown_path": paths["markdown"],
        "report_html_path": paths["html"],
        "indexed_promotion": indexed_promotion,
    }


def _build_report_model(
    symbol: str,
    company_profile: dict,
    evidence: list[dict],
    coverage: dict,
    policy_impacts: list[dict],
    status: str,
    strict_failures: list[str],
) -> dict:
    by_category = defaultdict(list)
    for row in evidence:
        by_category[row.get("category", "uncategorized")].append(row)
    deliberation = build_deliberation_view(symbol, by_category, coverage, policy_impacts)
    sections = {
        "business_model": _texts(by_category.get("business model", [])),
        "customer_base": _texts(by_category.get("customer base", [])),
        "sector_structure": _texts(by_category.get("sector structure", [])),
        "market_share": _texts(by_category.get("market share", [])),
        "competitors": _texts(by_category.get("competitor list", [])),
        "rbi_impact": [row.get("rationale", "") for row in policy_impacts if row.get("impact_area") != "consumer_demand"],
        "budget_impact": [row.get("rationale", "") for row in policy_impacts if row.get("impact_area") == "consumer_demand"],
    }
    if status == "blocked":
        sections["business_model"] = strict_failures
    return {
        "symbol": symbol,
        "company_name": company_profile.get("company_name", symbol),
        "coverage": coverage,
        "sections": sections,
        "deliberation": deliberation,
        "evidence": evidence,
    }


def _texts(rows: list[dict]) -> list[str]:
    return [row.get("text", "") for row in rows if row.get("text")]


def _default_company_name(symbol: str) -> str:
    return {"DMART": "Avenue Supermarts Ltd"}.get(symbol, symbol)


def _default_aliases(symbol: str, company_profile: dict) -> list[str]:
    aliases = [symbol]
    if symbol == "DMART":
        aliases.extend(["Avenue Supermarts", "Avenue Supermarts Ltd", "AVENUE SUPERMARTS"])
    if company_profile.get("company_name"):
        aliases.append(company_profile["company_name"])
    return aliases


def _verticals_from_attempts(search_attempts: list[dict]) -> list[str]:
    verticals = sorted({attempt.get("vertical", "general") for attempt in search_attempts})
    return verticals or ["general"]


def _coverage_score(coverage: dict) -> float:
    values = [value for key, value in coverage.items() if key != "known_gaps"]
    score = 0
    for value in values:
        if value == "High":
            score += 1
        elif value == "Medium":
            score += 0.5
    return score / max(len(values), 1)
