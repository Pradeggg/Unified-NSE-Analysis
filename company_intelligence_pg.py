"""PostgreSQL storage helpers for Company Intelligence.

The canonical company/web intelligence store lives in ``company_intel``.
Legacy SQLite helpers remain only as a migration bridge while callers are
cut over module by module.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


DEFAULT_DSN = os.environ.get("AGENT_ADDA_PG_DSN") or os.environ.get("PG_DSN") or "dbname=nse_market user=nse_admin host=/tmp"
SCHEMA_PATH = Path(__file__).parent / "postgres" / "migrations" / "20260612_company_intel.sql"
REQUIRED_TABLES = [
    "companies",
    "company_aliases",
    "source_documents",
    "search_runs",
    "search_attempts",
    "evidence_chunks",
    "structured_facts",
    "sector_entities",
    "macro_policy_events",
    "impact_assessments",
    "analysis_runs",
    "website_crawl_runs",
    "website_pages",
    "website_links",
    "website_page_chunks",
    "broker_sources",
    "broker_index_runs",
    "broker_reports",
    "broker_report_pages",
    "broker_report_tables",
    "broker_research_facts",
    "broker_research_runs",
]


class CompanyIntelligencePgError(RuntimeError):
    pass


def connect(dsn: str | None = None):
    try:
        import psycopg2
    except Exception as exc:  # pragma: no cover - depends on local env
        raise CompanyIntelligencePgError(f"psycopg2 unavailable: {exc}") from exc
    return psycopg2.connect(dsn or DEFAULT_DSN)


def schema_sql() -> str:
    return SCHEMA_PATH.read_text(encoding="utf-8")


def init_company_intelligence_pg(*, conn: Any | None = None, dsn: str | None = None) -> dict[str, Any]:
    own_conn = conn is None
    db = conn or connect(dsn)
    try:
        with db.cursor() as cur:
            cur.execute(schema_sql())
        db.commit()
        return {"status": "ready", "schema": "company_intel", "tables": REQUIRED_TABLES}
    finally:
        if own_conn:
            db.close()


def upsert_company(
    conn: Any,
    symbol: str,
    company_name: str = "",
    sector: str = "",
    industry: str = "",
    website: str = "",
    bse_code: str = "",
    isin: str = "",
) -> None:
    normalized = symbol.strip().upper()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO company_intel.companies
                (symbol, company_name, bse_code, isin, sector, industry, website)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol) DO UPDATE SET
                company_name = EXCLUDED.company_name,
                bse_code = EXCLUDED.bse_code,
                isin = EXCLUDED.isin,
                sector = EXCLUDED.sector,
                industry = EXCLUDED.industry,
                website = EXCLUDED.website,
                updated_at = NOW()
            """,
            (normalized, company_name, bse_code, isin, sector, industry, website),
        )
    conn.commit()


def add_company_alias(
    conn: Any,
    symbol: str,
    alias: str,
    alias_type: str,
    source: str = "system",
) -> None:
    clean_alias = alias.strip()
    if not clean_alias:
        return
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO company_intel.company_aliases (symbol, alias, alias_type, source)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (symbol, alias) DO NOTHING
            """,
            (symbol.strip().upper(), clean_alias, alias_type, source),
        )
    conn.commit()


def get_company_aliases(conn: Any, symbol: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT alias
            FROM company_intel.company_aliases
            WHERE symbol = %s
            ORDER BY lower(alias), alias
            """,
            (symbol.strip().upper(),),
        )
        rows = cur.fetchall()
    return [row[0] for row in rows]


def record_analysis_run(
    conn: Any,
    symbol: str,
    workflow: str,
    mode: str,
    status: str,
    report_path: str = "",
    coverage_score: float = 0.0,
    known_gaps: str = "[]",
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO company_intel.analysis_runs
                (symbol, workflow, mode, status, completed_at, report_path, coverage_score, known_gaps)
            VALUES (%s, %s, %s, %s, NOW(), %s, %s, %s::jsonb)
            RETURNING analysis_run_id
            """,
            (
                symbol.strip().upper(),
                workflow,
                mode,
                status,
                report_path,
                float(coverage_score),
                known_gaps,
            ),
        )
        row = cur.fetchone()
    conn.commit()
    return int(row[0])
