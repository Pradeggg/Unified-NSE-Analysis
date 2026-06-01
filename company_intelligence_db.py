"""SQLite storage helpers for Company + Sector X-Ray intelligence.

INTENTIONAL STANDALONE SQLite — NOT migrated to PostgreSQL.
------------------------------------------------------------
The company intelligence knowledge graph (website crawl, official documents,
investor pages, evidence chains) is a document/graph store, not a time-series
analytical store.  SQLite is appropriate here because:

  1. The schema is complex and document-centric (JSON evidence blobs, nested
     hierarchies) — no analytical queries that benefit from PG column indexes.
  2. The DB is written only during on-demand crawl jobs (/company-index), not
     during the nightly refresh pipeline.
  3. It is a local cache; losing it is safe (re-crawl restores it).

If a PostgreSQL migration is desired in the future, the target schema would
be under a new ``company_intel.*`` schema in ``nse_market``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS companies (
        symbol TEXT PRIMARY KEY,
        company_name TEXT DEFAULT '',
        bse_code TEXT DEFAULT '',
        isin TEXT DEFAULT '',
        sector TEXT DEFAULT '',
        industry TEXT DEFAULT '',
        website TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS company_aliases (
        symbol TEXT NOT NULL,
        alias TEXT NOT NULL,
        alias_type TEXT NOT NULL,
        source TEXT DEFAULT 'system',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (symbol, alias)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS source_documents (
        document_id TEXT PRIMARY KEY,
        symbol TEXT DEFAULT '',
        source_tier INTEGER NOT NULL,
        source_name TEXT NOT NULL,
        source_url TEXT DEFAULT '',
        document_type TEXT DEFAULT '',
        document_date TEXT DEFAULT '',
        local_path TEXT DEFAULT '',
        content_hash TEXT DEFAULT '',
        fetch_status TEXT DEFAULT '',
        parse_status TEXT DEFAULT '',
        failure_reason TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS search_runs (
        search_run_id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        verticals TEXT NOT NULL,
        mode TEXT NOT NULL,
        started_at TEXT DEFAULT CURRENT_TIMESTAMP,
        completed_at TEXT DEFAULT '',
        status TEXT DEFAULT 'running',
        summary TEXT DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS search_attempts (
        attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
        search_run_id INTEGER NOT NULL,
        source_group TEXT NOT NULL,
        query TEXT NOT NULL,
        alias_used TEXT DEFAULT '',
        result_count INTEGER DEFAULT 0,
        urls_found TEXT DEFAULT '[]',
        status TEXT NOT NULL,
        failure_reason TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS evidence_chunks (
        chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id TEXT NOT NULL,
        symbol TEXT NOT NULL,
        category TEXT NOT NULL,
        text TEXT NOT NULL,
        page_number INTEGER,
        table_id TEXT DEFAULT '',
        source_tier INTEGER NOT NULL,
        confidence REAL NOT NULL,
        evidence_date TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS structured_facts (
        fact_id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        category TEXT NOT NULL,
        fact_name TEXT NOT NULL,
        fact_value TEXT NOT NULL,
        unit TEXT DEFAULT '',
        period TEXT DEFAULT '',
        evidence_chunk_id INTEGER,
        confidence REAL NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sector_entities (
        sector TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        entity_name TEXT NOT NULL,
        symbol TEXT DEFAULT '',
        relationship TEXT DEFAULT '',
        evidence_chunk_id INTEGER,
        confidence REAL DEFAULT 0.0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS macro_policy_events (
        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        event_date TEXT NOT NULL,
        title TEXT NOT NULL,
        source_url TEXT DEFAULT '',
        summary TEXT DEFAULT '',
        raw_path TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS impact_assessments (
        impact_id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        event_id INTEGER,
        impact_area TEXT NOT NULL,
        direction TEXT NOT NULL,
        magnitude TEXT NOT NULL,
        rationale TEXT NOT NULL,
        evidence_chunk_ids TEXT DEFAULT '[]',
        confidence REAL NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS analysis_runs (
        analysis_run_id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        workflow TEXT NOT NULL,
        mode TEXT NOT NULL,
        started_at TEXT DEFAULT CURRENT_TIMESTAMP,
        completed_at TEXT DEFAULT '',
        status TEXT DEFAULT 'running',
        report_path TEXT DEFAULT '',
        coverage_score REAL DEFAULT 0.0,
        known_gaps TEXT DEFAULT '[]'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS website_crawl_runs (
        crawl_run_id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        base_url TEXT NOT NULL,
        started_at TEXT DEFAULT CURRENT_TIMESTAMP,
        completed_at TEXT DEFAULT '',
        status TEXT DEFAULT 'running',
        pages_seen INTEGER DEFAULT 0,
        pages_indexed INTEGER DEFAULT 0,
        documents_found INTEGER DEFAULT 0,
        failure_reason TEXT DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS website_pages (
        page_id INTEGER PRIMARY KEY AUTOINCREMENT,
        crawl_run_id INTEGER NOT NULL,
        symbol TEXT NOT NULL,
        url TEXT NOT NULL,
        url_hash TEXT NOT NULL,
        title TEXT DEFAULT '',
        content_hash TEXT DEFAULT '',
        content_type TEXT DEFAULT '',
        status TEXT DEFAULT '',
        fetched_at TEXT DEFAULT CURRENT_TIMESTAMP,
        raw_path TEXT DEFAULT '',
        text TEXT DEFAULT '',
        page_type TEXT DEFAULT '',
        UNIQUE(symbol, url_hash)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS website_links (
        link_id INTEGER PRIMARY KEY AUTOINCREMENT,
        crawl_run_id INTEGER NOT NULL,
        symbol TEXT NOT NULL,
        from_url TEXT NOT NULL,
        to_url TEXT NOT NULL,
        link_text TEXT DEFAULT '',
        link_type TEXT DEFAULT '',
        is_same_domain INTEGER DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS website_page_chunks (
        chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,
        page_id INTEGER NOT NULL,
        symbol TEXT NOT NULL,
        url TEXT NOT NULL,
        chunk_text TEXT NOT NULL,
        category TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS website_search_fts
    USING fts5(symbol UNINDEXED, url UNINDEXED, title, category, chunk_text)
    """,
]


def init_company_intelligence_db(db_path: str | Path) -> Path:
    """Create the company intelligence SQLite database and return its path."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        for statement in SCHEMA:
            conn.execute(statement)
        conn.commit()
    return path


def upsert_company(
    conn: sqlite3.Connection,
    symbol: str,
    company_name: str = "",
    sector: str = "",
    industry: str = "",
    website: str = "",
) -> None:
    normalized = symbol.strip().upper()
    conn.execute(
        """
        INSERT INTO companies (symbol, company_name, sector, industry, website)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(symbol) DO UPDATE SET
            company_name = excluded.company_name,
            sector = excluded.sector,
            industry = excluded.industry,
            website = excluded.website,
            updated_at = CURRENT_TIMESTAMP
        """,
        (normalized, company_name, sector, industry, website),
    )
    conn.commit()


def add_company_alias(
    conn: sqlite3.Connection,
    symbol: str,
    alias: str,
    alias_type: str,
    source: str = "system",
) -> None:
    clean_alias = alias.strip()
    if not clean_alias:
        return
    conn.execute(
        """
        INSERT OR IGNORE INTO company_aliases (symbol, alias, alias_type, source)
        VALUES (?, ?, ?, ?)
        """,
        (symbol.strip().upper(), clean_alias, alias_type, source),
    )
    conn.commit()


def get_company_aliases(conn: sqlite3.Connection, symbol: str) -> list[str]:
    rows = conn.execute(
        "SELECT alias FROM company_aliases WHERE symbol = ? ORDER BY alias COLLATE NOCASE",
        (symbol.strip().upper(),),
    ).fetchall()
    return [row[0] for row in rows]


def record_analysis_run(
    conn: sqlite3.Connection,
    symbol: str,
    workflow: str,
    mode: str,
    status: str,
    report_path: str = "",
    coverage_score: float = 0.0,
    known_gaps: str = "[]",
) -> int:
    cur = conn.execute(
        """
        INSERT INTO analysis_runs
            (symbol, workflow, mode, status, completed_at, report_path, coverage_score, known_gaps)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?)
        """,
        (symbol.strip().upper(), workflow, mode, status, report_path, coverage_score, known_gaps),
    )
    conn.commit()
    return int(cur.lastrowid)
