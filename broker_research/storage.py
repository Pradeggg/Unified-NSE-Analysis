"""PostgreSQL storage helpers for broker research metadata."""

from __future__ import annotations

import json
from typing import Any

from .discovery import DiscoveredReportLink
from .sources import BROKER_SOURCES


def seed_broker_sources(conn: Any) -> int:
    params = [source.as_insert_params() for source in BROKER_SOURCES]
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO company_intel.broker_sources
                (broker_code, broker_name, source_kind, source_url, access_mode, url_pattern, is_active, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (broker_code, source_kind, source_url) DO UPDATE SET
                broker_name = EXCLUDED.broker_name,
                access_mode = EXCLUDED.access_mode,
                url_pattern = EXCLUDED.url_pattern,
                is_active = EXCLUDED.is_active,
                notes = EXCLUDED.notes,
                updated_at = NOW()
            """,
            params,
        )
    conn.commit()
    return len(params)


def list_broker_sources(conn: Any) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT broker_code, broker_name, source_kind, access_mode, is_active, source_url
            FROM company_intel.broker_sources
            ORDER BY broker_code, source_kind, source_url
            """
        )
        rows = cur.fetchall()
    return [
        {
            "broker_code": row[0],
            "broker_name": row[1],
            "source_kind": row[2],
            "access_mode": row[3],
            "is_active": row[4],
            "source_url": row[5],
        }
        for row in rows
    ]


def list_reports_for_fetch(
    conn: Any,
    *,
    symbol: str,
    broker: str = "",
    limit: int = 10,
) -> list[dict[str, Any]]:
    clean_symbol = symbol.strip().upper()
    params: list[Any] = [clean_symbol]
    broker_clause = ""
    if broker:
        broker_clause = "AND broker_code = %s"
        params.append(broker)
    params.append(int(limit))
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT broker_report_id, broker_code, symbol, pdf_url, local_path
            FROM company_intel.broker_reports
            WHERE symbol = %s
              AND pdf_url <> ''
              AND fetch_status IN ('not_fetched', 'fetch_error', 'pdf_too_large')
              {broker_clause}
            ORDER BY broker_code, broker_report_id
            LIMIT %s
            """,
            tuple(params),
        )
        rows = cur.fetchall()
    return [
        {
            "broker_report_id": row[0],
            "broker_code": row[1],
            "symbol": row[2],
            "pdf_url": row[3],
            "local_path": row[4],
        }
        for row in rows
    ]


def list_broker_research_facts(conn: Any, *, symbol: str) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                f.broker_report_id,
                r.broker_code,
                f.symbol,
                r.report_title,
                r.pdf_url,
                f.fact_type,
                f.fact_value,
                f.page_number
            FROM company_intel.broker_research_facts f
            JOIN company_intel.broker_reports r
              ON r.broker_report_id = f.broker_report_id
            WHERE f.symbol = %s
            ORDER BY r.broker_code, f.broker_report_id, f.fact_type, f.fact_id
            """,
            (symbol.strip().upper(),),
        )
        rows = cur.fetchall()
    return [
        {
            "broker_report_id": row[0],
            "broker_code": row[1],
            "symbol": row[2],
            "report_title": row[3],
            "pdf_url": row[4],
            "fact_type": row[5],
            "fact_value": row[6],
            "page_number": row[7],
        }
        for row in rows
    ]


def record_index_run(conn: Any, *, source_id: int | None) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO company_intel.broker_index_runs (source_id)
            VALUES (%s)
            RETURNING index_run_id
            """,
            (source_id,),
        )
        row = cur.fetchone()
    conn.commit()
    return int(row[0])


def complete_index_run(
    conn: Any,
    *,
    index_run_id: int,
    status: str,
    reports_found: int,
    reports_new: int,
    http_status: int | None = None,
    failure_reason: str = "",
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE company_intel.broker_index_runs
            SET completed_at = NOW(),
                status = %s,
                http_status = %s,
                reports_found = %s,
                reports_new = %s,
                failure_reason = %s
            WHERE index_run_id = %s
            """,
            (status, http_status, reports_found, reports_new, failure_reason, index_run_id),
        )
    conn.commit()


def upsert_discovered_report(
    conn: Any,
    *,
    symbol: str,
    company_name: str,
    link: DiscoveredReportLink,
    match_score: float,
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO company_intel.broker_reports
                (broker_code, symbol, company_name, report_title, source_url, pdf_url, discovered_via, match_score)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (broker_code, pdf_url) DO UPDATE SET
                symbol = EXCLUDED.symbol,
                company_name = EXCLUDED.company_name,
                report_title = EXCLUDED.report_title,
                source_url = EXCLUDED.source_url,
                discovered_via = EXCLUDED.discovered_via,
                match_score = EXCLUDED.match_score,
                updated_at = NOW()
            RETURNING broker_report_id
            """,
            (
                link.broker_code,
                symbol.strip().upper(),
                company_name,
                link.title,
                link.source_url,
                link.pdf_url,
                "broker_index",
                float(match_score),
            ),
        )
        row = cur.fetchone()
    conn.commit()
    return int(row[0])


def find_report_by_hash(conn: Any, pdf_hash: str) -> dict[str, Any] | None:
    if not pdf_hash:
        return None
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT broker_report_id, broker_code, symbol, local_path
            FROM company_intel.broker_reports
            WHERE pdf_hash = %s AND local_path <> ''
            ORDER BY updated_at DESC, broker_report_id DESC
            LIMIT 1
            """,
            (pdf_hash,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return {
        "broker_report_id": row[0],
        "broker_code": row[1],
        "symbol": row[2],
        "local_path": row[3],
    }


def update_report_fetch_metadata(
    conn: Any,
    *,
    broker_report_id: int,
    fetch_status: str,
    pdf_hash: str = "",
    local_path: str = "",
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE company_intel.broker_reports
            SET fetch_status = %s,
                pdf_hash = %s,
                local_path = %s,
                updated_at = NOW()
            WHERE broker_report_id = %s
            """,
            (fetch_status, pdf_hash, local_path, broker_report_id),
        )
    conn.commit()


def replace_report_pages(conn: Any, *, broker_report_id: int, pages: list[dict[str, Any]]) -> int:
    rows = [
        (
            broker_report_id,
            int(page.get("page_number") or 0),
            str(page.get("text") or ""),
            int(page.get("char_count") if page.get("char_count") is not None else len(str(page.get("text") or ""))),
        )
        for page in pages
        if int(page.get("page_number") or 0) > 0
    ]
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM company_intel.broker_report_pages
            WHERE broker_report_id = %s
            """,
            (broker_report_id,),
        )
        if rows:
            cur.executemany(
                """
                INSERT INTO company_intel.broker_report_pages
                    (broker_report_id, page_number, text, char_count)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (broker_report_id, page_number) DO UPDATE SET
                    text = EXCLUDED.text,
                    char_count = EXCLUDED.char_count
                """,
                rows,
            )
    conn.commit()
    return len(rows)


def update_report_parse_status(conn: Any, *, broker_report_id: int, parse_status: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE company_intel.broker_reports
            SET parse_status = %s,
                updated_at = NOW()
            WHERE broker_report_id = %s
            """,
            (parse_status, broker_report_id),
        )
    conn.commit()


def insert_broker_research_facts(conn: Any, facts: list[dict[str, Any]]) -> int:
    rows = [
        (
            int(fact["broker_report_id"]),
            str(fact["symbol"]).strip().upper(),
            str(fact["fact_type"]),
            str(fact["fact_name"]),
            str(fact["fact_value"]),
            str(fact.get("unit") or ""),
            str(fact.get("period") or ""),
            int(fact["page_number"]) if fact.get("page_number") is not None else None,
            float(fact.get("confidence") or 0.0),
            str(fact.get("extractor") or "deterministic"),
        )
        for fact in facts
    ]
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO company_intel.broker_research_facts
                (broker_report_id, symbol, fact_type, fact_name, fact_value, unit, period, page_number, confidence, extractor)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            rows,
        )
    conn.commit()
    return len(rows)


def record_broker_research_run(
    conn: Any,
    *,
    symbol: str,
    objective: str,
    broker_filter: str,
    status: str,
    coverage: dict[str, Any],
    report_markdown_path: str = "",
    report_html_path: str = "",
    report_pdf_path: str = "",
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO company_intel.broker_research_runs
                (symbol, objective, broker_filter, status, report_markdown_path, report_html_path, report_pdf_path, coverage_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            RETURNING research_run_id
            """,
            (
                symbol.strip().upper(),
                objective,
                broker_filter,
                status,
                report_markdown_path,
                report_html_path,
                report_pdf_path,
                json.dumps(coverage, sort_keys=True),
            ),
        )
        row = cur.fetchone()
    conn.commit()
    return int(row[0])
