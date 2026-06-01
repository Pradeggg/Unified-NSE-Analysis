# SQLite to Postgres Full Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate all active SQLite-backed tables and runtime code paths to PostgreSQL, leaving SQLite only in migration fixtures, archived files, and documentation.

**Architecture:** Add a shared PostgreSQL access layer and missing schemas first, then move each SQLite-backed subsystem to PostgreSQL behind focused tests. Existing canonical PG tables remain the target for market, stage, breadth, and F&O data; company intelligence and Agent Adda historical data get explicit PG schemas/tables.

**Tech Stack:** Python, PostgreSQL, psycopg2, pandas, pytest, existing `postgres/schema.sql` and `postgres/migrate.py` migration stack.

---

## File Structure

- Create: `terminal/db.py`  
  Shared DSN resolution and psycopg2 connection helpers for runtime modules.

- Modify: `postgres/schema.sql`  
  Add `intelligence` and `agent_adda` schemas, tables, full-text indexes, and helper indexes.

- Modify: `postgres/migrate.py`  
  Add audit/parity helpers and new migration sections for company intelligence and Agent Adda historical SQLite data.

- Modify: `terminal/portfolio_monitor.py`  
  Replace `sector_rotation_tracker.db` reads with `scores.stage_snapshots`.

- Modify: `terminal/reports.py`  
  Replace sector rotation SQLite report reads with `scores.stage_snapshots` and `scores.stage_changes`.

- Modify: `terminal/data_readiness.py`  
  Remove production SQLite readiness fallback and report PostgreSQL coverage.

- Modify: `terminal/tools.py`  
  Remove production SQLite stage/F&O fallbacks where equivalent PG queries exist.

- Modify: `terminal/fno_data.py`  
  Keep PostgreSQL as the only runtime store for F&O EOD data.

- Modify: `company_intelligence_db.py`, `company_intelligence_extract.py`, `company_intelligence_search.py`, `company_intelligence_promote.py`, `company_intelligence_policy.py`, `company_intelligence.py`  
  Move company intelligence persistence from SQLite to PostgreSQL.

- Modify: `agent_adda/config/settings.py`, `agent_adda/doctor.py`, `agent_adda/data/historical.py`  
  Replace local SQLite config/data paths with PostgreSQL DSN-backed historical loading and doctor checks.

- Modify tests under `tests/` that currently import `sqlite3` for active runtime modules.  
  Convert runtime tests to PostgreSQL-backed fakes or monkeypatched connection helpers; keep SQLite only for migration fixture tests.

---

### Task 1: Shared PostgreSQL Runtime Helper

**Files:**
- Create: `terminal/db.py`
- Modify: `terminal/tools.py`
- Modify: `terminal/fno_data.py`
- Modify: `terminal/portfolio_monitor.py`
- Test: `tests/test_terminal_db.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_terminal_db.py`:

```python
import os

from terminal import db


def test_default_dsn_prefers_agent_adda_pg_dsn(monkeypatch):
    monkeypatch.setenv("AGENT_ADDA_PG_DSN", "dbname=agent")
    monkeypatch.setenv("PG_DSN", "dbname=pg")

    assert db.default_dsn() == "dbname=agent"


def test_default_dsn_falls_back_to_pg_dsn(monkeypatch):
    monkeypatch.delenv("AGENT_ADDA_PG_DSN", raising=False)
    monkeypatch.setenv("PG_DSN", "dbname=pg")

    assert db.default_dsn() == "dbname=pg"


def test_default_dsn_has_local_default(monkeypatch):
    monkeypatch.delenv("AGENT_ADDA_PG_DSN", raising=False)
    monkeypatch.delenv("PG_DSN", raising=False)

    assert db.default_dsn() == "dbname=nse_market user=nse_admin host=/tmp"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_terminal_db.py -q`  
Expected: FAIL with `ImportError` or missing `terminal.db`.

- [ ] **Step 3: Add shared helper**

Create `terminal/db.py`:

```python
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator


DEFAULT_DSN = "dbname=nse_market user=nse_admin host=/tmp"


def default_dsn() -> str:
    return os.environ.get("AGENT_ADDA_PG_DSN") or os.environ.get("PG_DSN") or DEFAULT_DSN


def connect(dsn: str | None = None):
    import psycopg2

    return psycopg2.connect(dsn or default_dsn())


@contextmanager
def cursor(dsn: str | None = None, *, dict_rows: bool = False) -> Iterator:
    import psycopg2.extras

    factory = psycopg2.extras.RealDictCursor if dict_rows else None
    conn = connect(dsn)
    try:
        with conn.cursor(cursor_factory=factory) as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
```

- [ ] **Step 4: Wire existing modules to use the helper**

In `terminal/tools.py`, `terminal/fno_data.py`, and `terminal/portfolio_monitor.py`, replace duplicated PG DSN constants and direct `psycopg2.connect(PG_DSN)` helpers with:

```python
from terminal.db import connect as pg_connect
from terminal.db import default_dsn

PG_DSN = default_dsn()


def _pg_conn():
    return pg_connect(PG_DSN)
```

Keep behavior unchanged in this task.

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_terminal_db.py -q`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add terminal/db.py terminal/tools.py terminal/fno_data.py terminal/portfolio_monitor.py tests/test_terminal_db.py
git commit -m "refactor(db): centralize postgres connection settings"
```

---

### Task 2: Add Missing PostgreSQL Schemas

**Files:**
- Modify: `postgres/schema.sql`
- Test: `tests/test_postgres_schema_sqlite_cutover.py`

- [ ] **Step 1: Write schema presence tests**

Create `tests/test_postgres_schema_sqlite_cutover.py`:

```python
from pathlib import Path


SCHEMA = Path("postgres/schema.sql").read_text(encoding="utf-8")


def test_intelligence_schema_tables_are_declared():
    assert "CREATE SCHEMA IF NOT EXISTS intelligence" in SCHEMA
    for table in [
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
    ]:
        assert f"CREATE TABLE IF NOT EXISTS intelligence.{table}" in SCHEMA


def test_agent_adda_historical_tables_are_declared():
    assert "CREATE SCHEMA IF NOT EXISTS agent_adda" in SCHEMA
    assert "CREATE TABLE IF NOT EXISTS agent_adda.daily_prices" in SCHEMA
    assert "CREATE TABLE IF NOT EXISTS agent_adda.data_refresh_log" in SCHEMA


def test_website_search_uses_postgres_full_text_index():
    assert "website_page_chunks_search_idx" in SCHEMA
    assert "to_tsvector('english'" in SCHEMA
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_postgres_schema_sqlite_cutover.py -q`  
Expected: FAIL because the new schemas are not declared.

- [ ] **Step 3: Add schema SQL**

Append this section to `postgres/schema.sql` before the final index section or near related evidence tables:

```sql
-- =============================================================================
-- 9. INTELLIGENCE - Company and sector evidence formerly stored in SQLite
-- =============================================================================
CREATE SCHEMA IF NOT EXISTS intelligence;

CREATE TABLE IF NOT EXISTS intelligence.companies (
    symbol TEXT PRIMARY KEY,
    company_name TEXT DEFAULT '',
    bse_code TEXT DEFAULT '',
    isin TEXT DEFAULT '',
    sector TEXT DEFAULT '',
    industry TEXT DEFAULT '',
    website TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS intelligence.company_aliases (
    symbol TEXT NOT NULL REFERENCES intelligence.companies(symbol) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    alias_type TEXT NOT NULL,
    source TEXT DEFAULT 'system',
    created_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (symbol, alias)
);

CREATE TABLE IF NOT EXISTS intelligence.source_documents (
    document_id TEXT PRIMARY KEY,
    symbol TEXT DEFAULT '',
    source_tier INTEGER NOT NULL,
    source_name TEXT NOT NULL,
    source_url TEXT DEFAULT '',
    document_type TEXT DEFAULT '',
    document_date DATE,
    local_path TEXT DEFAULT '',
    content_hash TEXT DEFAULT '',
    fetch_status TEXT DEFAULT '',
    parse_status TEXT DEFAULT '',
    failure_reason TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS intelligence.search_runs (
    search_run_id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    verticals TEXT NOT NULL,
    mode TEXT NOT NULL,
    started_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ,
    status TEXT DEFAULT 'running',
    summary TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS intelligence.search_attempts (
    attempt_id BIGSERIAL PRIMARY KEY,
    search_run_id BIGINT NOT NULL REFERENCES intelligence.search_runs(search_run_id) ON DELETE CASCADE,
    source_group TEXT NOT NULL,
    query TEXT NOT NULL,
    alias_used TEXT DEFAULT '',
    result_count INTEGER DEFAULT 0,
    urls_found JSONB DEFAULT '[]'::jsonb,
    status TEXT NOT NULL,
    failure_reason TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS intelligence.evidence_chunks (
    chunk_id BIGSERIAL PRIMARY KEY,
    document_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    category TEXT NOT NULL,
    text TEXT NOT NULL,
    page_number INTEGER,
    table_id TEXT DEFAULT '',
    source_tier INTEGER NOT NULL,
    confidence NUMERIC(8,4) NOT NULL,
    evidence_date DATE,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS intelligence.structured_facts (
    fact_id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    category TEXT NOT NULL,
    fact_name TEXT NOT NULL,
    fact_value TEXT NOT NULL,
    unit TEXT DEFAULT '',
    period TEXT DEFAULT '',
    evidence_chunk_id BIGINT REFERENCES intelligence.evidence_chunks(chunk_id),
    confidence NUMERIC(8,4) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS intelligence.sector_entities (
    sector TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_name TEXT NOT NULL,
    symbol TEXT DEFAULT '',
    relationship TEXT DEFAULT '',
    evidence_chunk_id BIGINT,
    confidence NUMERIC(8,4) DEFAULT 0
);

CREATE TABLE IF NOT EXISTS intelligence.macro_policy_events (
    event_id BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    event_date DATE NOT NULL,
    title TEXT NOT NULL,
    source_url TEXT DEFAULT '',
    summary TEXT DEFAULT '',
    raw_path TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS intelligence.impact_assessments (
    impact_id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    event_id BIGINT REFERENCES intelligence.macro_policy_events(event_id),
    impact_area TEXT NOT NULL,
    direction TEXT NOT NULL,
    magnitude TEXT NOT NULL,
    rationale TEXT NOT NULL,
    evidence_chunk_ids JSONB DEFAULT '[]'::jsonb,
    confidence NUMERIC(8,4) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS intelligence.analysis_runs (
    analysis_run_id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    workflow TEXT NOT NULL,
    mode TEXT NOT NULL,
    started_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ,
    status TEXT DEFAULT 'running',
    report_path TEXT DEFAULT '',
    coverage_score NUMERIC(8,4) DEFAULT 0,
    known_gaps JSONB DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS intelligence.website_crawl_runs (
    crawl_run_id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    base_url TEXT NOT NULL,
    started_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ,
    status TEXT DEFAULT 'running',
    pages_seen INTEGER DEFAULT 0,
    pages_indexed INTEGER DEFAULT 0,
    documents_found INTEGER DEFAULT 0,
    failure_reason TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS intelligence.website_pages (
    page_id BIGSERIAL PRIMARY KEY,
    crawl_run_id BIGINT NOT NULL REFERENCES intelligence.website_crawl_runs(crawl_run_id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    url TEXT NOT NULL,
    url_hash TEXT NOT NULL,
    title TEXT DEFAULT '',
    content_hash TEXT DEFAULT '',
    content_type TEXT DEFAULT '',
    status TEXT DEFAULT '',
    fetched_at TIMESTAMPTZ DEFAULT now(),
    raw_path TEXT DEFAULT '',
    text TEXT DEFAULT '',
    page_type TEXT DEFAULT '',
    UNIQUE(symbol, url_hash)
);

CREATE TABLE IF NOT EXISTS intelligence.website_links (
    link_id BIGSERIAL PRIMARY KEY,
    crawl_run_id BIGINT NOT NULL REFERENCES intelligence.website_crawl_runs(crawl_run_id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    from_url TEXT NOT NULL,
    to_url TEXT NOT NULL,
    link_text TEXT DEFAULT '',
    link_type TEXT DEFAULT '',
    is_same_domain BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS intelligence.website_page_chunks (
    chunk_id BIGSERIAL PRIMARY KEY,
    page_id BIGINT NOT NULL REFERENCES intelligence.website_pages(page_id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    url TEXT NOT NULL,
    chunk_text TEXT NOT NULL,
    category TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS website_page_chunks_search_idx
    ON intelligence.website_page_chunks
    USING GIN (to_tsvector('english', coalesce(category, '') || ' ' || coalesce(chunk_text, '')));

CREATE INDEX IF NOT EXISTS company_aliases_trgm_idx
    ON intelligence.company_aliases USING GIN (alias gin_trgm_ops);

-- =============================================================================
-- 10. AGENT_ADDA - Local historical bootstrap formerly stored in SQLite
-- =============================================================================
CREATE SCHEMA IF NOT EXISTS agent_adda;

CREATE TABLE IF NOT EXISTS agent_adda.daily_prices (
    symbol TEXT NOT NULL,
    trade_date DATE NOT NULL,
    open NUMERIC(12,4),
    high NUMERIC(12,4),
    low NUMERIC(12,4),
    close NUMERIC(12,4),
    volume BIGINT,
    source_file TEXT NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (symbol, trade_date, source_file)
);

CREATE TABLE IF NOT EXISTS agent_adda.data_refresh_log (
    id BIGSERIAL PRIMARY KEY,
    source TEXT NOT NULL,
    source_path TEXT NOT NULL,
    rows_loaded INTEGER NOT NULL,
    rows_skipped INTEGER NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL
);
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_postgres_schema_sqlite_cutover.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add postgres/schema.sql tests/test_postgres_schema_sqlite_cutover.py
git commit -m "feat(postgres): add sqlite cutover schemas"
```

---

### Task 3: Add Migration Audit and Parity Reporting

**Files:**
- Modify: `postgres/migrate.py`
- Test: `tests/test_postgres_migrate_audit.py`

- [ ] **Step 1: Write failing unit tests for audit helpers**

Create `tests/test_postgres_migrate_audit.py`:

```python
import sqlite3

from postgres import migrate


def test_sqlite_table_counts_reports_present_tables(tmp_path):
    db = tmp_path / "source.db"
    with sqlite3.connect(db) as conn:
        conn.execute("create table one (id integer primary key)")
        conn.execute("create table two (id integer primary key)")
        conn.execute("insert into one values (1)")
        conn.executemany("insert into two values (?)", [(1,), (2,)])
        conn.commit()

    assert migrate.sqlite_table_counts(db) == {"one": 1, "two": 2}


def test_sqlite_table_counts_missing_db_is_empty(tmp_path):
    assert migrate.sqlite_table_counts(tmp_path / "missing.db") == {}


def test_parity_status_exact_match():
    result = migrate.parity_status(source_count=5, target_count=5)

    assert result == "match"


def test_parity_status_mismatch():
    result = migrate.parity_status(source_count=5, target_count=4)

    assert result == "mismatch"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_postgres_migrate_audit.py -q`  
Expected: FAIL because helper functions do not exist.

- [ ] **Step 3: Add audit helpers**

In `postgres/migrate.py`, add near helper functions:

```python
def sqlite_table_counts(db_path: Path) -> dict[str, int]:
    if not db_path.exists():
        return {}
    conn = sqlite3.connect(db_path)
    try:
        tables = [
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            if not str(row[0]).startswith("sqlite_")
        ]
        counts: dict[str, int] = {}
        for table in tables:
            counts[table] = int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
        return counts
    finally:
        conn.close()


def parity_status(source_count: int, target_count: int) -> str:
    return "match" if int(source_count) == int(target_count) else "mismatch"


def pg_count(cur, table: str, where_sql: str = "", params: tuple | list | None = None) -> int:
    cur.execute(f"SELECT COUNT(*) FROM {table} {where_sql}", params or ())
    row = cur.fetchone()
    return int(row[0] or 0)


def print_parity(source_label: str, source_count: int, target_label: str, target_count: int) -> None:
    status = parity_status(source_count, target_count)
    log(f"parity {source_label} -> {target_label}: source={source_count} target={target_count} status={status}")
```

- [ ] **Step 4: Add optional audit flag**

In `main()`, add:

```python
ap.add_argument("--audit", action="store_true", help="Print SQLite source table counts before migration")
```

After printing DSN, add:

```python
if args.audit:
    for db_path in [
        DATA / "sector_rotation_tracker.db",
        DATA / "fno" / "fno_eod.db",
        DATA / "nse_analysis.db",
        BASE / "nse_analysis.db",
        DATA / "nse_eod.db",
        DATA / "stage_tracker.db",
    ]:
        counts = sqlite_table_counts(db_path)
        log(f"audit {db_path}: {counts if counts else 'missing_or_empty'}")
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_postgres_migrate_audit.py -q`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add postgres/migrate.py tests/test_postgres_migrate_audit.py
git commit -m "feat(migrate): add sqlite source audit helpers"
```

---

### Task 4: Migrate Company Intelligence Data

**Files:**
- Modify: `postgres/migrate.py`
- Test: `tests/test_company_intelligence_pg_migration.py`

- [ ] **Step 1: Write migration test**

Create `tests/test_company_intelligence_pg_migration.py` with a fake cursor that captures upsert calls:

```python
import sqlite3

from postgres import migrate


class FakeCursor:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))


def test_load_company_intelligence_reads_sqlite_tables(tmp_path, monkeypatch):
    db = tmp_path / "company_intelligence.db"
    with sqlite3.connect(db) as conn:
        conn.executescript(
            """
            create table companies (
                symbol text primary key,
                company_name text,
                bse_code text,
                isin text,
                sector text,
                industry text,
                website text,
                created_at text,
                updated_at text
            );
            insert into companies values (
                'DMART', 'Avenue Supermarts', '', '', 'Retail', '', 'https://example.com',
                '2026-01-01T00:00:00', '2026-01-01T00:00:00'
            );
            """
        )
        conn.commit()

    captured = {}

    def fake_upsert(cur, table, rows, conflict_cols, update_cols=None):
        captured[table] = rows
        return len(rows)

    monkeypatch.setattr(migrate, "upsert", fake_upsert)
    monkeypatch.setattr(migrate, "COMPANY_INTELLIGENCE_DBS", [db])

    migrate.load_company_intelligence(FakeCursor(), dry_run=False)

    assert captured["intelligence.companies"][0]["symbol"] == "DMART"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_company_intelligence_pg_migration.py -q`  
Expected: FAIL because `load_company_intelligence` and `COMPANY_INTELLIGENCE_DBS` do not exist.

- [ ] **Step 3: Add migration section**

In `postgres/migrate.py`, add:

```python
COMPANY_INTELLIGENCE_DBS = [
    DATA / "company_intelligence.db",
    BASE / "company_intelligence.db",
]


def _read_sqlite_table(db_path: Path, table: str) -> pd.DataFrame:
    conn = sqlite3.connect(db_path)
    try:
        names = pd.read_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
            conn,
            params=[table],
        )
        if names.empty:
            return pd.DataFrame()
        return pd.read_sql(f'SELECT * FROM "{table}"', conn)
    finally:
        conn.close()


def load_company_intelligence(cur, dry_run=False):
    print("\n[9/10] INTELLIGENCE - Company intelligence SQLite data")
    for db_path in COMPANY_INTELLIGENCE_DBS:
        if not db_path.exists():
            continue
        companies = _read_sqlite_table(db_path, "companies")
        rows = [
            {
                "symbol": clean_text(r.get("symbol")),
                "company_name": clean_text(r.get("company_name")) or "",
                "bse_code": clean_text(r.get("bse_code")) or "",
                "isin": clean_text(r.get("isin")) or "",
                "sector": clean_text(r.get("sector")) or "",
                "industry": clean_text(r.get("industry")) or "",
                "website": clean_text(r.get("website")) or "",
            }
            for _, r in companies.iterrows()
            if clean_text(r.get("symbol"))
        ]
        if not dry_run and rows:
            upsert(
                cur,
                "intelligence.companies",
                rows,
                ["symbol"],
                ["company_name", "bse_code", "isin", "sector", "industry", "website", "updated_at"],
            )
        log(f"intelligence.companies ({db_path.name}): {len(rows)} rows")
```

Then extend the same function for these tables using the same pattern:

```python
table_specs = [
    ("company_aliases", "intelligence.company_aliases", ["symbol", "alias"], ["alias_type", "source"]),
    ("source_documents", "intelligence.source_documents", ["document_id"], ["symbol", "source_tier", "source_name", "source_url", "document_type", "document_date", "local_path", "content_hash", "fetch_status", "parse_status", "failure_reason"]),
    ("evidence_chunks", "intelligence.evidence_chunks", ["document_id", "symbol", "category", "text"], ["page_number", "table_id", "source_tier", "confidence", "evidence_date"]),
    ("structured_facts", "intelligence.structured_facts", ["symbol", "category", "fact_name", "fact_value", "period"], ["unit", "confidence"]),
    ("sector_entities", "intelligence.sector_entities", ["sector", "entity_type", "entity_name", "symbol"], ["relationship", "confidence"]),
    ("macro_policy_events", "intelligence.macro_policy_events", ["event_type", "event_date", "title"], ["source_url", "summary", "raw_path"]),
    ("impact_assessments", "intelligence.impact_assessments", ["symbol", "impact_area", "direction", "magnitude", "rationale"], ["event_id", "evidence_chunk_ids", "confidence"]),
    ("website_crawl_runs", "intelligence.website_crawl_runs", ["symbol", "base_url", "started_at"], ["completed_at", "status", "pages_seen", "pages_indexed", "documents_found", "failure_reason"]),
    ("website_pages", "intelligence.website_pages", ["symbol", "url_hash"], ["crawl_run_id", "url", "title", "content_hash", "content_type", "status", "raw_path", "text", "page_type"]),
    ("website_links", "intelligence.website_links", ["crawl_run_id", "symbol", "from_url", "to_url"], ["link_text", "link_type", "is_same_domain"]),
    ("website_page_chunks", "intelligence.website_page_chunks", ["page_id", "symbol", "url", "chunk_text"], ["category"]),
]
```

Normalize JSON text columns with `json.loads` fallback to `[]`, booleans with `safe_bool`, dates with `norm_date`, and timestamps by passing SQLite text through as PostgreSQL-compatible text.

- [ ] **Step 4: Add section registration**

Update `SECTIONS`:

```python
"intelligence": load_company_intelligence,
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_company_intelligence_pg_migration.py tests/test_postgres_migrate_audit.py -q`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add postgres/migrate.py tests/test_company_intelligence_pg_migration.py
git commit -m "feat(migrate): load company intelligence into postgres"
```

---

### Task 5: Migrate Agent Adda Historical Data

**Files:**
- Modify: `postgres/migrate.py`
- Test: `tests/test_agent_adda_pg_migration.py`

- [ ] **Step 1: Write migration test**

Create `tests/test_agent_adda_pg_migration.py`:

```python
import sqlite3

from postgres import migrate


class FakeCursor:
    pass


def test_load_agent_adda_historical_reads_daily_prices(tmp_path, monkeypatch):
    db = tmp_path / "market_data.sqlite"
    with sqlite3.connect(db) as conn:
        conn.executescript(
            """
            create table daily_prices (
                symbol text,
                trade_date text,
                open real,
                high real,
                low real,
                close real,
                volume integer,
                source_file text,
                loaded_at text
            );
            insert into daily_prices values (
                'RELIANCE', '2026-01-01', 1, 2, 1, 2, 100, 'fixture.csv', '2026-01-01T00:00:00+00:00'
            );
            """
        )
        conn.commit()

    captured = {}

    def fake_upsert(cur, table, rows, conflict_cols, update_cols=None):
        captured[table] = rows
        return len(rows)

    monkeypatch.setattr(migrate, "upsert", fake_upsert)
    monkeypatch.setattr(migrate, "AGENT_ADDA_SQLITE_DBS", [db])

    migrate.load_agent_adda_historical(FakeCursor(), dry_run=False)

    assert captured["agent_adda.daily_prices"][0]["symbol"] == "RELIANCE"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_agent_adda_pg_migration.py -q`  
Expected: FAIL because `load_agent_adda_historical` does not exist.

- [ ] **Step 3: Add migration section**

In `postgres/migrate.py`, add:

```python
AGENT_ADDA_SQLITE_DBS = [
    Path.home() / ".agent-adda" / "data" / "market_data.sqlite",
]


def load_agent_adda_historical(cur, dry_run=False):
    print("\n[10/10] AGENT_ADDA - Historical SQLite data")
    for db_path in AGENT_ADDA_SQLITE_DBS:
        if not db_path.exists():
            continue
        daily = _read_sqlite_table(db_path, "daily_prices")
        rows = [
            {
                "symbol": clean_text(r.get("symbol")),
                "trade_date": norm_date(r.get("trade_date")),
                "open": safe_float(r.get("open")),
                "high": safe_float(r.get("high")),
                "low": safe_float(r.get("low")),
                "close": safe_float(r.get("close")),
                "volume": safe_int(r.get("volume")),
                "source_file": clean_text(r.get("source_file")) or "",
                "loaded_at": clean_text(r.get("loaded_at")) or datetime.now().isoformat(),
            }
            for _, r in daily.iterrows()
            if clean_text(r.get("symbol")) and norm_date(r.get("trade_date"))
        ]
        if not dry_run and rows:
            upsert(
                cur,
                "agent_adda.daily_prices",
                rows,
                ["symbol", "trade_date", "source_file"],
                ["open", "high", "low", "close", "volume", "loaded_at"],
            )
        log(f"agent_adda.daily_prices ({db_path}): {len(rows)} rows")
```

Also migrate `data_refresh_log` if present:

```python
refresh = _read_sqlite_table(db_path, "data_refresh_log")
refresh_rows = [
    {
        "source": clean_text(r.get("source")) or "historical_csv",
        "source_path": clean_text(r.get("source_path")) or "",
        "rows_loaded": safe_int(r.get("rows_loaded")) or 0,
        "rows_skipped": safe_int(r.get("rows_skipped")) or 0,
        "loaded_at": clean_text(r.get("loaded_at")) or datetime.now().isoformat(),
    }
    for _, r in refresh.iterrows()
]
```

Register:

```python
"agent_adda": load_agent_adda_historical,
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_agent_adda_pg_migration.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add postgres/migrate.py tests/test_agent_adda_pg_migration.py
git commit -m "feat(migrate): load agent adda historical data into postgres"
```

---

### Task 6: Refactor Portfolio Monitor to PostgreSQL

**Files:**
- Modify: `terminal/portfolio_monitor.py`
- Modify: `tests/test_portfolio_monitor.py`

- [ ] **Step 1: Update tests to mock PG snapshot reads**

In `tests/test_portfolio_monitor.py`, replace SQLite fixture setup for `_load_db_snapshot` with a monkeypatch of `terminal.portfolio_monitor.pg_connect`. Add:

```python
def test_load_db_snapshot_reads_postgres(monkeypatch):
    from terminal import portfolio_monitor as pm

    class FakeCursor:
        description = [
            ("symbol",), ("company_name",), ("stage",), ("stage_score",), ("price",),
            ("live_price",), ("technical_score",), ("rsi",), ("trading_signal",),
            ("trend_signal",), ("relative_strength",), ("change_1d_pct",),
            ("change_1w_pct",), ("change_1m_pct",), ("market_cap_cat",), ("sector",),
            ("fundamental_score",), ("enhanced_fund_score",), ("earnings_quality",),
            ("sales_growth",), ("financial_strength",), ("institutional_backing",),
            ("can_slim_score",), ("minervini_score",), ("investment_score",),
            ("fund_details",), ("narrative",), ("stance",), ("supertrend_state",),
            ("supertrend_value",),
        ]

        def execute(self, sql, params=None):
            self.sql = sql

        def fetchone(self):
            return ("2026-05-31",)

        def fetchall(self):
            return [(
                "DMART", "Avenue Supermarts", "STAGE_2", 80, 4000, 4010,
                75, 60, "BUY", "BULLISH", 70, 1, 2, 3, "LARGE_CAP", "Retail",
                70, 72, 68, 65, 66, 67, 69, 71, 74, "{}", "Good", "BULLISH",
                "BULLISH", 3900,
            )]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class FakeConn:
        def cursor(self):
            return FakeCursor()

        def close(self):
            pass

    monkeypatch.setattr(pm, "pg_connect", lambda *_args, **_kwargs: FakeConn())

    records, snap_date = pm._load_db_snapshot()

    assert snap_date == "2026-05-31"
    assert records["DMART"]["stage"] == "STAGE_2"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_portfolio_monitor.py -q`  
Expected: FAIL while `_load_db_snapshot` still opens SQLite.

- [ ] **Step 3: Replace SQLite snapshot loader**

In `terminal/portfolio_monitor.py`:

- Remove `import sqlite3`.
- Remove `DB_PATH`.
- Import `pg_connect`.
- Replace `_load_db_snapshot` with:

```python
def _load_db_snapshot() -> tuple[dict[str, dict], str]:
    try:
        conn = pg_connect()
        with conn.cursor() as cur:
            cur.execute("SELECT MAX(snapshot_date)::text FROM scores.stage_snapshots")
            row = cur.fetchone()
            if not row or not row[0]:
                return {}, "N/A"
            snap_date = row[0]
            cur.execute(
                """
                SELECT symbol, company_name, stage, stage_score, price, live_price,
                       technical_score, rsi, trading_signal, trend_signal, relative_strength,
                       change_1d_pct, change_1w_pct, change_1m_pct, market_cap_cat, sector,
                       fundamental_score, enhanced_fund_score, earnings_quality, sales_growth,
                       financial_strength, institutional_backing, can_slim_score, minervini_score,
                       investment_score, fund_details::text, narrative, stance, supertrend_state,
                       supertrend_value
                FROM scores.stage_snapshots
                WHERE snapshot_date = %s
                """,
                (snap_date,),
            )
            cols = [
                "symbol", "company_name", "stage", "stage_score", "price", "live_price",
                "tech_score", "rsi", "trade_sig", "trend_sig", "rel_str",
                "chg1d", "chg1w", "chg1m", "mktcap", "sector",
                "fund_score", "efund_score", "earn_qual", "sales_gr",
                "fin_str", "inst_back", "canslim", "minervini", "inv_score",
                "fund_det", "narrative", "stance", "supertrend", "st_val",
            ]
            records = {}
            for result in cur.fetchall():
                data = dict(zip(cols, result))
                records[data["symbol"]] = data
            return records, snap_date
    except Exception:
        return {}, "N/A"
    finally:
        try:
            conn.close()
        except Exception:
            pass
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_portfolio_monitor.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add terminal/portfolio_monitor.py tests/test_portfolio_monitor.py
git commit -m "refactor(portfolio): read monitor snapshots from postgres"
```

---

### Task 7: Refactor Terminal Reports and Data Readiness

**Files:**
- Modify: `terminal/reports.py`
- Modify: `terminal/data_readiness.py`
- Modify: `tests/test_terminal_reports.py`
- Modify: `tests/test_data_readiness.py`

- [ ] **Step 1: Write/update tests for PG source behavior**

In `tests/test_terminal_reports.py`, add assertions that sector-stage report code calls `scores.stage_snapshots` instead of SQLite fixture setup. Use monkeypatched connection objects or helper functions.

In `tests/test_data_readiness.py`, replace SQLite fixture requirements with a monkeypatched PG health response:

```python
def test_data_readiness_uses_postgres_health(monkeypatch):
    from terminal import data_readiness

    monkeypatch.setattr(
        data_readiness,
        "get_postgres_health",
        lambda *_args, **_kwargs: {
            "status": "ok",
            "tables": {"scores.stage_snapshots": {"rows": 10}},
        },
    )

    status = data_readiness.get_data_readiness_status()

    assert "postgres" in status.source.lower()
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_terminal_reports.py tests/test_data_readiness.py -q`  
Expected: FAIL where modules still require SQLite fixtures or labels.

- [ ] **Step 3: Refactor report snapshot connection**

In `terminal/reports.py`, replace `_connect_stage_db` and sector report SQLite queries around the `sector_rotation_tracker.db` usage with PostgreSQL queries against:

```sql
SELECT *
FROM scores.stage_snapshots
WHERE snapshot_date = (SELECT max(snapshot_date) FROM scores.stage_snapshots)
```

For stage changes:

```sql
SELECT *
FROM scores.stage_changes
WHERE change_date = (SELECT max(change_date) FROM scores.stage_changes)
```

- [ ] **Step 4: Refactor data readiness**

In `terminal/data_readiness.py`:

- Remove `import sqlite3`.
- Remove `_legacy_sqlite_fallbacks_enabled`.
- Remove SQLite table/column inspection.
- Use `terminal.postgres_tools.get_postgres_health` and direct count queries for `scores.stage_snapshots`, `scores.stage_changes`, `market.equity_eod`, and `derivatives.fno_eod`.
- Return blocker messages that mention missing PostgreSQL coverage rather than SQLite unavailability.

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_terminal_reports.py tests/test_data_readiness.py -q`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add terminal/reports.py terminal/data_readiness.py tests/test_terminal_reports.py tests/test_data_readiness.py
git commit -m "refactor(reports): remove sqlite stage data reads"
```

---

### Task 8: Remove Runtime SQLite F&O Fallbacks

**Files:**
- Modify: `terminal/fno_data.py`
- Modify: `terminal/tools.py`
- Modify: `tests/test_fno_live_stock_futures.py`
- Modify: `tests/test_postgres_loader.py`

- [ ] **Step 1: Update tests for PG-only F&O behavior**

Add a test in `tests/test_fno_live_stock_futures.py` that sets `AGENT_ADDA_ENABLE_SQLITE_FALLBACKS=1` and confirms F&O read functions still prefer PostgreSQL and do not open `_db_conn`.

```python
def test_fno_reads_do_not_open_sqlite_when_pg_available(monkeypatch):
    from terminal import fno_data

    monkeypatch.setenv("AGENT_ADDA_ENABLE_SQLITE_FALLBACKS", "1")
    monkeypatch.setattr(fno_data, "_db_conn", lambda: (_ for _ in ()).throw(AssertionError("sqlite opened")))
    monkeypatch.setattr(fno_data, "_load_pg_fno", lambda *args, **kwargs: [])

    result = fno_data.get_available_fno_dates()

    assert result is not None
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_fno_live_stock_futures.py -q`  
Expected: FAIL if SQLite fallback still opens in tested path.

- [ ] **Step 3: Remove runtime SQLite fallback code**

In `terminal/fno_data.py`:

- Remove `import sqlite3`.
- Remove `FNO_DB`, `_db_conn`, `_ensure_schema`, and SQLite read fallback blocks.
- Keep migration/source comments only in `postgres/migrate.py`.
- Make `load_and_store_latest()` write to `derivatives.fno_eod` only.
- Return `"sqlite_rows_stored": 0` only if needed for backward-compatible output; otherwise remove the field and update tests.

In `terminal/tools.py`:

- Remove F&O SQLite source labels.
- Update help/tool output to report `postgres.derivatives.fno_eod`.

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/test_fno_live_stock_futures.py tests/test_postgres_loader.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add terminal/fno_data.py terminal/tools.py tests/test_fno_live_stock_futures.py tests/test_postgres_loader.py
git commit -m "refactor(fno): remove sqlite runtime fallbacks"
```

---

### Task 9: Refactor Company Intelligence Runtime to PostgreSQL

**Files:**
- Modify: `company_intelligence_db.py`
- Modify: `company_intelligence_extract.py`
- Modify: `company_intelligence_search.py`
- Modify: `company_intelligence_promote.py`
- Modify: `company_intelligence_policy.py`
- Modify: `company_intelligence.py`
- Modify: related tests under `tests/test_company_intelligence*.py`, `tests/test_company_website_indexer.py`, `tests/test_company_xray_dmart_regression.py`

- [ ] **Step 1: Add PG-backed storage tests**

Convert `tests/test_company_intelligence_db.py` to assert SQL and behavior through a fake PG connection. Start with these cases:

```python
def test_upsert_company_uses_intelligence_schema(monkeypatch):
    import company_intelligence_db as db

    statements = []

    class FakeCursor:
        def execute(self, sql, params=None):
            statements.append(sql)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class FakeConn:
        def cursor(self):
            return FakeCursor()

        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(db, "pg_connect", lambda *_args, **_kwargs: FakeConn())

    db.upsert_company("DMART", "Avenue Supermarts", sector="Retail")

    assert any("intelligence.companies" in sql for sql in statements)
```

- [ ] **Step 2: Run company intelligence tests to verify failure**

Run: `pytest tests/test_company_intelligence_db.py tests/test_company_intelligence_search.py tests/test_company_intelligence_promote.py tests/test_company_intelligence_extract.py tests/test_company_intelligence_policy.py -q`  
Expected: FAIL because APIs still expect `sqlite3.Connection`.

- [ ] **Step 3: Refactor storage API**

In `company_intelligence_db.py`:

- Remove `sqlite3`.
- Import `pg_connect`.
- Change `init_company_intelligence_db(db_path)` to `ensure_company_intelligence_schema(dsn: str | None = None)` that executes `postgres/schema.sql` or a dedicated schema subset.
- Change function signatures from `conn: sqlite3.Connection` to DSN-optional functions that open PG connections internally, or accept a psycopg2 connection.
- Use `%s` placeholders and PostgreSQL `ON CONFLICT`.
- Replace SQLite `AUTOINCREMENT` assumptions with PostgreSQL `RETURNING` where callers need IDs.

Example replacement:

```python
def upsert_company(
    symbol: str,
    company_name: str = "",
    sector: str = "",
    industry: str = "",
    website: str = "",
    *,
    conn=None,
) -> None:
    normalized = symbol.strip().upper()
    own_conn = conn is None
    conn = conn or pg_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO intelligence.companies (symbol, company_name, sector, industry, website)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT(symbol) DO UPDATE SET
                    company_name = EXCLUDED.company_name,
                    sector = EXCLUDED.sector,
                    industry = EXCLUDED.industry,
                    website = EXCLUDED.website,
                    updated_at = now()
                """,
                (normalized, company_name, sector, industry, website),
            )
        if own_conn:
            conn.commit()
    except Exception:
        if own_conn:
            conn.rollback()
        raise
    finally:
        if own_conn:
            conn.close()
```

- [ ] **Step 4: Replace FTS queries**

In `company_intelligence_search.py`, replace `website_search_fts MATCH ?` with:

```sql
SELECT symbol, url, category, chunk_text,
       ts_rank(to_tsvector('english', coalesce(category, '') || ' ' || coalesce(chunk_text, '')), plainto_tsquery('english', %s)) AS rank
FROM intelligence.website_page_chunks
WHERE symbol = %s
  AND to_tsvector('english', coalesce(category, '') || ' ' || coalesce(chunk_text, '')) @@ plainto_tsquery('english', %s)
ORDER BY rank DESC, created_at DESC
LIMIT %s
```

- [ ] **Step 5: Update callers**

Update extraction, promotion, policy, and top-level `company_intelligence.py` to use the new PG API. Remove direct `sqlite3.connect` calls.

- [ ] **Step 6: Run company intelligence tests**

Run: `pytest tests/test_company_intelligence_db.py tests/test_company_intelligence_search.py tests/test_company_intelligence_promote.py tests/test_company_intelligence_extract.py tests/test_company_intelligence_policy.py tests/test_company_website_indexer.py tests/test_company_xray_dmart_regression.py -q`  
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add company_intelligence_db.py company_intelligence_extract.py company_intelligence_search.py company_intelligence_promote.py company_intelligence_policy.py company_intelligence.py tests/test_company_intelligence_db.py tests/test_company_intelligence_search.py tests/test_company_intelligence_promote.py tests/test_company_intelligence_extract.py tests/test_company_intelligence_policy.py tests/test_company_website_indexer.py tests/test_company_xray_dmart_regression.py
git commit -m "refactor(intelligence): move company storage to postgres"
```

---

### Task 10: Refactor Agent Adda Historical Store and Doctor

**Files:**
- Modify: `agent_adda/config/settings.py`
- Modify: `agent_adda/data/historical.py`
- Modify: `agent_adda/doctor.py`
- Modify: `tests/test_agent_adda_historical.py`

- [ ] **Step 1: Update config tests**

In `tests/test_agent_adda_historical.py`, replace assertions about `database_path` with `pg_dsn` where needed:

```python
def test_default_config_contains_pg_dsn():
    from agent_adda.config.settings import default_config

    config = default_config()

    assert config.pg_dsn == "dbname=nse_market user=nse_admin host=/tmp"
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_agent_adda_historical.py -q`  
Expected: FAIL because `pg_dsn` does not exist and historical loader writes SQLite.

- [ ] **Step 3: Change config model**

In `agent_adda/config/settings.py`:

- Add `pg_dsn: str` to `AppConfig`.
- Keep `database_path` only as a deprecated field if existing config compatibility requires it; do not use it for runtime writes.
- In `default_config()`, set `pg_dsn` with env fallback:

```python
pg_dsn=os.environ.get("AGENT_ADDA_PG_DSN") or os.environ.get("PG_DSN") or "dbname=nse_market user=nse_admin host=/tmp"
```

- Persist `pg_dsn` under a new `[database]` config section.

- [ ] **Step 4: Refactor historical loader**

In `agent_adda/data/historical.py`:

- Remove `sqlite3`.
- Replace `_create_schema(conn)` with `_ensure_schema(conn)` that creates `agent_adda.daily_prices` and `agent_adda.data_refresh_log`.
- Replace `insert or replace` with PostgreSQL:

```sql
INSERT INTO agent_adda.daily_prices (
    symbol, trade_date, open, high, low, close, volume, source_file, loaded_at
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (symbol, trade_date, source_file) DO UPDATE SET
    open = EXCLUDED.open,
    high = EXCLUDED.high,
    low = EXCLUDED.low,
    close = EXCLUDED.close,
    volume = EXCLUDED.volume,
    loaded_at = EXCLUDED.loaded_at
```

Change `BootstrapResult.database_path` to `dsn` or add a new field while preserving compatibility:

```python
@dataclass(frozen=True)
class BootstrapResult:
    dsn: str
    files_scanned: int
    rows_loaded: int
    rows_skipped: int
```

- [ ] **Step 5: Refactor doctor**

In `agent_adda/doctor.py`, replace SQLite open/check logic with a PG connection and:

```sql
SELECT COUNT(*) FROM agent_adda.daily_prices
```

Report missing schema as a repairable PostgreSQL issue.

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_agent_adda_historical.py -q`  
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add agent_adda/config/settings.py agent_adda/data/historical.py agent_adda/doctor.py tests/test_agent_adda_historical.py
git commit -m "refactor(agent-adda): store historical bootstrap data in postgres"
```

---

### Task 11: Remove Remaining Production SQLite References

**Files:**
- Modify: active source files reported by `rg`
- Test: `tests/test_no_runtime_sqlite.py`

- [ ] **Step 1: Add runtime SQLite guard test**

Create `tests/test_no_runtime_sqlite.py`:

```python
from pathlib import Path


ALLOWED = {
    "postgres/migrate.py",
}

ALLOWED_PREFIXES = (
    "archive/",
    "organized/",
    "tests/",
    "docs/",
    "reports/",
)


def test_no_runtime_sqlite_imports_remain():
    offenders = []
    for path in Path(".").rglob("*.py"):
        rel = path.as_posix()
        if rel in ALLOWED or rel.startswith(ALLOWED_PREFIXES):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        if "import sqlite3" in text or "sqlite3.connect" in text:
            offenders.append(rel)

    assert offenders == []
```

- [ ] **Step 2: Run guard test**

Run: `pytest tests/test_no_runtime_sqlite.py -q`  
Expected: FAIL with the remaining active SQLite files.

- [ ] **Step 3: Remove or quarantine remaining references**

For each offender:

- If it is an active runtime module, refactor to PostgreSQL using `terminal.db`.
- If it is an import-only migration utility, move the SQLite code under `postgres/migrate.py` or add the file to the explicit allowed list with a comment in the test.
- If it is obsolete, archive it or update it to call PostgreSQL-backed APIs.

- [ ] **Step 4: Update source labels**

Run:

```bash
rg -n "SQLite|sqlite|sector_rotation_tracker\\.db|fno_eod\\.db|market_data\\.sqlite" terminal company_intelligence*.py agent_adda portfolio postgres
```

Update user-facing text that describes runtime sources as SQLite. Do not edit archived reports or generated historical benchmark JSON.

- [ ] **Step 5: Run guard test**

Run: `pytest tests/test_no_runtime_sqlite.py -q`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/test_no_runtime_sqlite.py terminal company_intelligence*.py agent_adda portfolio postgres
git commit -m "chore(sqlite): remove production sqlite runtime references"
```

---

### Task 12: Run Migration and Verification

**Files:**
- Modify only if verification exposes bugs.
- Test: existing affected suites.

- [ ] **Step 1: Apply PostgreSQL schema**

Run:

```bash
psql "dbname=nse_market user=nse_admin host=/tmp" -v ON_ERROR_STOP=1 -f postgres/schema.sql
```

Expected: schema applies without error.

- [ ] **Step 2: Run dry-run migration audit**

Run:

```bash
python3 postgres/migrate.py --audit --dry-run
```

Expected: prints table counts for SQLite sources and parses each section without writes.

- [ ] **Step 3: Run live migration**

Run:

```bash
python3 postgres/migrate.py --audit
```

Expected: all sections commit, materialized views refresh, and parity output has no unexplained mismatches.

- [ ] **Step 4: Run focused test suites**

Run:

```bash
pytest tests/test_terminal_db.py tests/test_postgres_schema_sqlite_cutover.py tests/test_postgres_migrate_audit.py tests/test_company_intelligence_pg_migration.py tests/test_agent_adda_pg_migration.py tests/test_portfolio_monitor.py tests/test_terminal_reports.py tests/test_data_readiness.py tests/test_fno_live_stock_futures.py tests/test_agent_adda_historical.py tests/test_no_runtime_sqlite.py -q
```

Expected: PASS.

- [ ] **Step 5: Run runtime smoke checks**

Run:

```bash
python3 - <<'PY'
from terminal.portfolio_monitor import run_eod_report
print(run_eod_report())
PY
```

Expected: report generation succeeds and writes `reports/latest/portfolio_analysis.html`.

Run:

```bash
python3 - <<'PY'
from terminal.fno_data import get_available_fno_dates
print(get_available_fno_dates())
PY
```

Expected: returns dates from `derivatives.fno_eod`.

- [ ] **Step 6: Final SQLite scan**

Run:

```bash
rg -n "sqlite3|sqlite|\\.db|market_data\\.sqlite" terminal company_intelligence*.py agent_adda portfolio postgres tests
```

Expected: remaining hits are `postgres/migrate.py`, migration fixture tests, documentation, or explicit comments about retired sources.

- [ ] **Step 7: Commit verification fixes**

If verification required fixes:

```bash
git add <fixed-files>
git commit -m "fix(sqlite-cutover): resolve postgres verification issues"
```

If no fixes were required, do not create an empty commit.
