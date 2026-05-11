# Company + Sector X-Ray Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a company-anchored intelligence workflow that creates a reusable evidence database, runs source-audited multi-step search, expands into sector and competitive context, maps RBI/Budget impact, and generates strict or permissive analyst memos.

**Architecture:** Implement this as an additive Agent Adda capability. A SQLite evidence store records companies, aliases, source documents, search attempts, evidence chunks, structured facts, macro/policy events, impact assessments, and report runs. A `/company-xray` command and `/ric company-xray` workflow orchestrate source retrieval, categorization, analysis, and report generation.

**Tech Stack:** Python 3, SQLite, local filesystem cache, existing Agent Adda terminal/RIC/report patterns, existing filing and sector intelligence modules, pytest.

---

## Phase 0: Design and Readiness

### CX-0.1: Finalize Product Contract

**Files:**
- Read: `docs/superpowers/specs/2026-05-10-company-sector-xray-intelligence-design.md`
- Modify: `docs/AGENT_ADDA_CAPABILITIES.md`

- [ ] **Step 1: Add capability summary to docs**

Add a new section to `docs/AGENT_ADDA_CAPABILITIES.md` describing:

```text
Company + Sector X-Ray
- /company-xray SYMBOL
- /company-xray SYMBOL --strict
- /ric company-xray SYMBOL
- evidence coverage table
- official/external/LLM tiering
- research-only disclaimer
```

- [ ] **Step 2: Verify docs mention source audit**

Run:

```bash
rg -n "company-xray|evidence coverage|search audit" docs/AGENT_ADDA_CAPABILITIES.md
```

Expected: all three phrases are found.

### CX-0.2: Define Source Registry

**Files:**
- Create: `data/company_intelligence/source_registry.json`

- [ ] **Step 1: Create initial source registry**

Create JSON entries for source groups:

```json
{
  "official_exchange": {
    "tier": 1,
    "sources": ["NSE", "BSE"],
    "allowed_document_types": ["filing", "announcement", "results", "shareholding", "concall_transcript"]
  },
  "official_policy": {
    "tier": 1,
    "sources": ["RBI", "Union Budget", "Ministry of Finance", "PIB"],
    "allowed_document_types": ["policy_statement", "budget_document", "press_release"]
  },
  "company_ir": {
    "tier": 1,
    "sources": ["company_website", "investor_relations"],
    "allowed_document_types": ["annual_report", "investor_presentation", "results", "transcript"]
  },
  "structured_internal": {
    "tier": 2,
    "sources": ["agent_adda_fundamentals", "sector_rotation", "technical_cache", "knowledge_graph"],
    "allowed_document_types": ["dataset", "report", "cache"]
  },
  "external_context": {
    "tier": 3,
    "sources": ["news", "industry_articles", "analyst_coverage", "broker_research_landing_pages", "rating_commentary"],
    "allowed_document_types": ["article", "summary", "landing_page", "public_pdf"]
  }
}
```

- [ ] **Step 2: Validate JSON**

Run:

```bash
python3 -m json.tool data/company_intelligence/source_registry.json >/tmp/company_source_registry.json
```

Expected: exit code 0.

## Phase 1: Database Foundation

### CX-1.1: SQLite Schema

**Files:**
- Create: `company_intelligence_db.py`
- Test: `tests/test_company_intelligence_db.py`

- [ ] **Step 1: Write schema initialization test**

Create tests that assert `init_company_intelligence_db(path)` creates these tables:

```text
companies
company_aliases
source_documents
search_runs
search_attempts
evidence_chunks
structured_facts
sector_entities
macro_policy_events
impact_assessments
analysis_runs
```

- [ ] **Step 2: Run failing test**

Run:

```bash
pytest tests/test_company_intelligence_db.py -v
```

Expected: fails because `company_intelligence_db.py` does not exist.

- [ ] **Step 3: Implement schema**

Implement:

```python
def init_company_intelligence_db(db_path: str | Path) -> Path:
    """Create the company intelligence SQLite database and return its path."""
```

Use `sqlite3`, `Path`, and `CREATE TABLE IF NOT EXISTS`.

- [ ] **Step 4: Run passing test**

Run:

```bash
pytest tests/test_company_intelligence_db.py -v
```

Expected: all DB schema tests pass.

### CX-1.2: Company and Alias Upsert

**Files:**
- Modify: `company_intelligence_db.py`
- Test: `tests/test_company_intelligence_db.py`

- [ ] **Step 1: Add upsert tests**

Test:

- `upsert_company()` inserts and updates `companies`.
- `add_company_alias()` avoids duplicate aliases.
- aliases support `symbol`, `company_name`, `bse_name`, and `common_name`.

- [ ] **Step 2: Implement upserts**

Implement:

```python
def upsert_company(conn, symbol: str, company_name: str = "", sector: str = "", industry: str = "", website: str = "") -> None
def add_company_alias(conn, symbol: str, alias: str, alias_type: str, source: str = "system") -> None
def get_company_aliases(conn, symbol: str) -> list[str]
```

- [ ] **Step 3: Run tests**

Run:

```bash
pytest tests/test_company_intelligence_db.py -v
```

Expected: alias and upsert tests pass.

## Phase 2: Search Audit Engine

### CX-2.1: Search Run Logging

**Files:**
- Create: `company_intelligence_search.py`
- Modify: `company_intelligence_db.py`
- Test: `tests/test_company_intelligence_search.py`

- [ ] **Step 1: Write audit logging tests**

Test that a search run can log:

- symbol
- verticals
- mode
- source group
- query string
- alias used
- result count
- URLs found
- status
- failure reason

- [ ] **Step 2: Implement audit functions**

Implement:

```python
def start_search_run(conn, symbol: str, verticals: list[str], mode: str) -> int
def log_search_attempt(conn, search_run_id: int, source_group: str, query: str, alias_used: str, result_count: int, urls_found: list[str], status: str, failure_reason: str = "") -> int
def complete_search_run(conn, search_run_id: int, status: str, summary: str = "") -> None
```

- [ ] **Step 3: Run tests**

Run:

```bash
pytest tests/test_company_intelligence_search.py -v
```

Expected: audit logging tests pass.

### CX-2.2: Alias-Aware Query Builder

**Files:**
- Modify: `company_intelligence_search.py`
- Test: `tests/test_company_intelligence_search.py`

- [ ] **Step 1: Add DMART regression test**

For symbol `DMART`, aliases should produce queries containing:

```text
DMART
Avenue Supermarts
Avenue Supermarts Ltd
AVENUE SUPERMARTS
```

For verticals `analyst_coverage`, `broker_research`, `concalls`, generated queries should include variants such as:

```text
Avenue Supermarts concall transcript
DMART broker research
Avenue Supermarts analyst coverage
AVENUE SUPERMARTS investor presentation
```

- [ ] **Step 2: Implement query builder**

Implement:

```python
def build_search_queries(symbol: str, aliases: list[str], verticals: list[str]) -> list[dict]
```

Each dict should include:

```python
{
    "vertical": "concalls",
    "alias": "Avenue Supermarts",
    "query": "Avenue Supermarts concall transcript"
}
```

- [ ] **Step 3: Run tests**

Run:

```bash
pytest tests/test_company_intelligence_search.py -v
```

Expected: query builder tests pass.

## Phase 2A: Company Website Indexing Backend

### CX-2A.1: Website Index Schema

**Files:**
- Modify: `company_intelligence_db.py`
- Test: `tests/test_company_intelligence_db.py`

- [ ] **Step 1: Extend schema tests**

Assert these tables exist:

```text
website_crawl_runs
website_pages
website_links
website_page_chunks
website_search_fts
```

- [ ] **Step 2: Implement schema**

Add regular tables plus a SQLite FTS5 virtual table for website chunk search.

- [ ] **Step 3: Run tests**

Run:

```bash
./.venv/bin/python -m unittest tests.test_company_intelligence_db -v
```

Expected: DB tests pass.

### CX-2A.2: Same-Domain Website Crawler and Document Discovery

**Files:**
- Create: `company_website_indexer.py`
- Test: `tests/test_company_website_indexer.py`

- [ ] **Step 1: Write crawler tests with fake pages**

Test that the crawler:

- normalizes relative links
- follows same-domain HTML links
- skips off-domain links
- records linked PDFs/documents
- classifies annual report, investor presentation, results, and transcript links
- respects `max_pages`

- [ ] **Step 2: Implement crawler foundation**

Implement:

```python
def crawl_company_website(conn, symbol, base_url, fetcher, max_pages=25, max_depth=1, include_documents=True) -> dict
def search_company_website(conn, symbol, query, limit=10) -> list[dict]
```

- [ ] **Step 3: Run tests**

Run:

```bash
./.venv/bin/python -m unittest tests.test_company_website_indexer -v
```

Expected: crawler/indexer tests pass.

### CX-2A.3: Website Index Search Integration

**Files:**
- Modify: `company_intelligence_search.py`
- Test: `tests/test_company_intelligence_search.py`

- [ ] **Step 1: Broaden vertical patterns**

Add verticals:

```text
company_website
investor_relations
annual_reports
investor_presentations
concall_transcripts
product_pages
store_network
leadership
customers
suppliers
market_share
competitors
regulatory
litigation
ratings
budget_impact
rbi_impact
```

- [ ] **Step 2: Add website-index-first query plan**

Search planning should indicate `source_group = website_index` for company website and IR verticals.

- [ ] **Step 3: Run tests**

Run:

```bash
./.venv/bin/python -m unittest tests.test_company_intelligence_search -v
```

Expected: expanded search query tests pass.

### CX-2A.4: Real Website Fetcher and Crawl Safety

**Files:**
- Modify: `company_website_indexer.py`
- Test: `tests/test_company_website_indexer.py`

- [x] **Step 1: Write fetcher tests**

Test:

- HTTP timeout returns structured error
- unsupported content type is skipped
- response larger than max bytes is skipped
- robots.txt disallow is respected when enabled
- sitemap URLs can seed crawl queue

- [x] **Step 2: Implement safe fetcher**

Implement:

```python
def fetch_url(url: str, timeout: float = 10.0, max_bytes: int = 5_000_000, user_agent: str = "AgentAddaResearchBot/1.0") -> dict
def discover_sitemap_urls(base_url: str, fetcher=fetch_url) -> list[str]
def robots_allows(url: str, user_agent: str = "AgentAddaResearchBot/1.0", fetcher=fetch_url) -> bool
```

- [x] **Step 3: Run tests**

Run:

```bash
./.venv/bin/python -m unittest tests.test_company_website_indexer -v
```

Expected: fetcher and crawl-safety tests pass.

### CX-2A.5: Linked Document Download and Parsing

**Status:** Partial. Linked document download, idempotency, metadata storage, and optional crawl-time persistence are implemented. PDF/text parsing and promotion of parsed document text still remain.

**Files:**
- Modify: `company_website_indexer.py`
- Modify: `financial_filing_agent.py` if a small reusable parser hook is needed
- Test: `tests/test_company_website_indexer.py`

- [x] **Step 1: Write linked document tests**

Test:

- annual report PDF link is downloaded once
- investor presentation PDF link is downloaded once
- transcript PDF link is downloaded once
- parsed text is stored as website page text or source document evidence
- unchanged content hash is not re-downloaded

- [x] **Step 2: Implement document download path**

Store downloaded documents under:

```text
data/company_intelligence/documents/{SYMBOL}/
```

Use source metadata in `source_documents` and website link metadata in `website_links`.

- [x] **Step 3: Run tests**

Run:

```bash
./.venv/bin/python -m unittest tests.test_company_website_indexer tests.test_financial_filing_agent -v
```

Expected: document discovery/download tests pass and filing parser tests still pass.

### CX-2A.6: `/company-index` Terminal Command

**Status:** Implemented with a backend runner, terminal route, generic HTML crawl path, bounded document download, and DMart SPA/API adapter for official investor files. `--stale-only` remains reserved for CX-2A.8 scheduled/stale refresh.

**Files:**
- Modify: `nse_agent.py`
- Modify: `docs/AGENT_ADDA_CAPABILITIES.md`
- Test: `tests/test_company_index_command.py`
- Test: `tests/test_company_website_adapters.py`

- [x] **Step 1: Write command parsing tests**

Test:

```text
/company-index DMART
/company-index DMART --refresh
/company-index DMART --max-pages 50
/company-index DMART --include-documents
/company-index --stale-only
```

- [x] **Step 2: Implement terminal command**

Command should call `crawl_company_website()` using the resolved company website and show:

- pages indexed
- documents found
- skipped/off-domain links
- DB path
- next suggested `/company-xray SYMBOL`

- [x] **Step 3: Run tests**

Run:

```bash
./.venv/bin/python -m unittest tests.test_company_index_command tests.test_company_website_adapters -v
```

Expected: command parser and handler tests pass.

### CX-2A.7: Website Index to Evidence Promotion

**Status:** Implemented. Indexed website chunks and downloaded source documents are promoted into `evidence_chunks`, and `run_company_xray()` consumes those records before scoring coverage and rendering reports.

**Files:**
- Modify: `company_intelligence.py`
- Create: `company_intelligence_promote.py`
- Test: `tests/test_company_intelligence.py`
- Test: `tests/test_company_intelligence_promote.py`

- [x] **Step 1: Write promotion tests**

Test that `/company-xray` or `run_company_xray()` can search website FTS and promote relevant chunks into `evidence_chunks` for categories:

- business model
- customer base
- operating model
- market share
- competitors
- risks

- [x] **Step 2: Implement promotion helper**

Implement:

```python
def promote_indexed_company_evidence(conn, symbol: str, parse_documents: bool = True, ...) -> dict
```

- [x] **Step 3: Run tests**

Run:

```bash
./.venv/bin/python -m unittest tests.test_company_intelligence tests.test_company_website_indexer -v
```

Expected: promoted website evidence appears in reports and DB.

### CX-2A.8: Scheduled/Stale Company Index Job

**Status:** Implemented as a backend job. It selects stale/no-index symbols, skips fresh symbols, respects `max_companies`, records failed crawl runs, and continues across the batch.

**Files:**
- Create: `company_index_job.py`
- Test: `tests/test_company_index_job.py`

- [x] **Step 1: Write stale-job tests**

Test:

- stale company index is selected for refresh
- fresh company index is skipped
- job respects max companies
- failed crawl records failure without stopping the batch

- [x] **Step 2: Implement backend job**

Implement:

```python
def run_company_index_job(symbols: list[str], stale_days: int = 30, max_companies: int = 25, refresh: bool = False) -> dict
```

- [x] **Step 3: Run tests**

Run:

```bash
./.venv/bin/python -m unittest tests.test_company_index_job -v
```

Expected: stale indexing job tests pass.

## Phase 3: Evidence and Classification

### CX-3.1: Evidence Chunk Store

**Files:**
- Create: `company_intelligence_extract.py`
- Modify: `company_intelligence_db.py`
- Test: `tests/test_company_intelligence_extract.py`

- [ ] **Step 1: Write evidence insert/query tests**

Test that `store_evidence_chunk()` stores:

- document ID
- symbol
- category
- text
- page number
- table ID
- source tier
- confidence
- evidence date

- [ ] **Step 2: Implement evidence helpers**

Implement:

```python
def store_evidence_chunk(conn, document_id: str, symbol: str, category: str, text: str, source_tier: int, confidence: float, page_number: int | None = None, table_id: str = "", evidence_date: str = "") -> int
def list_evidence_by_symbol(conn, symbol: str, category: str | None = None) -> list[dict]
```

- [ ] **Step 3: Run tests**

Run:

```bash
pytest tests/test_company_intelligence_extract.py -v
```

Expected: evidence storage tests pass.

### CX-3.2: Deterministic Category Classifier

**Files:**
- Modify: `company_intelligence_extract.py`
- Test: `tests/test_company_intelligence_extract.py`

- [ ] **Step 1: Write classification tests**

Test sample text maps to categories:

```text
"same store sales growth and new store additions" -> operating model
"customers include BFSI and retail clients" -> customer base
"market share increased in organized grocery retail" -> market share
"repo rate cut may reduce borrowing costs" -> RBI monetary policy sensitivity
"budget capex allocation supports infrastructure demand" -> Union Budget sensitivity
```

- [ ] **Step 2: Implement keyword classifier**

Implement:

```python
def classify_evidence_text(text: str) -> list[str]
```

Use deterministic keyword rules first. LLM classification can be added later after deterministic tests pass.

- [ ] **Step 3: Run tests**

Run:

```bash
pytest tests/test_company_intelligence_extract.py -v
```

Expected: classification tests pass.

## Phase 4: Source Connectors and Controlled Search

### CX-4.1: Official/Internal Source Collector

**Files:**
- Create: `company_intelligence_sources.py`
- Test: `tests/test_company_intelligence_sources.py`

- [ ] **Step 1: Write source collection tests with fakes**

Use fake local fixtures to test that official/internal collectors return normalized source records:

```python
{
    "source_tier": 1,
    "source_name": "Company IR",
    "source_url": "https://example.com/dmart-results.pdf",
    "document_type": "investor_presentation",
    "document_date": "2026-04-30",
    "title": "Avenue Supermarts Q4 FY26 Investor Presentation"
}
```

- [ ] **Step 2: Implement collector interface**

Implement:

```python
def collect_official_sources(symbol: str, aliases: list[str]) -> list[dict]
def collect_internal_sources(symbol: str) -> list[dict]
```

The first version can return local known report/cache paths and source metadata. Network fetches should be added behind timeout-protected helpers.

- [ ] **Step 3: Run tests**

Run:

```bash
pytest tests/test_company_intelligence_sources.py -v
```

Expected: source normalization tests pass.

### CX-4.2: External Search Result Normalization

**Files:**
- Modify: `company_intelligence_sources.py`
- Test: `tests/test_company_intelligence_sources.py`

- [ ] **Step 1: Write normalization tests**

Test that raw search result dicts normalize into:

- title
- url
- snippet
- source group
- source tier
- query
- alias used

- [ ] **Step 2: Implement normalizer**

Implement:

```python
def normalize_external_search_results(results: list[dict], query: str, alias_used: str, source_group: str) -> list[dict]
```

- [ ] **Step 3: Run tests**

Run:

```bash
pytest tests/test_company_intelligence_sources.py -v
```

Expected: search normalization tests pass.

## Phase 5: RBI and Budget Impact Intelligence

### CX-5.1: Policy Event Store

**Files:**
- Create: `company_intelligence_policy.py`
- Test: `tests/test_company_intelligence_policy.py`

- [ ] **Step 1: Write policy event tests**

Test insertion and retrieval of:

- RBI repo-rate event
- Union Budget capex event
- Ministry release event

- [ ] **Step 2: Implement policy event helpers**

Implement:

```python
def store_policy_event(conn, event_type: str, event_date: str, title: str, source_url: str, summary: str, raw_path: str = "") -> int
def list_policy_events(conn, event_type: str | None = None) -> list[dict]
```

- [ ] **Step 3: Run tests**

Run:

```bash
pytest tests/test_company_intelligence_policy.py -v
```

Expected: policy event tests pass.

### CX-5.2: Company Sensitivity Mapping

**Files:**
- Modify: `company_intelligence_policy.py`
- Test: `tests/test_company_intelligence_policy.py`

- [ ] **Step 1: Write impact mapping tests**

Test these deterministic mappings:

- high debt + rate cut -> borrowing-cost tailwind
- consumption company + tax relief -> demand tailwind
- infrastructure supplier + budget capex -> demand tailwind
- import-heavy company + INR weakness -> cost headwind

- [ ] **Step 2: Implement mapper**

Implement:

```python
def assess_policy_impact(company_profile: dict, event: dict, evidence: list[dict]) -> dict
```

Return:

```python
{
    "impact_area": "borrowing_cost",
    "direction": "positive",
    "magnitude": "medium",
    "rationale": "...",
    "confidence": 0.65
}
```

- [ ] **Step 3: Run tests**

Run:

```bash
pytest tests/test_company_intelligence_policy.py -v
```

Expected: policy impact tests pass.

## Phase 6: Analysis and Deliberation Engine

### CX-6.1: Evidence Coverage Scoring

**Files:**
- Create: `company_intelligence_analyze.py`
- Test: `tests/test_company_intelligence_analyze.py`

- [ ] **Step 1: Write coverage scoring tests**

Test output for:

- high official evidence
- weak broker research
- no concall transcripts
- enough evidence for permissive report
- insufficient evidence for strict report

- [ ] **Step 2: Implement coverage scorer**

Implement:

```python
def score_evidence_coverage(evidence: list[dict], search_attempts: list[dict]) -> dict
def strict_mode_passes(coverage: dict) -> tuple[bool, list[str]]
```

- [ ] **Step 3: Run tests**

Run:

```bash
pytest tests/test_company_intelligence_analyze.py -v
```

Expected: coverage scoring tests pass.

### CX-6.2: Bull/Bear/Base Case Builder

**Files:**
- Modify: `company_intelligence_analyze.py`
- Test: `tests/test_company_intelligence_analyze.py`

- [ ] **Step 1: Write case-builder tests**

Given categorized evidence, test that output includes:

- bull case
- bear case
- base case
- evidence gaps
- disconfirming evidence
- open questions

- [ ] **Step 2: Implement deterministic case skeleton**

Implement:

```python
def build_deliberation_view(symbol: str, evidence_by_category: dict, coverage: dict, policy_impacts: list[dict]) -> dict
```

The v1 implementation should produce structured sections without needing an LLM call.

- [ ] **Step 3: Run tests**

Run:

```bash
pytest tests/test_company_intelligence_analyze.py -v
```

Expected: deliberation structure tests pass.

## Phase 7: Report Generation

### CX-7.1: Markdown Report

**Files:**
- Create: `company_intelligence_report.py`
- Test: `tests/test_company_intelligence_report.py`

- [ ] **Step 1: Write report tests**

Test Markdown contains:

- company snapshot
- evidence coverage
- business model
- customer base
- sector structure
- market share
- competitors
- RBI impact
- Budget impact
- bull/bear/base case
- open questions
- evidence table
- research-only disclaimer

- [ ] **Step 2: Implement Markdown renderer**

Implement:

```python
def render_company_xray_markdown(model: dict) -> str
```

- [ ] **Step 3: Run tests**

Run:

```bash
pytest tests/test_company_intelligence_report.py -v
```

Expected: Markdown report tests pass.

### CX-7.2: HTML Report via Existing Report Engine

**Files:**
- Modify: `company_intelligence_report.py`
- Modify: `terminal/reports.py`
- Test: `tests/test_company_intelligence_report.py`

- [ ] **Step 1: Write HTML smoke test**

Test generated HTML contains:

- title
- evidence coverage table
- report sections
- disclaimer

- [ ] **Step 2: Implement HTML renderer**

Use the existing style from `terminal/reports.py` where practical.

Implement:

```python
def render_company_xray_html(model: dict) -> str
def write_company_xray_report(symbol: str, markdown: str, html: str, output_dir: Path) -> dict
```

- [ ] **Step 3: Run tests**

Run:

```bash
pytest tests/test_company_intelligence_report.py -v
```

Expected: HTML/report writing tests pass.

## Phase 8: Orchestration and Terminal Integration

### CX-8.1: Main Orchestrator

**Files:**
- Create: `company_intelligence.py`
- Test: `tests/test_company_intelligence.py`

- [ ] **Step 1: Write orchestration tests with fake collectors**

Test:

- permissive mode generates report with weak evidence gaps
- strict mode blocks weak report and returns gap report
- search attempts are logged
- analysis run is recorded

- [ ] **Step 2: Implement orchestrator**

Implement:

```python
def run_company_xray(symbol: str, strict: bool = False, refresh: bool = False, db_path: str | Path = "data/company_intelligence/company_intelligence.db") -> dict
```

Return:

```python
{
    "symbol": "DMART",
    "status": "ok",
    "strict": false,
    "coverage": {...},
    "report_markdown_path": "...",
    "report_html_path": "...",
    "known_gaps": [...]
}
```

- [ ] **Step 3: Run tests**

Run:

```bash
pytest tests/test_company_intelligence.py -v
```

Expected: orchestration tests pass.

### CX-8.2: Terminal Command

**Status:** Implemented through `company_xray_command.py` plus a direct `nse_agent.py` route.

**Files:**
- Modify: `nse_agent.py`
- Create: `company_xray_command.py`
- Test: `tests/test_company_xray_command.py`

- [x] **Step 1: Add command parsing tests**

Test commands:

```text
/company-xray DMART
/company-xray DMART --strict
/company-xray DMART --refresh
```

- [x] **Step 2: Integrate command handler**

Add a direct terminal command that calls `run_company_xray()`.

Expected behavior:

- show evidence coverage summary
- show report paths
- show strict-mode gaps when blocked
- always show research-only disclaimer

- [x] **Step 3: Run tests**

Run:

```bash
./.venv/bin/python -m unittest tests.test_company_xray_command -v
```

Expected: terminal parsing tests pass.

### CX-8.3: RIC Integration

**Status:** Implemented as a 9-step RIC recipe in `nse_agent.py`.

**Files:**
- Modify: `nse_agent.py`
- Modify: `docs/AGENT_ADDA_CAPABILITIES.md`
- Test: `tests/test_ric_company_xray.py`

- [x] **Step 1: Add RIC definition test**

Test `/ric company-xray DMART` resolves to a multi-step recipe.

- [x] **Step 2: Add RIC recipe**

Add steps:

```text
Resolve identity
Build evidence
Business model
Sector expansion
Competitive map
Financial and market behavior
RBI/Budget impact
Deliberation
Final report
```

- [x] **Step 3: Run tests**

Run:

```bash
./.venv/bin/python -m unittest tests.test_ric_company_xray -v
```

Expected: RIC definition and routing tests pass.

## Phase 9: Regression and End-to-End Tests

### CX-9.1: DMART No-Result Regression

**Files:**
- Test: `tests/test_company_xray_dmart_regression.py`

- [ ] **Step 1: Create fake no-result source fixtures**

Create fake collectors that return no direct broker/concall documents but log attempts.

- [ ] **Step 2: Assert report quality**

Test that the report includes:

- aliases searched
- queries attempted
- no-result status
- failure reasons
- evidence coverage table
- known gaps
- no fabricated broker targets

- [ ] **Step 3: Run test**

Run:

```bash
pytest tests/test_company_xray_dmart_regression.py -v
```

Expected: DMART no-result regression passes.

### CX-9.2: Full Test Slice

**Files:**
- All Company X-Ray modules and tests

- [ ] **Step 1: Run full Company X-Ray tests**

Run:

```bash
pytest tests/test_company_intelligence*.py tests/test_company_xray_dmart_regression.py tests/test_ric_company_xray.py -v
```

Expected: all Company X-Ray tests pass.

- [ ] **Step 2: Run relevant existing terminal/report tests**

Run:

```bash
pytest tests -k "report or ric or company" -v
```

Expected: no regressions in related report/RIC behavior.

## Phase 10: Documentation and Acceptance

### CX-10.1: Documentation Update

**Files:**
- Modify: `docs/AGENT_ADDA_CAPABILITIES.md`
- Modify: `docs/BACKLOG.md`

- [ ] **Step 1: Document usage**

Document:

```text
/company-xray SYMBOL
/company-xray SYMBOL --strict
/company-xray SYMBOL --refresh
/ric company-xray SYMBOL
```

- [ ] **Step 2: Document evidence model**

Document the difference between:

- official evidence
- structured internal data
- external context
- LLM interpretation

- [ ] **Step 3: Verify documentation**

Run:

```bash
rg -n "Company \\+ Sector X-Ray|/company-xray|official evidence|LLM interpretation" docs
```

Expected: relevant docs contain the new capability and evidence model.

## Acceptance Checklist

- [ ] SQLite DB initializes all required tables.
- [ ] Company aliases are stored and reused.
- [ ] Search runs and failed search attempts are auditable.
- [ ] DMART-style no-result searches produce evidence gaps, not generic prose.
- [ ] Evidence chunks are categorized.
- [ ] Strict mode blocks weak reports.
- [ ] Permissive mode generates reports with confidence labels.
- [ ] RBI/Budget impact mapping is represented as derived analysis.
- [ ] Markdown and HTML reports are generated.
- [ ] `/company-xray SYMBOL` works.
- [ ] `/ric company-xray SYMBOL` works.
- [ ] Tests cover DB, search audit, evidence classification, reporting, terminal routing, and DMART regression.

## Self-Review

- Spec coverage: all design requirements have implementation phases.
- Placeholder scan: no incomplete sections remain.
- Type consistency: module names and function names are consistent across phases.
- Scope check: v1 is company-first with optional sector expansion, not a broad sector intelligence platform.
