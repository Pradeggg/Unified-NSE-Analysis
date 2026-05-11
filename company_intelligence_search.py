"""Search audit and query planning for Company + Sector X-Ray."""

from __future__ import annotations

import json
import sqlite3


VERTICAL_PATTERNS = {
    "company_website": [
        "{alias} business model site:company_website",
        "{alias} products customers operating model",
    ],
    "investor_relations": [
        "{alias} investor relations annual report",
        "{alias} investor presentation results transcript",
    ],
    "annual_reports": [
        "{alias} annual report",
        "{alias} annual-report pdf",
    ],
    "investor_presentations": [
        "{alias} investor presentation",
        "{alias} results presentation",
    ],
    "concall_transcripts": [
        "{alias} concall transcript",
        "{alias} earnings call transcript",
    ],
    "product_pages": [
        "{alias} products services",
        "{alias} business divisions",
    ],
    "store_network": [
        "{alias} store network",
        "{alias} capacity footprint distribution",
    ],
    "leadership": [
        "{alias} management leadership board",
    ],
    "customers": [
        "{alias} customers client base",
        "{alias} customer concentration",
    ],
    "suppliers": [
        "{alias} suppliers supply chain vendors",
    ],
    "market_share": [
        "{alias} market share",
        "{alias} industry position",
    ],
    "competitors": [
        "{alias} competitors peers",
        "{alias} competitive landscape",
    ],
    "regulatory": [
        "{alias} regulatory approvals compliance",
    ],
    "litigation": [
        "{alias} litigation legal dispute",
    ],
    "ratings": [
        "{alias} credit rating rationale",
    ],
    "budget_impact": [
        "{alias} Union Budget impact",
        "{alias} budget tax capex impact",
    ],
    "rbi_impact": [
        "{alias} RBI monetary policy impact",
        "{alias} interest rate sensitivity",
    ],
    "analyst_coverage": [
        "{alias} analyst coverage",
        "{alias} analyst rating",
    ],
    "broker_research": [
        "{alias} broker research",
        "{alias} research report",
        "{alias} investor presentation",
    ],
    "concalls": [
        "{alias} concall transcript",
        "{alias} earnings call transcript",
        "{alias} investor presentation",
    ],
}

VERTICAL_SOURCE_GROUPS = {
    "company_website": "website_index",
    "investor_relations": "website_index",
    "annual_reports": "website_index",
    "investor_presentations": "website_index",
    "concall_transcripts": "website_index",
    "product_pages": "website_index",
    "store_network": "website_index",
    "leadership": "website_index",
    "budget_impact": "official_policy",
    "rbi_impact": "official_policy",
}


def start_search_run(
    conn: sqlite3.Connection,
    symbol: str,
    verticals: list[str],
    mode: str,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO search_runs (symbol, verticals, mode, status)
        VALUES (?, ?, ?, 'running')
        """,
        (symbol.strip().upper(), json.dumps(verticals), mode),
    )
    conn.commit()
    return int(cur.lastrowid)


def log_search_attempt(
    conn: sqlite3.Connection,
    search_run_id: int,
    source_group: str,
    query: str,
    alias_used: str,
    result_count: int,
    urls_found: list[str],
    status: str,
    failure_reason: str = "",
) -> int:
    cur = conn.execute(
        """
        INSERT INTO search_attempts
            (search_run_id, source_group, query, alias_used, result_count, urls_found, status, failure_reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            search_run_id,
            source_group,
            query,
            alias_used,
            int(result_count),
            json.dumps(urls_found),
            status,
            failure_reason,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def complete_search_run(
    conn: sqlite3.Connection,
    search_run_id: int,
    status: str,
    summary: str = "",
) -> None:
    conn.execute(
        """
        UPDATE search_runs
        SET status = ?, summary = ?, completed_at = CURRENT_TIMESTAMP
        WHERE search_run_id = ?
        """,
        (status, summary, search_run_id),
    )
    conn.commit()


def build_search_queries(symbol: str, aliases: list[str], verticals: list[str]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    ordered_aliases = []
    for alias in [symbol, *aliases]:
        clean = alias.strip()
        if clean and clean not in ordered_aliases:
            ordered_aliases.append(clean)

    queries: list[dict] = []
    for vertical in verticals:
        patterns = VERTICAL_PATTERNS.get(vertical, [f"{{alias}} {vertical.replace('_', ' ')}"])
        for alias in ordered_aliases:
            for pattern in patterns:
                query = pattern.format(alias=alias)
                key = (vertical, query)
                if key in seen:
                    continue
                seen.add(key)
                queries.append(
                    {
                        "vertical": vertical,
                        "alias": alias,
                        "query": query,
                        "source_group": VERTICAL_SOURCE_GROUPS.get(vertical, "external_context"),
                    }
                )
    return queries
