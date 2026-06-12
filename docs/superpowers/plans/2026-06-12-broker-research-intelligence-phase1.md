# Broker Research Intelligence Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first PostgreSQL-backed broker research intelligence slice: source registry, single-symbol public report discovery, and terminal commands.

**Architecture:** Extend the existing `company_intel` PostgreSQL schema with broker-specific tables, then keep broker source definitions, discovery parsing, and command rendering in a new focused `broker_research` package. Tests use small local HTML fixtures and fake database connections, so no live broker network calls are required for correctness.

**Tech Stack:** Python 3, PostgreSQL, psycopg2-compatible DB API, BeautifulSoup optional fallback to stdlib HTML parsing, pytest, existing Agent Adda `CommandRegistry`.

---

## Scope

This plan implements Phase 1 from `docs/superpowers/specs/2026-06-12-broker-research-intelligence-design.md`.

Included:

- PostgreSQL broker source and report metadata tables under `company_intel`
- Seeded public/direct broker source registry for ICICI Direct, HDFC Securities/HSIE, Axis Direct, Sharekhan, and Trendlyne discovery
- Fixture-backed link extraction from broker index pages
- Symbol and company-alias matching against discovered PDF links
- Storage helpers for broker index runs and broker reports
- `/broker-sources` terminal command
- `/broker-index SYMBOL` terminal command that fetches public index pages at runtime and accepts injected HTML in tests

Deferred to later phases:

- Downloading broker PDFs
- PDF text/page/table parsing
- LLM fact extraction
- Consensus comparison
- `/broker-fetch`, `/broker-research`, `/deep-research`, and `/report broker`

## File Structure

- Modify `postgres/migrations/20260612_company_intel.sql`
  - Add broker research tables and indexes under `company_intel`.
- Modify `company_intelligence_pg.py`
  - Add broker table names to `REQUIRED_TABLES`.
- Create `broker_research/__init__.py`
  - Export the public Phase 1 API.
- Create `broker_research/sources.py`
  - Define source registry rows and seed helpers.
- Create `broker_research/discovery.py`
  - Extract PDF links from HTML and score links against symbol/company aliases.
- Create `broker_research/storage.py`
  - Insert broker sources, record index runs, and upsert discovered report metadata.
- Create `broker_research/commands.py`
  - Parse and render `/broker-sources` and `/broker-index` output.
- Modify `nse_agent.py`
  - Add slash catalog entries and register command dispatch.
- Modify `terminal/help.py`
  - Show broker research commands in help.
- Create `tests/fixtures/broker_research/icici_co_reports.html`
  - Minimal ICICI-style fixture with BEL report links.
- Create `tests/fixtures/broker_research/hdfc_reports.html`
  - Minimal HDFC/HSIE-style fixture with timestamped PDF links.
- Create `tests/fixtures/broker_research/axis_fundamental.html`
  - Minimal Axis-style fixture with `downloadReport` and image PDF links.
- Create `tests/test_broker_research_schema.py`
  - Schema/table/index contract tests.
- Create `tests/test_broker_research_sources.py`
  - Seed registry tests.
- Create `tests/test_broker_research_discovery.py`
  - Fixture extraction and match scoring tests.
- Create `tests/test_broker_research_storage.py`
  - DB helper tests with fake connection.
- Create `tests/test_broker_research_commands.py`
  - Command parsing/rendering tests.
- Create `tests/test_broker_research_command_registry.py`
  - Command registry snapshot test.

## Database Model

Add these tables exactly under `company_intel`:

```sql
CREATE TABLE IF NOT EXISTS company_intel.broker_sources (
    source_id BIGSERIAL PRIMARY KEY,
    broker_code TEXT NOT NULL,
    broker_name TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    source_url TEXT NOT NULL,
    access_mode TEXT NOT NULL,
    url_pattern TEXT NOT NULL DEFAULT '',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    notes TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (broker_code, source_kind, source_url)
);

CREATE TABLE IF NOT EXISTS company_intel.broker_index_runs (
    index_run_id BIGSERIAL PRIMARY KEY,
    source_id BIGINT REFERENCES company_intel.broker_sources(source_id) ON DELETE SET NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'running',
    http_status INTEGER,
    reports_found INTEGER NOT NULL DEFAULT 0,
    reports_new INTEGER NOT NULL DEFAULT 0,
    failure_reason TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS company_intel.broker_reports (
    broker_report_id BIGSERIAL PRIMARY KEY,
    broker_code TEXT NOT NULL,
    symbol TEXT NOT NULL DEFAULT '',
    company_name TEXT NOT NULL DEFAULT '',
    report_title TEXT NOT NULL DEFAULT '',
    report_type TEXT NOT NULL DEFAULT 'unknown',
    report_date DATE,
    source_url TEXT NOT NULL DEFAULT '',
    pdf_url TEXT NOT NULL,
    pdf_hash TEXT NOT NULL DEFAULT '',
    local_path TEXT NOT NULL DEFAULT '',
    fetch_status TEXT NOT NULL DEFAULT 'not_fetched',
    parse_status TEXT NOT NULL DEFAULT 'not_parsed',
    discovered_via TEXT NOT NULL DEFAULT '',
    match_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (broker_code, pdf_url)
);

CREATE TABLE IF NOT EXISTS company_intel.broker_report_pages (
    page_id BIGSERIAL PRIMARY KEY,
    broker_report_id BIGINT NOT NULL REFERENCES company_intel.broker_reports(broker_report_id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    text TEXT NOT NULL,
    char_count INTEGER NOT NULL DEFAULT 0,
    search_vector TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', coalesce(text, ''))) STORED,
    UNIQUE (broker_report_id, page_number)
);

CREATE TABLE IF NOT EXISTS company_intel.broker_report_tables (
    table_id BIGSERIAL PRIMARY KEY,
    broker_report_id BIGINT NOT NULL REFERENCES company_intel.broker_reports(broker_report_id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    table_index INTEGER NOT NULL,
    table_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    caption TEXT NOT NULL DEFAULT '',
    UNIQUE (broker_report_id, page_number, table_index)
);

CREATE TABLE IF NOT EXISTS company_intel.broker_research_facts (
    fact_id BIGSERIAL PRIMARY KEY,
    broker_report_id BIGINT NOT NULL REFERENCES company_intel.broker_reports(broker_report_id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    fact_type TEXT NOT NULL,
    fact_name TEXT NOT NULL,
    fact_value TEXT NOT NULL,
    unit TEXT NOT NULL DEFAULT '',
    period TEXT NOT NULL DEFAULT '',
    page_number INTEGER,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    extractor TEXT NOT NULL DEFAULT 'deterministic',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS company_intel.broker_research_runs (
    research_run_id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    objective TEXT NOT NULL DEFAULT '',
    broker_filter TEXT NOT NULL DEFAULT '',
    as_of TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status TEXT NOT NULL DEFAULT 'running',
    report_markdown_path TEXT NOT NULL DEFAULT '',
    report_html_path TEXT NOT NULL DEFAULT '',
    report_pdf_path TEXT NOT NULL DEFAULT '',
    coverage_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_company_intel_broker_sources_active
    ON company_intel.broker_sources (is_active, access_mode, broker_code);
CREATE INDEX IF NOT EXISTS idx_company_intel_broker_reports_symbol
    ON company_intel.broker_reports (symbol, broker_code, report_date DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_company_intel_broker_reports_pdf_hash
    ON company_intel.broker_reports (pdf_hash) WHERE pdf_hash <> '';
CREATE INDEX IF NOT EXISTS idx_company_intel_broker_pages_search
    ON company_intel.broker_report_pages USING GIN (search_vector);
CREATE INDEX IF NOT EXISTS idx_company_intel_broker_facts_symbol
    ON company_intel.broker_research_facts (symbol, fact_type, broker_report_id);
```

## Task 1: Schema Contract

**Files:**
- Modify: `postgres/migrations/20260612_company_intel.sql`
- Modify: `company_intelligence_pg.py`
- Create: `tests/test_broker_research_schema.py`

- [ ] **Step 1: Write the failing schema tests**

Create `tests/test_broker_research_schema.py`:

```python
from company_intelligence_pg import REQUIRED_TABLES, schema_sql


BROKER_TABLES = [
    "broker_sources",
    "broker_index_runs",
    "broker_reports",
    "broker_report_pages",
    "broker_report_tables",
    "broker_research_facts",
    "broker_research_runs",
]


def test_company_intel_schema_contains_broker_research_tables():
    sql = schema_sql()

    for table in BROKER_TABLES:
        assert f"CREATE TABLE IF NOT EXISTS company_intel.{table}" in sql
        assert table in REQUIRED_TABLES


def test_company_intel_schema_contains_broker_research_indexes():
    sql = schema_sql()

    assert "idx_company_intel_broker_sources_active" in sql
    assert "idx_company_intel_broker_reports_symbol" in sql
    assert "idx_company_intel_broker_pages_search" in sql
    assert "idx_company_intel_broker_facts_symbol" in sql
```

- [ ] **Step 2: Run the schema tests and confirm failure**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_broker_research_schema.py
```

Expected:

```text
FAILED tests/test_broker_research_schema.py::test_company_intel_schema_contains_broker_research_tables
```

- [ ] **Step 3: Extend the migration**

Append the SQL from the "Database Model" section to `postgres/migrations/20260612_company_intel.sql` after the existing website chunk index.

- [ ] **Step 4: Extend `REQUIRED_TABLES`**

In `company_intelligence_pg.py`, append these strings to `REQUIRED_TABLES`:

```python
    "broker_sources",
    "broker_index_runs",
    "broker_reports",
    "broker_report_pages",
    "broker_report_tables",
    "broker_research_facts",
    "broker_research_runs",
```

- [ ] **Step 5: Run the schema tests and existing PG tests**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_broker_research_schema.py tests/test_company_intelligence_pg.py
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit**

Run:

```bash
git add postgres/migrations/20260612_company_intel.sql company_intelligence_pg.py tests/test_broker_research_schema.py
git commit -m "feat: add broker research postgres schema"
```

## Task 2: Source Registry Seed

**Files:**
- Create: `broker_research/__init__.py`
- Create: `broker_research/sources.py`
- Create: `tests/test_broker_research_sources.py`

- [ ] **Step 1: Write failing source tests**

Create `tests/test_broker_research_sources.py`:

```python
from broker_research.sources import BROKER_SOURCES, BrokerSource, active_public_sources


def test_seeded_broker_sources_cover_user_supplied_public_sources():
    broker_codes = {source.broker_code for source in BROKER_SOURCES}

    assert {"icici", "hdfc_hsie", "axis", "sharekhan", "trendlyne"} <= broker_codes


def test_source_rows_are_stable_and_insertable():
    source = BrokerSource(
        broker_code="test",
        broker_name="Test Broker",
        source_kind="index_page",
        source_url="https://example.com/research",
        access_mode="public",
        url_pattern="",
        notes="fixture",
    )

    assert source.as_insert_params() == (
        "test",
        "Test Broker",
        "index_page",
        "https://example.com/research",
        "public",
        "",
        True,
        "fixture",
    )


def test_active_public_sources_excludes_login_required_rows():
    sources = active_public_sources()

    assert all(source.is_active for source in sources)
    assert all(source.access_mode in {"public", "partial"} for source in sources)
    assert not any(source.access_mode == "login_required" for source in sources)
```

- [ ] **Step 2: Run source tests and confirm import failure**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_broker_research_sources.py
```

Expected:

```text
ModuleNotFoundError: No module named 'broker_research'
```

- [ ] **Step 3: Create `broker_research/__init__.py`**

Create `broker_research/__init__.py`:

```python
"""Broker research intelligence package."""

from .sources import BROKER_SOURCES, BrokerSource, active_public_sources

__all__ = ["BROKER_SOURCES", "BrokerSource", "active_public_sources"]
```

- [ ] **Step 4: Create `broker_research/sources.py`**

Create `broker_research/sources.py`:

```python
"""Broker research source registry definitions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BrokerSource:
    broker_code: str
    broker_name: str
    source_kind: str
    source_url: str
    access_mode: str
    url_pattern: str = ""
    is_active: bool = True
    notes: str = ""

    def as_insert_params(self) -> tuple[str, str, str, str, str, str, bool, str]:
        return (
            self.broker_code,
            self.broker_name,
            self.source_kind,
            self.source_url,
            self.access_mode,
            self.url_pattern,
            self.is_active,
            self.notes,
        )


BROKER_SOURCES: tuple[BrokerSource, ...] = (
    BrokerSource(
        broker_code="icici",
        broker_name="ICICI Direct",
        source_kind="index_page",
        source_url="https://www.icicidirect.com/mailcontent/co_reports.html",
        access_mode="public",
        url_pattern="https://www.icicidirect.com/mailcontent/idirect_{ticker}_{type}_{period}.pdf",
        notes="Public master coverage index plus direct PDFs.",
    ),
    BrokerSource(
        broker_code="hdfc_hsie",
        broker_name="HDFC Securities / HSIE",
        source_kind="index_page",
        source_url="https://www.hdfcsec.com/research/equity/stock-research-institutional-reports",
        access_mode="public",
        url_pattern="https://www.hdfcsec.com/hsl.docs/{report_title}-HSIE-{timestamp}.pdf",
        notes="Public institutional report index with timestamped PDF links.",
    ),
    BrokerSource(
        broker_code="axis",
        broker_name="Axis Direct",
        source_kind="index_page",
        source_url="https://simplehai.axisdirect.in/app/index.php/insights/reports/fundamental",
        access_mode="public",
        url_pattern="https://simplehai.axisdirect.in/app/index.php/insights/reports/downloadReport/file/{report_title}/type/fundamental",
        notes="Public fundamental research index.",
    ),
    BrokerSource(
        broker_code="axis",
        broker_name="Axis Direct",
        source_kind="index_page",
        source_url="https://simplehai.axisdirect.in/research/research-reports/trading-reports",
        access_mode="public",
        url_pattern="",
        notes="Public technical and trading reports index.",
    ),
    BrokerSource(
        broker_code="sharekhan",
        broker_name="Mirae Asset Sharekhan",
        source_kind="fixed_pdf",
        source_url="https://www.sharekhan.com/MediaGalary/Newsletter/Investoreye.pdf",
        access_mode="public",
        url_pattern="",
        notes="Latest weekly multi-stock Investor's Eye newsletter.",
    ),
    BrokerSource(
        broker_code="sharekhan",
        broker_name="Mirae Asset Sharekhan",
        source_kind="fixed_pdf",
        source_url="https://www.sharekhan.com/MediaGalary/Newsletter/Eagleeye_e.pdf",
        access_mode="public",
        url_pattern="",
        notes="Latest daily technical Eagle Eye newsletter.",
    ),
    BrokerSource(
        broker_code="sharekhan",
        broker_name="Mirae Asset Sharekhan",
        source_kind="fixed_pdf",
        source_url="https://www.sharekhan.com/MediaGalary/Newsletter/DerivativeEye.pdf",
        access_mode="public",
        url_pattern="",
        notes="Latest derivatives newsletter.",
    ),
    BrokerSource(
        broker_code="trendlyne",
        broker_name="Trendlyne Research Reports",
        source_kind="trendlyne_broker",
        source_url="https://trendlyne.com/research-reports/",
        access_mode="partial",
        url_pattern="",
        notes="Discovery metadata only; prefer direct broker PDF evidence when available.",
    ),
)


def active_public_sources() -> tuple[BrokerSource, ...]:
    return tuple(
        source
        for source in BROKER_SOURCES
        if source.is_active and source.access_mode in {"public", "partial"}
    )
```

- [ ] **Step 5: Run source tests**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_broker_research_sources.py
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit**

Run:

```bash
git add broker_research/__init__.py broker_research/sources.py tests/test_broker_research_sources.py
git commit -m "feat: seed broker research sources"
```

## Task 3: Discovery Parser

**Files:**
- Create: `broker_research/discovery.py`
- Create: `tests/fixtures/broker_research/icici_co_reports.html`
- Create: `tests/fixtures/broker_research/hdfc_reports.html`
- Create: `tests/fixtures/broker_research/axis_fundamental.html`
- Create: `tests/test_broker_research_discovery.py`

- [ ] **Step 1: Create fixture files**

Create `tests/fixtures/broker_research/icici_co_reports.html`:

```html
<html><body>
  <a href="idirect_bel_shubhnivesh_apr26.pdf">BEL Shubh Nivesh Apr 2026</a>
  <a href="https://www.icicidirect.com/mailcontent/idirect_bharatelectronics_q3fy26.pdf">Bharat Electronics Q3FY26 Result Update</a>
  <a href="idirect_infosys_q3fy26.pdf">Infosys Q3FY26 Result Update</a>
</body></html>
```

Create `tests/fixtures/broker_research/hdfc_reports.html`:

```html
<html><body>
  <a href="/hsl.docs//Bharat Electronics - Q4FY26 - HSIE-202605200629467330553.pdf">Bharat Electronics Q4FY26</a>
  <a href="/hsl.docs//Bharat barometer - Apr26 - HSIE-202605151451211787178.pdf">Bharat barometer Apr26</a>
</body></html>
```

Create `tests/fixtures/broker_research/axis_fundamental.html`:

```html
<html><body>
  <a href="/app/index.php/insights/reports/downloadReport/file/Bharat+Electronics_Q4FY26_20-05-2026.pdf/type/fundamental">BEL result update</a>
  <a href="https://simplehai.axisdirect.in/images/ResearchPDF/2023/Cipla-ResultUpdate--27012026.pdf">Cipla Q3FY26</a>
</body></html>
```

- [ ] **Step 2: Write failing discovery tests**

Create `tests/test_broker_research_discovery.py`:

```python
from pathlib import Path

from broker_research.discovery import DiscoveredReportLink, discover_report_links, score_report_match


FIXTURES = Path(__file__).parent / "fixtures" / "broker_research"


def test_icici_fixture_extracts_absolute_pdf_links():
    html = (FIXTURES / "icici_co_reports.html").read_text(encoding="utf-8")

    links = discover_report_links(
        html,
        base_url="https://www.icicidirect.com/mailcontent/co_reports.html",
        broker_code="icici",
    )

    urls = [link.pdf_url for link in links]
    assert "https://www.icicidirect.com/mailcontent/idirect_bel_shubhnivesh_apr26.pdf" in urls
    assert "https://www.icicidirect.com/mailcontent/idirect_bharatelectronics_q3fy26.pdf" in urls


def test_hdfc_fixture_extracts_timestamped_pdf_links():
    html = (FIXTURES / "hdfc_reports.html").read_text(encoding="utf-8")

    links = discover_report_links(
        html,
        base_url="https://www.hdfcsec.com/research/equity/stock-research-institutional-reports",
        broker_code="hdfc_hsie",
    )

    assert any(link.pdf_url.startswith("https://www.hdfcsec.com/hsl.docs/") for link in links)
    assert any("Bharat Electronics" in link.title for link in links)


def test_axis_fixture_extracts_download_report_and_image_pdf_links():
    html = (FIXTURES / "axis_fundamental.html").read_text(encoding="utf-8")

    links = discover_report_links(
        html,
        base_url="https://simplehai.axisdirect.in/app/index.php/insights/reports/fundamental",
        broker_code="axis",
    )

    urls = [link.pdf_url for link in links]
    assert any("/downloadReport/file/Bharat+Electronics_Q4FY26_20-05-2026.pdf/type/fundamental" in url for url in urls)
    assert any(url.endswith("Cipla-ResultUpdate--27012026.pdf") for url in urls)


def test_score_report_match_prefers_symbol_and_alias_hits():
    bel = DiscoveredReportLink(
        broker_code="icici",
        title="Bharat Electronics Q3FY26 Result Update",
        pdf_url="https://www.icicidirect.com/mailcontent/idirect_bharatelectronics_q3fy26.pdf",
        source_url="https://www.icicidirect.com/mailcontent/co_reports.html",
    )
    barometer = DiscoveredReportLink(
        broker_code="hdfc_hsie",
        title="Bharat barometer Apr26",
        pdf_url="https://www.hdfcsec.com/hsl.docs/Bharat-barometer-Apr26-HSIE.pdf",
        source_url="https://www.hdfcsec.com/research/equity/stock-research-institutional-reports",
    )

    assert score_report_match(bel, symbol="BEL", aliases=["Bharat Electronics"]) >= 0.8
    assert score_report_match(barometer, symbol="BEL", aliases=["Bharat Electronics"]) < 0.5
```

- [ ] **Step 3: Run discovery tests and confirm failure**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_broker_research_discovery.py
```

Expected:

```text
ModuleNotFoundError: No module named 'broker_research.discovery'
```

- [ ] **Step 4: Create `broker_research/discovery.py`**

Create `broker_research/discovery.py`:

```python
"""HTML discovery helpers for public broker research links."""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin


@dataclass(frozen=True)
class DiscoveredReportLink:
    broker_code: str
    title: str
    pdf_url: str
    source_url: str


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._href: str | None = None
        self._text: list[str] = []
        self.anchors: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        values = dict(attrs)
        self._href = values.get("href") or ""
        self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._href is None:
            return
        title = " ".join(" ".join(self._text).split())
        self.anchors.append((self._href, title))
        self._href = None
        self._text = []


def _looks_like_pdf_link(href: str) -> bool:
    clean = href.lower()
    return ".pdf" in clean or "/downloadreport/file/" in clean


def discover_report_links(html: str, *, base_url: str, broker_code: str) -> list[DiscoveredReportLink]:
    parser = _AnchorParser()
    parser.feed(html or "")
    links: list[DiscoveredReportLink] = []
    seen: set[str] = set()
    for href, title in parser.anchors:
        if not _looks_like_pdf_link(href):
            continue
        pdf_url = urljoin(base_url, href)
        if pdf_url in seen:
            continue
        seen.add(pdf_url)
        links.append(
            DiscoveredReportLink(
                broker_code=broker_code,
                title=title or pdf_url.rsplit("/", 1)[-1],
                pdf_url=pdf_url,
                source_url=base_url,
            )
        )
    return links


def _norm(text: str) -> str:
    return " ".join((text or "").replace("_", " ").replace("-", " ").replace("+", " ").lower().split())


def score_report_match(link: DiscoveredReportLink, *, symbol: str, aliases: list[str] | tuple[str, ...]) -> float:
    haystack = _norm(f"{link.title} {link.pdf_url}")
    clean_symbol = _norm(symbol)
    if clean_symbol and clean_symbol in haystack.split():
        return 1.0
    for alias in aliases:
        clean_alias = _norm(alias)
        if clean_alias and clean_alias in haystack:
            return 0.9
    if clean_symbol and clean_symbol in haystack:
        return 0.65
    return 0.0
```

- [ ] **Step 5: Run discovery tests**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_broker_research_discovery.py
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit**

Run:

```bash
git add broker_research/discovery.py tests/fixtures/broker_research tests/test_broker_research_discovery.py
git commit -m "feat: discover broker research links from fixtures"
```

## Task 4: PostgreSQL Storage Helpers

**Files:**
- Create: `broker_research/storage.py`
- Create: `tests/test_broker_research_storage.py`

- [ ] **Step 1: Write failing storage tests**

Create `tests/test_broker_research_storage.py`:

```python
from broker_research.discovery import DiscoveredReportLink
from broker_research.sources import BROKER_SOURCES
from broker_research.storage import (
    complete_index_run,
    list_broker_sources,
    record_index_run,
    seed_broker_sources,
    upsert_discovered_report,
)


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.conn.executed.append((sql, params))
        normalized = " ".join(sql.split())
        if "RETURNING index_run_id" in sql:
            self.rows = [(17,)]
        elif "RETURNING broker_report_id" in sql:
            self.rows = [(33,)]
        elif "FROM company_intel.broker_sources" in normalized:
            self.rows = [("icici", "ICICI Direct", "index_page", "public", True, "https://example.com")]
        else:
            self.rows = []

    def executemany(self, sql, params):
        self.conn.executed.append((sql, list(params)))

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)


class FakeConnection:
    def __init__(self):
        self.executed = []
        self.commits = 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1


def test_seed_broker_sources_upserts_registry_rows():
    conn = FakeConnection()

    count = seed_broker_sources(conn)

    sql = conn.executed[0][0]
    params = conn.executed[0][1]
    assert "INSERT INTO company_intel.broker_sources" in sql
    assert "ON CONFLICT (broker_code, source_kind, source_url) DO UPDATE" in sql
    assert len(params) == len(BROKER_SOURCES)
    assert count == len(BROKER_SOURCES)
    assert conn.commits == 1


def test_index_run_and_report_helpers_use_company_intel_tables():
    conn = FakeConnection()
    run_id = record_index_run(conn, source_id=5)
    report_id = upsert_discovered_report(
        conn,
        symbol="BEL",
        company_name="Bharat Electronics",
        link=DiscoveredReportLink(
            broker_code="icici",
            title="Bharat Electronics Q3FY26",
            pdf_url="https://www.icicidirect.com/mailcontent/idirect_bharatelectronics_q3fy26.pdf",
            source_url="https://www.icicidirect.com/mailcontent/co_reports.html",
        ),
        match_score=0.9,
    )
    complete_index_run(conn, index_run_id=run_id, status="ok", reports_found=2, reports_new=1)

    executed = "\n".join(sql for sql, _params in conn.executed)
    assert "INSERT INTO company_intel.broker_index_runs" in executed
    assert "INSERT INTO company_intel.broker_reports" in executed
    assert "UPDATE company_intel.broker_index_runs" in executed
    assert run_id == 17
    assert report_id == 33


def test_list_broker_sources_returns_dicts():
    conn = FakeConnection()

    rows = list_broker_sources(conn)

    assert rows == [
        {
            "broker_code": "icici",
            "broker_name": "ICICI Direct",
            "source_kind": "index_page",
            "access_mode": "public",
            "is_active": True,
            "source_url": "https://example.com",
        }
    ]
```

- [ ] **Step 2: Run storage tests and confirm failure**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_broker_research_storage.py
```

Expected:

```text
ModuleNotFoundError: No module named 'broker_research.storage'
```

- [ ] **Step 3: Create `broker_research/storage.py`**

Create `broker_research/storage.py` with the DB helpers from the test names. Use parameterized SQL only.

```python
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
```

- [ ] **Step 4: Run storage tests**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_broker_research_storage.py
```

Expected:

```text
passed
```

- [ ] **Step 5: Commit**

Run:

```bash
git add broker_research/storage.py tests/test_broker_research_storage.py
git commit -m "feat: store broker research metadata in postgres"
```

## Task 5: Broker Commands

**Files:**
- Create: `broker_research/commands.py`
- Create: `tests/test_broker_research_commands.py`

- [ ] **Step 1: Write failing command tests**

Create `tests/test_broker_research_commands.py`:

```python
from broker_research.commands import (
    BrokerIndexOptions,
    handle_broker_index_command,
    parse_broker_index_command,
    render_broker_sources,
)


ICICI_URL = "https://www.icicidirect.com/mailcontent/co_reports.html"


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.conn.executed.append((sql, params))
        normalized = " ".join(sql.split())
        if "SELECT alias FROM company_intel.company_aliases" in normalized:
            self.rows = [("Bharat Electronics",)]
        elif "RETURNING broker_report_id" in sql:
            self.rows = [(77,)]
        else:
            self.rows = []

    def executemany(self, sql, params):
        self.conn.executed.append((sql, list(params)))

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)


class FakeConnection:
    def __init__(self):
        self.executed = []
        self.commits = 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1


def test_parse_broker_index_command_defaults():
    options = parse_broker_index_command("/broker-index BEL")

    assert options == BrokerIndexOptions(symbol="BEL", broker="", all_public=False, refresh=False)


def test_parse_broker_index_command_flags():
    options = parse_broker_index_command("/broker-index bel --broker icici --all-public --refresh")

    assert options == BrokerIndexOptions(symbol="BEL", broker="icici", all_public=True, refresh=True)


def test_render_broker_sources_has_research_only_framing():
    output = render_broker_sources(
        [
            {
                "broker_code": "icici",
                "broker_name": "ICICI Direct",
                "source_kind": "index_page",
                "access_mode": "public",
                "is_active": True,
                "source_url": "https://www.icicidirect.com/mailcontent/co_reports.html",
            }
        ]
    )

    assert "Not investment advice" in output
    assert "ICICI Direct" in output
    assert "public" in output


def test_handle_broker_index_command_uses_injected_html_without_network():
    conn = FakeConnection()
    html = '<a href="idirect_bharatelectronics_q3fy26.pdf">Bharat Electronics Q3FY26 Result Update</a>'

    output = handle_broker_index_command(
        "/broker-index BEL --broker icici",
        conn=conn,
        html_by_source_url={ICICI_URL: html},
    )

    executed_sql = "\n".join(sql for sql, _params in conn.executed)
    assert "Broker Index: BEL" in output
    assert "Links discovered: 1" in output
    assert "Symbol matches: 1" in output
    assert "INSERT INTO company_intel.broker_reports" in executed_sql
```

- [ ] **Step 2: Run command tests and confirm failure**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_broker_research_commands.py
```

Expected:

```text
ModuleNotFoundError: No module named 'broker_research.commands'
```

- [ ] **Step 3: Create `broker_research/commands.py`**

Create the parser and renderer:

```python
"""User-facing broker research command handlers."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any

from company_intelligence_pg import connect, get_company_aliases, upsert_company

from .discovery import discover_report_links, score_report_match
from .sources import active_public_sources
from .storage import list_broker_sources, seed_broker_sources, upsert_discovered_report


DISCLAIMER = "Not investment advice. For research and learning only."


@dataclass(frozen=True)
class BrokerIndexOptions:
    symbol: str
    broker: str = ""
    all_public: bool = False
    refresh: bool = False


def parse_broker_index_command(text: str) -> BrokerIndexOptions:
    parser = argparse.ArgumentParser(prog="/broker-index", add_help=False)
    parser.add_argument("command")
    parser.add_argument("symbol")
    parser.add_argument("--broker", default="")
    parser.add_argument("--all-public", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args((text or "").split())
    return BrokerIndexOptions(
        symbol=args.symbol.strip().upper(),
        broker=args.broker.strip().lower(),
        all_public=bool(args.all_public),
        refresh=bool(args.refresh),
    )


def render_broker_sources(rows: list[dict[str, Any]]) -> str:
    lines = [f"━━━ {DISCLAIMER} ━━━", "", "## Broker Research Sources", ""]
    if not rows:
        lines.append("No broker sources are registered.")
        return "\n".join(lines)
    lines.append("| Broker | Kind | Access | Active | URL |")
    lines.append("|---|---:|---:|---:|---|")
    for row in rows:
        active = "yes" if row["is_active"] else "no"
        lines.append(
            f"| {row['broker_name']} | {row['source_kind']} | {row['access_mode']} | {active} | {row['source_url']} |"
        )
    return "\n".join(lines)


def handle_broker_sources_command(*, conn: Any | None = None) -> str:
    own_conn = conn is None
    db = conn or connect()
    try:
        seed_broker_sources(db)
        return render_broker_sources(list_broker_sources(db))
    finally:
        if own_conn:
            db.close()


def _fetch_source_html(source_url: str, *, timeout: int = 15) -> str:
    from urllib.request import Request, urlopen

    request = Request(
        source_url,
        headers={
            "User-Agent": "AgentAddaResearchBot/1.0 (+research-only)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get("Content-Type", "")
        if "pdf" in content_type.lower():
            return f'<a href="{source_url}">{source_url.rsplit("/", 1)[-1]}</a>'
        raw = response.read(2_000_000)
    return raw.decode("utf-8", errors="replace")


def index_symbol_from_html(
    *,
    conn: Any,
    symbol: str,
    html_by_source_url: dict[str, str],
    company_name: str = "",
) -> dict[str, Any]:
    clean_symbol = symbol.strip().upper()
    upsert_company(conn, clean_symbol, company_name=company_name)
    aliases = get_company_aliases(conn, clean_symbol)
    if company_name and company_name not in aliases:
        aliases = [company_name, *aliases]
    discovered = 0
    matched = 0
    stored = 0
    for source in active_public_sources():
        html = html_by_source_url.get(source.source_url)
        if not html:
            continue
        links = discover_report_links(html, base_url=source.source_url, broker_code=source.broker_code)
        discovered += len(links)
        for link in links:
            score = score_report_match(link, symbol=clean_symbol, aliases=aliases)
            if score < 0.5:
                continue
            matched += 1
            upsert_discovered_report(
                conn,
                symbol=clean_symbol,
                company_name=company_name,
                link=link,
                match_score=score,
            )
            stored += 1
    return {"symbol": clean_symbol, "discovered": discovered, "matched": matched, "stored": stored}


def handle_broker_index_command(
    text: str,
    *,
    conn: Any | None = None,
    html_by_source_url: dict[str, str] | None = None,
) -> str:
    options = parse_broker_index_command(text)
    own_conn = conn is None
    db = conn or connect()
    try:
        seed_broker_sources(db)
        sources = active_public_sources()
        if options.broker:
            sources = tuple(source for source in sources if source.broker_code == options.broker)
        html_map = dict(html_by_source_url or {})
        for source in sources:
            if source.source_url not in html_map:
                html_map[source.source_url] = _fetch_source_html(source.source_url)
        result = index_symbol_from_html(conn=db, symbol=options.symbol, html_by_source_url=html_map)
        return "\n".join(
            [
                f"━━━ {DISCLAIMER} ━━━",
                "",
                f"## Broker Index: {result['symbol']}",
                "",
                f"- Sources scanned: {len(sources)}",
                f"- Links discovered: {result['discovered']}",
                f"- Symbol matches: {result['matched']}",
                f"- Stored report metadata rows: {result['stored']}",
                "",
                "PDF fetch, parsing, and LLM analysis are separate follow-up phases.",
            ]
        )
    finally:
        if own_conn:
            db.close()
```

- [ ] **Step 4: Run command tests**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_broker_research_commands.py
```

Expected:

```text
passed
```

- [ ] **Step 5: Commit**

Run:

```bash
git add broker_research/commands.py tests/test_broker_research_commands.py
git commit -m "feat: add broker research command handlers"
```

## Task 6: Terminal Command Registry

**Files:**
- Modify: `nse_agent.py`
- Modify: `terminal/help.py`
- Create: `tests/test_broker_research_command_registry.py`

- [ ] **Step 1: Write failing registry test**

Create `tests/test_broker_research_command_registry.py`:

```python
import nse_agent


def test_broker_commands_are_registered_in_catalog():
    commands = dict(nse_agent._SLASH_COMMANDS)

    assert "/broker-sources" in commands
    assert "/broker-index" in commands
```

- [ ] **Step 2: Run registry test and confirm failure**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_broker_research_command_registry.py
```

Expected:

```text
FAILED tests/test_broker_research_command_registry.py::test_broker_commands_are_registered_in_catalog
```

- [ ] **Step 3: Add slash catalog rows in `nse_agent.py`**

Add these rows near the existing company intelligence command rows in `_SLASH_COMMANDS`:

```python
    ("/broker-sources",                  "List PostgreSQL-backed broker research sources"),
    ("/broker-index",                    "Discover public broker reports for a symbol"),
    ("/broker-index BEL",                "Index public broker reports for Bharat Electronics"),
    ("/broker-index BEL --broker icici", "Index one broker source for a symbol"),
```

- [ ] **Step 4: Register command handlers in `_build_command_registry`**

Add this block after the `/data-coverage` handler and before natural-language report open handling in `nse_agent.py`:

```python
    # /broker-sources and /broker-index
    def _h_broker_research(query, agent, show_trace):
        from broker_research.commands import handle_broker_index_command, handle_broker_sources_command
        _print_user(query)
        q = query.strip().lower()
        if q.startswith("/broker-sources"):
            output = handle_broker_sources_command()
            console.print(Markdown(_linkify_markdown(output)))
            return True
        output = handle_broker_index_command(query)
        console.print(Markdown(_linkify_markdown(output)))
        return True
    registry.register(CommandHandler(
        name="broker-research",
        match_fn=lambda q: q.startswith(("/broker-sources", "/broker-index")),
        handler_fn=_h_broker_research,
        description="Broker research source registry and public report discovery",
    ))
```

- [ ] **Step 5: Add help entries**

In `terminal/help.py`, add broker command entries to the `Research, Documents & Broker Notes` section:

```python
            ("/broker-sources",                  "List PostgreSQL-backed broker research sources"),
            ("/broker-index BEL",                "Discover public broker reports for a symbol"),
            ("/broker-index BEL --broker icici", "Discover reports from one broker source"),
```

- [ ] **Step 6: Run registry test**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_broker_research_command_registry.py
```

Expected:

```text
passed
```

- [ ] **Step 7: Run focused broker test suite**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_broker_research_schema.py tests/test_broker_research_sources.py tests/test_broker_research_discovery.py tests/test_broker_research_storage.py tests/test_broker_research_commands.py tests/test_broker_research_command_registry.py
```

Expected:

```text
passed
```

- [ ] **Step 8: Commit**

Run:

```bash
git add nse_agent.py terminal/help.py tests/test_broker_research_command_registry.py
git commit -m "feat: expose broker research commands"
```

## Task 7: Local PostgreSQL Migration Smoke

**Files:**
- No source files expected.

- [ ] **Step 1: Run Python compile check**

Run:

```bash
./.venv/bin/python -m py_compile company_intelligence_pg.py broker_research/__init__.py broker_research/sources.py broker_research/discovery.py broker_research/storage.py broker_research/commands.py nse_agent.py terminal/help.py
```

Expected:

```text
```

The command prints no output when compilation succeeds.

- [ ] **Step 2: Run PostgreSQL migration audit when local database is available**

Run:

```bash
PG_DSN='dbname=nse_market user=nse_admin host=127.0.0.1 port=55432 password=nse_admin' AGENT_ADDA_PG_DSN='dbname=nse_market user=nse_admin host=127.0.0.1 port=55432 password=nse_admin' ../../.venv/bin/python postgres/migrate.py --audit
```

Expected output includes:

```text
company_intel
```

- [ ] **Step 3: Check broker tables exist when local database is available**

Run:

```bash
PGPASSWORD=nse_admin psql "dbname=nse_market user=nse_admin host=127.0.0.1 port=55432" -Atc "select table_name from information_schema.tables where table_schema='company_intel' and table_name like 'broker_%' order by table_name;"
```

Expected output includes:

```text
broker_index_runs
broker_report_pages
broker_report_tables
broker_reports
broker_research_facts
broker_research_runs
broker_sources
```

- [ ] **Step 4: Commit smoke-only adjustments if needed**

If Step 1, Step 2, or Step 3 exposes a code or migration issue, commit the fix:

```bash
git add company_intelligence_pg.py postgres/migrations/20260612_company_intel.sql broker_research nse_agent.py terminal/help.py tests
git commit -m "fix: stabilize broker research phase1"
```

If no source files changed after smoke, skip this commit.

## Final Verification

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_broker_research_schema.py tests/test_broker_research_sources.py tests/test_broker_research_discovery.py tests/test_broker_research_storage.py tests/test_broker_research_commands.py tests/test_broker_research_command_registry.py tests/test_company_intelligence_pg.py
```

Expected:

```text
passed
```

Run:

```bash
./.venv/bin/python -m py_compile company_intelligence_pg.py broker_research/__init__.py broker_research/sources.py broker_research/discovery.py broker_research/storage.py broker_research/commands.py nse_agent.py terminal/help.py
```

Expected:

```text
```

The compile command prints no output when all files compile.

## Self-Review

Spec coverage:

- PostgreSQL storage is covered by Tasks 1 and 4.
- Source registry seed is covered by Task 2.
- Public-source discovery is covered by Task 3.
- User-visible commands are covered by Tasks 5 and 6.
- Live PDF fetch, parsing, fact extraction, consensus, and final research writing are intentionally out of Phase 1 and remain in the design spec for Phases 2-5.

Type consistency:

- `BrokerSource.as_insert_params()` returns the same field order used by `seed_broker_sources()`.
- `DiscoveredReportLink` fields match `upsert_discovered_report()`.
- `BrokerIndexOptions` fields match `parse_broker_index_command()` tests.

Validation approach:

- Unit tests require no network access.
- Migration smoke uses the local PostgreSQL DSN already used by this repo when available.
- Terminal command integration is checked by catalog registration first; Phase 1 unit tests inject HTML, and a manual `/broker-index BEL --broker icici` smoke can be run when public broker sites are reachable.
