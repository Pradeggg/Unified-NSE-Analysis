"""PostgreSQL storage helpers for broker research metadata."""

from __future__ import annotations

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
