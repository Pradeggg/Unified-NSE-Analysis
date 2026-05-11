# Company + Sector X-Ray Intelligence Design

Date: 2026-05-10
Owner: Agent Adda / Codex
Audience: Agent Adda product and implementation workers
Primary output: company-anchored sector intelligence workflow, knowledge base, and analyst memo

## Goal

Build a Company + Sector X-Ray intelligence capability for Agent Adda.

The user starts from one listed company symbol. Agent Adda builds or refreshes a company knowledge base, expands into sector context, maps competitors and customer base, evaluates business model and operating model, links RBI and Union Budget impacts, records search coverage, and generates a deliberation-style analyst memo.

The first user-facing workflow should be:

```text
/ric company-xray DMART
/company-xray DMART
/company-xray DMART --strict
```

The system should support both:

- **Permissive mode:** generate the report even when evidence is incomplete, while showing confidence and evidence gaps clearly.
- **Strict mode:** require minimum official/source coverage before producing a full memo.

## Core Product Principle

Never store only an LLM summary.

The system must store:

- raw source documents or source metadata
- search runs and query attempts
- extracted evidence chunks
- structured facts
- category labels
- source confidence tier
- generated interpretations
- report run metadata

This makes the intelligence reusable for historical comparison, recent analysis, multi-step search, and future re-analysis.

## Source Strategy

Use a tiered source system.

### Tier 1: Official Evidence

Highest-confidence sources:

- NSE filings and announcements
- BSE filings and announcements
- annual reports
- quarterly results
- investor presentations
- concall transcripts from company/NSE/BSE sources
- company investor-relations pages
- RBI policy statements
- RBI monetary policy committee minutes
- Union Budget documents
- Ministry of Finance releases
- relevant sector ministry releases
- company website pages
- crawled company website and investor-relations pages
- linked documents discovered on company/IR pages, especially annual reports, investor presentations, results PDFs, and concall transcripts

### Tier 2: Structured Market and Fundamental Data

Internal and semi-structured data:

- existing Agent Adda price, technical, sector rotation, macro, FII/DII, and global-market datasets
- Screener-style fundamentals already cached in the repo
- peer tables and financial ratios when available
- knowledge graph sector and supply-chain edges
- filing-intelligence extracted facts

### Tier 3: External Context

Lower-confidence supporting sources:

- news websites
- industry articles
- rating agency commentary
- exchange-linked research pages
- brokerage report landing pages where accessible
- analyst coverage pages
- public concall-summary sources

External context should support or challenge official evidence. It should not override official filings unless the report explicitly states the conflict.

### Tier 4: LLM Interpretation

LLM output is interpretation, not evidence. It should be stored separately from source facts and should reference evidence IDs whenever possible.

## Knowledge Categories

Every extracted evidence chunk should be classified into one or more categories:

- company identity
- business model
- revenue segments
- product lines
- customer base
- client concentration
- geography
- suppliers
- distribution channel
- operating model
- store/network/capacity footprint
- cost structure
- pricing power
- margin drivers
- sector definition
- sector value chain
- demand drivers
- supply drivers
- market share
- competitor list
- peer comparison
- competitive advantage
- moat durability
- regulation
- RBI monetary policy sensitivity
- Union Budget sensitivity
- commodity/input sensitivity
- FX/import/export sensitivity
- capex/order book
- management commentary
- corporate actions
- risks
- financial quality
- technical/market behavior
- open questions

## Search Audit Requirement

The DMART deep-search example showed a failure pattern: the assistant returned a polished "no results found" narrative without enough proof of what was searched.

Every deep search must create an auditable search record with:

- symbol
- resolved company name
- aliases used
- verticals requested
- source groups attempted
- query strings
- result counts
- URLs found
- URLs downloaded
- parse status
- evidence chunk count
- failure reason
- confidence tier
- timestamp

The final report must include an evidence coverage table:

```text
Official filings: High / Medium / Low
Company IR: High / Medium / Low
Broker research: High / Medium / Low / Unavailable
Concalls: High / Medium / Low / Unavailable
News coverage: High / Medium / Low
Sector data: High / Medium / Low
RBI/Budget mapping: Official / Derived / Not assessed
Known gaps: explicit list
```

## Company Website Indexing Requirement

Company X-Ray should not depend only on live web search. It should maintain a local company website index that can be searched quickly and audited.

The backend indexing job should:

- start from a company website or investor-relations URL
- crawl same-domain HTML pages within configured depth and page limits
- discover linked documents on crawled pages
- include linked PDFs/documents that look like annual reports, investor presentations, results, transcripts, policies, business updates, or corporate governance documents
- skip login, mailto, tel, social media, tracking, and off-domain links by default
- normalize relative URLs
- hash page/document content for idempotency
- store crawl runs, pages, links, chunks, and searchable text
- use SQLite FTS5 for v1 local full-text search
- promote relevant website chunks into `evidence_chunks` during Company X-Ray

Recommended backend commands:

```text
/company-index DMART
/company-index DMART --refresh
/company-index DMART --max-pages 50
/company-index DMART --include-documents
/company-index --stale-only
```

Search order should become:

1. local company website index
2. official exchange and filing sources
3. internal structured datasets
4. external web/news/research
5. LLM synthesis over stored evidence

## Database Design

Use SQLite first. The repo already uses local database and CSV patterns, and SQLite is enough for v1.

Recommended file:

```text
data/company_intelligence/company_intelligence.db
```

Recommended tables:

### `companies`

- `symbol`
- `company_name`
- `bse_code`
- `isin`
- `sector`
- `industry`
- `website`
- `created_at`
- `updated_at`

### `company_aliases`

- `symbol`
- `alias`
- `alias_type`
- `source`
- `created_at`

### `source_documents`

- `document_id`
- `symbol`
- `source_tier`
- `source_name`
- `source_url`
- `document_type`
- `document_date`
- `local_path`
- `content_hash`
- `fetch_status`
- `parse_status`
- `failure_reason`
- `created_at`

### `search_runs`

- `search_run_id`
- `symbol`
- `verticals`
- `mode`
- `started_at`
- `completed_at`
- `status`
- `summary`

### `search_attempts`

- `attempt_id`
- `search_run_id`
- `source_group`
- `query`
- `alias_used`
- `result_count`
- `urls_found`
- `status`
- `failure_reason`
- `created_at`

### `evidence_chunks`

- `chunk_id`
- `document_id`
- `symbol`
- `category`
- `text`
- `page_number`
- `table_id`
- `source_tier`
- `confidence`
- `evidence_date`
- `created_at`

### `structured_facts`

- `fact_id`
- `symbol`
- `category`
- `fact_name`
- `fact_value`
- `unit`
- `period`
- `evidence_chunk_id`
- `confidence`
- `created_at`

### `sector_entities`

- `sector`
- `entity_type`
- `entity_name`
- `symbol`
- `relationship`
- `evidence_chunk_id`
- `confidence`

### `macro_policy_events`

- `event_id`
- `event_type`
- `event_date`
- `title`
- `source_url`
- `summary`
- `raw_path`
- `created_at`

### `impact_assessments`

- `impact_id`
- `symbol`
- `event_id`
- `impact_area`
- `direction`
- `magnitude`
- `rationale`
- `evidence_chunk_ids`
- `confidence`
- `created_at`

### `analysis_runs`

- `analysis_run_id`
- `symbol`
- `workflow`
- `mode`
- `started_at`
- `completed_at`
- `status`
- `report_path`
- `coverage_score`
- `known_gaps`

### `website_crawl_runs`

- `crawl_run_id`
- `symbol`
- `base_url`
- `started_at`
- `completed_at`
- `status`
- `pages_seen`
- `pages_indexed`
- `documents_found`
- `failure_reason`

### `website_pages`

- `page_id`
- `crawl_run_id`
- `symbol`
- `url`
- `url_hash`
- `title`
- `content_hash`
- `content_type`
- `status`
- `fetched_at`
- `raw_path`
- `text`
- `page_type`

### `website_links`

- `link_id`
- `crawl_run_id`
- `symbol`
- `from_url`
- `to_url`
- `link_text`
- `link_type`
- `is_same_domain`

### `website_page_chunks`

- `chunk_id`
- `page_id`
- `symbol`
- `url`
- `chunk_text`
- `category`
- `created_at`

### `website_search_fts`

SQLite FTS5 virtual table over website chunks:

- `symbol`
- `url`
- `title`
- `category`
- `chunk_text`

## Company X-Ray RIC Workflow

Recommended RIC name:

```text
/ric company-xray SYMBOL
```

Steps:

1. **Resolve identity**
   - Resolve symbol, company name, aliases, sector, peers, website, and filing identifiers.

2. **Build or refresh evidence**
   - Search official sources first, then structured/internal data, then external context.
   - Store search attempts and failures.

3. **Business model extraction**
   - Extract products, segments, revenue engines, channel model, geography, customer base, and operating model.

4. **Sector expansion**
   - Define the sector, value chain, demand drivers, supply drivers, regulatory dependencies, and listed peer universe.

5. **Competitive map**
   - Identify competitors, market share references, customer overlap, distribution advantages, pricing power, and moat evidence.

6. **Financial and market behavior**
   - Pull available financial ratios, growth, margin, balance-sheet signals, technical setup, sector rotation context, and historical snapshots.

7. **RBI and Budget impact**
   - Map monetary-policy and budget events to company sensitivities such as credit demand, interest cost, consumption, capex, infrastructure spending, taxation, imports, exports, and commodity inputs.

8. **Deliberation**
   - Generate bull case, bear case, base case, evidence gaps, disconfirming evidence, and open questions.

9. **Report generation**
   - Produce Markdown and HTML reports with evidence coverage, source tables, and research-only disclaimer.

## Analyst Memo Structure

The final memo should include:

1. Company snapshot
2. Evidence coverage and known gaps
3. Business model
4. Revenue segments
5. Customer base and client concentration
6. Operating model
7. Sector structure
8. Value chain
9. Market share and positioning
10. Competitor map
11. Competitive advantage and moat durability
12. Financial quality
13. Technical and market behavior
14. RBI monetary policy impact
15. Union Budget impact
16. Recent developments
17. Historical pattern analysis
18. Bull case
19. Bear case
20. Base case
21. Open questions
22. Evidence table
23. Research-only disclaimer

## Example: DMART Failure Handling

If a DMART search across analyst coverage, broker research, and concalls finds no direct results, the final answer should not simply say "no results found."

It should report:

- which aliases were searched
- which source groups were searched
- which queries were executed
- which results were found
- which URLs were inaccessible or paywalled
- which documents were parsed
- whether no data was found or parsing failed
- what fallback searches were attempted
- which evidence categories remain weak

This converts a failed search into useful coverage intelligence.

## Modes

### Permissive Mode

Default mode. Always generate a report, but clearly label evidence strength and gaps.

### Strict Mode

Generate a full memo only if minimum thresholds pass:

- company identity resolved
- at least one official filing or official company source parsed
- at least one source for business model
- at least one source for sector or peer context
- search audit completed

If thresholds fail, produce an evidence-gap report instead.

## Integration Points

Likely files to create:

- `company_intelligence_db.py`
- `company_intelligence_search.py`
- `company_intelligence_extract.py`
- `company_intelligence_analyze.py`
- `company_intelligence_report.py`
- `company_intelligence.py`
- `tests/test_company_intelligence_db.py`
- `tests/test_company_intelligence_search.py`
- `tests/test_company_intelligence_report.py`

Likely files to modify:

- `nse_agent.py`
- `terminal/reports.py`
- `docs/AGENT_ADDA_CAPABILITIES.md`
- `docs/BACKLOG.md`

## Testing Strategy

Testing should cover:

- database schema initialization
- idempotent company upsert
- alias expansion
- search-run and search-attempt audit logging
- failed search handling
- evidence chunk classification
- strict-mode threshold behavior
- permissive-mode report behavior
- report generation with source coverage
- DMART no-result-style regression case

## Acceptance Criteria

The design is satisfied when:

- `/ric company-xray SYMBOL` or `/company-xray SYMBOL` can run a company-anchored workflow.
- Search attempts are stored before final synthesis.
- Failed searches are represented in the report with reasons and source coverage.
- Evidence chunks are categorized and queryable.
- Reports distinguish official evidence, external context, and LLM interpretation.
- Strict mode blocks weak reports and emits an evidence-gap report.
- Permissive mode generates a report with visible confidence and gaps.
- Tests cover DB, search audit, strict/permissive mode, and report generation.

## Out of Scope for v1

- Paid data subscriptions
- scraping paywalled brokerage PDFs
- investment recommendations
- broker target aggregation as a trading signal
- real-time streaming ingestion
- automated portfolio action recommendations

## Spec Self-Review

- No incomplete markers remain.
- Scope is company-first with sector expansion.
- Source tiers are explicit.
- Failed search handling is explicit.
- Strict/permissive behavior is explicit.
- Storage separates evidence, facts, search audit, and interpretation.
